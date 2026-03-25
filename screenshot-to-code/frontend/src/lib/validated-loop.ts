import {
  Commit,
  Variant,
  VariantHistoryMessage,
  VariantResumableStop,
} from "../components/commits/types";
import { PromptContent } from "../types";

const LEGACY_MAX_ITERATIONS = 10;

export type ContinuationMode = "validated_loop" | "user_prompt";

export type ContinuationCandidate = {
  issueIndex: number;
  issueVariant: Variant;
  resumableStop: VariantResumableStop;
  mode: ContinuationMode;
  baseCode: string;
  history: VariantHistoryMessage[];
  savedCodePath?: string;
  savedRunDir?: string;
};

function hasPromptReferenceMedia(prompt?: PromptContent | null): boolean {
  return Boolean(prompt?.images.length || (prompt?.videos?.length ?? 0) > 0);
}

export function hasReferenceMediaForContinuation(
  commit?: Commit | null,
  savedRunDir?: string
): boolean {
  if (!commit || commit.type === "code_create") {
    return false;
  }

  return Boolean(
    savedRunDir ||
      commit.inputMode === "image" ||
      commit.inputMode === "video" ||
      hasPromptReferenceMedia(commit.inputs)
  );
}

export function buildContinuationPrompt(
  commit: Exclude<Commit, { type: "code_create" }>,
  options?: {
    useSavedReferenceRunDir?: boolean;
  }
): PromptContent {
  const useSavedReferenceRunDir = options?.useSavedReferenceRunDir === true;
  const originalRequest = commit.inputs.text.trim();
  const hasReferenceMedia = hasReferenceMediaForContinuation(
    commit,
    useSavedReferenceRunDir ? "saved-run-dir" : undefined
  );
  const continuationInstruction = hasReferenceMedia
    ? "Continue from the current implementation and use the reference media as the source of truth. Review the remaining visual, behavior, and animation gaps against the reference, then improve the existing code toward like-for-like fidelity. Treat the current HTML as the working baseline, preserve sections that are already correct, and do not start over."
    : "Continue from the current implementation. Treat the current HTML as the working baseline, preserve working sections, and make the next targeted edits without starting over.";

  return {
    ...commit.inputs,
    text: originalRequest
      ? `${continuationInstruction}\n\nOriginal request:\n${originalRequest}`
      : continuationInstruction,
    images: useSavedReferenceRunDir ? [] : commit.inputs.images,
    videos: useSavedReferenceRunDir ? [] : commit.inputs.videos ?? [],
  };
}

export function isLegacyMaxIterationsVariant(variant?: Variant | null): boolean {
  return (
    variant?.status === "error" &&
    variant.errorMessage?.includes("(max_iterations)") === true &&
    variant.code.trim().length > 0
  );
}

export function getVariantResumableStop(
  variant?: Variant | null
): VariantResumableStop | undefined {
  if (variant?.resumableStop?.canContinue) {
    return variant.resumableStop;
  }

  if (!isLegacyMaxIterationsVariant(variant)) {
    return undefined;
  }

  return {
    stopReason: "max_iterations",
    iterationsCompleted: LEGACY_MAX_ITERATIONS,
    maxIterations: LEGACY_MAX_ITERATIONS,
    canContinue: true,
  };
}

function findCodeBearingVariant(commit?: Commit | null): Variant | null {
  if (!commit) {
    return null;
  }

  const selectedVariant = commit.variants[commit.selectedVariantIndex];
  if (selectedVariant?.code.trim()) {
    return selectedVariant;
  }

  return commit.variants.find((variant) => variant.code.trim().length > 0) ?? null;
}

export function findContinuationCandidate(
  commit?: Commit | null,
  commitsByHash: Record<string, Commit> = {}
): ContinuationCandidate | null {
  if (!commit) {
    return null;
  }

  for (let index = 0; index < commit.variants.length; index += 1) {
    const variant = commit.variants[index];
    const resumableStop = getVariantResumableStop(variant);
    if (resumableStop?.canContinue) {
      return {
        issueIndex: index,
        issueVariant: variant,
        resumableStop,
        mode: "validated_loop",
        baseCode: variant.code,
        history: variant.history || [],
        savedCodePath: variant.savedCodePath,
        savedRunDir: variant.savedRunDir,
      };
    }
  }

  if (commit.type === "code_create") {
    return null;
  }

  const issueIndex = commit.variants.findIndex(
    (variant) => variant.status === "error" || variant.status === "paused"
  );

  if (issueIndex === -1) {
    return null;
  }

  const issueVariant = commit.variants[issueIndex];
  const parentBaseVariant =
    commit.parentHash !== null
      ? findCodeBearingVariant(commitsByHash[commit.parentHash] || null)
      : null;
  const baseCode = issueVariant.code.trim() ? issueVariant.code : parentBaseVariant?.code || "";
  const hasReferenceMedia = hasReferenceMediaForContinuation(
    commit,
    issueVariant.savedRunDir
  );

  if (!baseCode.trim()) {
    return null;
  }

  return {
    issueIndex,
    issueVariant,
    resumableStop: {
      stopReason: "generation_issue",
      canContinue: true,
    },
    mode: hasReferenceMedia ? "validated_loop" : "user_prompt",
    baseCode,
    history: issueVariant.history || [],
    savedCodePath: issueVariant.savedCodePath,
    savedRunDir: issueVariant.savedRunDir,
  };
}

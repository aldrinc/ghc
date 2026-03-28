import {
  buildContinuationPrompt,
  findContinuationCandidate,
  getVariantResumableStop,
  hasReferenceMediaForContinuation,
  isLegacyMaxIterationsVariant,
} from "./validated-loop";
import { AiCreateCommit, Commit } from "../components/commits/types";

function buildCommit(overrides?: Partial<AiCreateCommit>): AiCreateCommit {
  return {
    hash: "commit-1",
    type: "ai_create",
    parentHash: null,
    dateCreated: new Date("2026-03-19T12:00:00.000Z"),
    isCommitted: false,
    selectedVariantIndex: 1,
    inputs: {
      text: "Create this page",
      images: [],
      videos: [],
      referenceUrl: undefined,
    },
    variants: [
      {
        code: "<html>resume</html>",
        history: [],
        status: "error",
        errorMessage:
          "Validated loop stopped before reaching a passing result (max_iterations).",
      },
      {
        code: "<html>done</html>",
        history: [],
        status: "complete",
      },
    ],
    ...overrides,
  };
}

function buildAnyCommit(overrides?: Partial<Commit>): Commit {
  return {
    ...buildCommit(),
    ...overrides,
  } as Commit;
}

describe("validated loop helpers", () => {
  it("treats legacy max-iteration errors as resumable", () => {
    const variant = buildCommit().variants[0];

    expect(isLegacyMaxIterationsVariant(variant)).toBe(true);
    expect(getVariantResumableStop(variant)).toEqual({
      stopReason: "max_iterations",
      iterationsCompleted: 10,
      maxIterations: 10,
      canContinue: true,
    });
  });

  it("finds a resumable variant even when it is not selected", () => {
    const commit = buildCommit();

    expect(findContinuationCandidate(commit)).toMatchObject({
      issueIndex: 0,
      mode: "validated_loop",
      resumableStop: {
        stopReason: "max_iterations",
        canContinue: true,
      },
    });
  });

  it("prefers explicit resumable-stop metadata when present", () => {
    const commit = buildCommit({
      variants: [
        {
          code: "<html>paused</html>",
          history: [],
          status: "paused",
          resumableStop: {
            stopReason: "max_iterations",
            iterationsCompleted: 20,
            maxIterations: 10,
            canContinue: true,
          },
        },
      ],
      selectedVariantIndex: 0,
    });

    expect(findContinuationCandidate(commit)).toMatchObject({
      issueIndex: 0,
      mode: "validated_loop",
      resumableStop: {
        iterationsCompleted: 20,
        maxIterations: 10,
        canContinue: true,
      },
    });
  });

  it("treats failed user-prompt updates with current code as continuable", () => {
    const commit = buildAnyCommit({
      type: "ai_edit",
      variants: [
        {
          code: "<html>partial update</html>",
          history: [],
          status: "error",
          errorMessage: "Generation interrupted by refresh.",
        },
      ],
      selectedVariantIndex: 0,
    });

    expect(findContinuationCandidate(commit)).toMatchObject({
      issueIndex: 0,
      mode: "user_prompt",
      resumableStop: {
        stopReason: "generation_issue",
        canContinue: true,
      },
    });
  });

  it("falls back to parent code for failed user-prompt updates with blank output", () => {
    const parentCommit = buildAnyCommit({
      hash: "parent-1",
      selectedVariantIndex: 0,
      variants: [
        {
          code: "<html>parent base</html>",
          history: [],
          status: "complete",
        },
      ],
    });
    const commit = buildAnyCommit({
      type: "ai_edit",
      parentHash: parentCommit.hash,
      variants: [
        {
          code: "",
          history: [],
          status: "error",
          errorMessage: "Generation interrupted by refresh.",
        },
      ],
      selectedVariantIndex: 0,
    });

    expect(
      findContinuationCandidate(commit, { [parentCommit.hash]: parentCommit })
    ).toMatchObject({
      issueIndex: 0,
      mode: "user_prompt",
      baseCode: "<html>parent base</html>",
    });
  });

  it("keeps media-backed failed updates in validated-loop mode", () => {
    const commit = buildAnyCommit({
      type: "ai_edit",
      inputMode: "video",
      inputs: {
        text: "Continue matching the video",
        images: [],
        videos: [],
      },
      variants: [
        {
          code: "<html>partial update</html>",
          history: [],
          status: "error",
          errorMessage: "Generation interrupted by refresh.",
          savedRunDir: "/tmp/validated-loop/run-1",
        },
      ],
      selectedVariantIndex: 0,
    });

    expect(findContinuationCandidate(commit)).toMatchObject({
      issueIndex: 0,
      mode: "validated_loop",
      savedRunDir: "/tmp/validated-loop/run-1",
      resumableStop: {
        stopReason: "generation_issue",
        canContinue: true,
      },
    });
  });

  it("recognizes saved-run media as reference media for continuation", () => {
    const commit = buildAnyCommit({
      type: "ai_edit",
      inputMode: "video",
      inputs: {
        text: "",
        images: [],
        videos: [],
      },
    });

    expect(hasReferenceMediaForContinuation(commit, "/tmp/validated-loop/run-2")).toBe(
      true
    );
  });

  it("treats a saved reference URL as reference media for continuation", () => {
    const commit = buildAnyCommit({
      type: "ai_edit",
      inputMode: "text",
      inputs: {
        text: "",
        images: [],
        videos: [],
        referenceUrl: "https://example.com/reference",
      },
    });

    expect(hasReferenceMediaForContinuation(commit)).toBe(true);
  });

  it("builds a continuation prompt that resumes from current code and saved media", () => {
    const commit = buildAnyCommit({
      type: "ai_edit",
      inputMode: "video",
      inputs: {
        text: "Match the uploaded walkthrough video.",
        images: [],
        videos: ["data:video/mp4;base64,AAAA"],
      },
    }) as Extract<Commit, { type: "ai_edit" }>;

    const continuationPrompt = buildContinuationPrompt(commit, {
      useSavedReferenceRunDir: true,
    });

    expect(continuationPrompt.text).toContain(
      "Continue from the current implementation and use the reference media as the source of truth."
    );
    expect(continuationPrompt.text).toContain(
      "Original request:\nMatch the uploaded walkthrough video."
    );
    expect(continuationPrompt.images).toEqual([]);
    expect(continuationPrompt.videos).toEqual([]);
  });

  it("preserves the reference URL on continuation prompts", () => {
    const commit = buildAnyCommit({
      type: "ai_edit",
      inputMode: "image",
      inputs: {
        text: "Match the marketing page.",
        images: ["data:image/png;base64,AAAA"],
        videos: [],
        referenceUrl: "https://example.com/live-page",
      },
    }) as Extract<Commit, { type: "ai_edit" }>;

    const continuationPrompt = buildContinuationPrompt(commit);

    expect(continuationPrompt.referenceUrl).toBe("https://example.com/live-page");
  });
});

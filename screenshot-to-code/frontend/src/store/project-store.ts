import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  AgentEvent,
  AiCreateCommit,
  AiEditCommit,
  CodeCreateCommit,
  Commit,
  CommitHash,
  VariantResumableStop,
  VariantHistoryMessage,
  Variant,
  VariantStatus,
} from "../components/commits/types";
import { PromptAsset } from "../types";

const PROJECT_STORE_STORAGE_KEY = "project-store-v1";
const REFRESH_INTERRUPTED_MESSAGE = "Generation interrupted by refresh.";
const PERSISTED_EVENT_CONTENT_MAX_LENGTH = 8_000;
const PERSISTED_CODE_MAX_LENGTH = 250_000;
const PERSISTED_PROMPT_TEXT_MAX_LENGTH = 12_000;
const PERSISTED_CONSOLE_LINE_LIMIT = 200;
const PERSISTED_CONSOLE_LINE_MAX_LENGTH = 2_000;

function createEmptyVariant(): Variant {
  return {
    code: "",
    history: [],
    agentEvents: [],
  };
}

function pickCanonicalVariantIndex(commit: Commit): number {
  const variants = commit.variants;
  if (variants.length === 0) {
    return 0;
  }

  const completeWithCodeIndex = variants.findIndex(
    (variant) => variant.status === "complete" && variant.code.trim().length > 0
  );
  if (completeWithCodeIndex !== -1) {
    return completeWithCodeIndex;
  }

  const selectedVariant = variants[commit.selectedVariantIndex];
  if (selectedVariant?.code.trim().length) {
    return commit.selectedVariantIndex;
  }

  const firstCodeIndex = variants.findIndex(
    (variant) => variant.code.trim().length > 0
  );
  if (firstCodeIndex !== -1) {
    return firstCodeIndex;
  }

  const issueIndex = variants.findIndex(
    (variant) => variant.status === "paused" || variant.status === "error"
  );
  if (issueIndex !== -1) {
    return issueIndex;
  }

  return Math.min(commit.selectedVariantIndex, variants.length - 1);
}

function collapseCommitToSingleVariant(commit: Commit): Commit {
  const variants = commit.variants.length > 0 ? commit.variants : [createEmptyVariant()];
  const canonicalVariant = variants[pickCanonicalVariantIndex(commit)] || variants[0];
  const resumableSibling = variants.find(
    (variant) =>
      variant !== canonicalVariant &&
      (
        variant.resumableStop?.canContinue === true ||
        variant.status === "error" ||
        variant.status === "paused" ||
        variant.errorMessage?.includes("(max_iterations)") === true
      )
  );
  const mergedVariant =
    resumableSibling && !canonicalVariant.resumableStop?.canContinue
      ? {
          ...canonicalVariant,
          resumableStop:
            resumableSibling.resumableStop ??
            ({
              stopReason: resumableSibling.errorMessage?.includes("(max_iterations)")
                ? "max_iterations"
                : "generation_issue",
              canContinue: true,
            } satisfies VariantResumableStop),
          savedCodePath:
            canonicalVariant.savedCodePath ?? resumableSibling.savedCodePath,
          savedRunDir: canonicalVariant.savedRunDir ?? resumableSibling.savedRunDir,
        }
      : canonicalVariant;
  return {
    ...commit,
    variants: [mergedVariant],
    selectedVariantIndex: 0,
  };
}

// Store for app-wide state
interface ProjectStore {
  // Inputs
  inputMode: "image" | "video" | "text";
  setInputMode: (mode: "image" | "video" | "text") => void;
  referenceImages: string[];
  setReferenceImages: (images: string[]) => void;
  initialPrompt: string;
  setInitialPrompt: (prompt: string) => void;
  assetsById: Record<string, PromptAsset>;
  upsertPromptAssets: (assets: PromptAsset[]) => void;
  resetPromptAssets: () => void;

  // Outputs
  commits: Record<string, Commit>;
  head: CommitHash | null;
  latestCommitHash: CommitHash | null;

  addCommit: (commit: Commit) => void;
  removeCommit: (hash: CommitHash) => void;
  resetCommits: () => void;

  appendCommitCode: (
    hash: CommitHash,
    numVariant: number,
    code: string
  ) => void;
  appendVariantThinking: (
    hash: CommitHash,
    numVariant: number,
    thinking: string
  ) => void;
  setCommitCode: (hash: CommitHash, numVariant: number, code: string) => void;
  appendVariantHistoryMessage: (
    hash: CommitHash,
    numVariant: number,
    message: VariantHistoryMessage
  ) => void;
  updateSelectedVariantIndex: (hash: CommitHash, index: number) => void;
  updateVariantStatus: (
    hash: CommitHash,
    numVariant: number,
    status: VariantStatus,
    errorMessage?: string
  ) => void;
  setVariantResumableStop: (
    hash: CommitHash,
    numVariant: number,
    resumableStop?: VariantResumableStop
  ) => void;
  setVariantArtifactLocation: (
    hash: CommitHash,
    numVariant: number,
    savedCodePath?: string,
    savedRunDir?: string
  ) => void;
  resizeVariants: (hash: CommitHash, count: number) => void;
  setVariantModels: (hash: CommitHash, models: string[]) => void;
  collapseCommitsToSingleVariant: () => void;

  startAgentEvent: (
    hash: CommitHash,
    numVariant: number,
    event: AgentEvent
  ) => void;
  appendAgentEventContent: (
    hash: CommitHash,
    numVariant: number,
    eventId: string,
    content: string
  ) => void;
  finishAgentEvent: (
    hash: CommitHash,
    numVariant: number,
    eventId: string,
    updates: Partial<AgentEvent>
  ) => void;

  setHead: (hash: CommitHash) => void;
  resetHead: () => void;

  executionConsoles: { [key: number]: string[] };
  appendExecutionConsole: (variantIndex: number, line: string) => void;
  resetExecutionConsoles: () => void;
}

type PersistedProjectState = Pick<
  ProjectStore,
  | "inputMode"
  | "referenceImages"
  | "initialPrompt"
  | "assetsById"
  | "commits"
  | "head"
  | "latestCommitHash"
  | "executionConsoles"
>;

function truncatePersistedText(value: string | undefined, maxLength: number) {
  if (!value) return value;
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}\n\n[truncated for persistence]`;
}

function sanitizePersistedAgentEvent(event: AgentEvent): AgentEvent {
  return {
    ...event,
    content: truncatePersistedText(event.content, PERSISTED_EVENT_CONTENT_MAX_LENGTH),
    input: undefined,
    output: undefined,
  };
}

function sanitizePersistedVariant(variant: Variant): Variant {
  return {
    ...variant,
    code: truncatePersistedText(variant.code, PERSISTED_CODE_MAX_LENGTH) || "",
    agentEvents: (variant.agentEvents || []).map(sanitizePersistedAgentEvent),
  };
}

function sanitizePersistedCommit(commit: Commit): Commit {
  const collapsedCommit = collapseCommitToSingleVariant(commit);
  const baseCommit = {
    ...collapsedCommit,
    variants: collapsedCommit.variants.map(sanitizePersistedVariant),
  };

  if (commit.type === "code_create") {
    return {
      ...baseCommit,
      type: "code_create",
      inputs: null,
    };
  }

  return {
    ...baseCommit,
    type: commit.type,
    inputs: {
      text: truncatePersistedText(
        commit.inputs.text,
        PERSISTED_PROMPT_TEXT_MAX_LENGTH
      ) || "",
      images: [],
      videos: [],
      selectedElementHtml: truncatePersistedText(
        commit.inputs.selectedElementHtml,
        PERSISTED_PROMPT_TEXT_MAX_LENGTH
      ),
    },
  };
}

function sanitizePersistedExecutionConsoles(
  executionConsoles: PersistedProjectState["executionConsoles"]
): PersistedProjectState["executionConsoles"] {
  const mergedLines = Object.entries(executionConsoles)
    .sort(([left], [right]) => Number(left) - Number(right))
    .flatMap(([, lines]) => lines);

  if (mergedLines.length === 0) {
    return {};
  }

  return {
    0: mergedLines
      .slice(-PERSISTED_CONSOLE_LINE_LIMIT)
      .map((line) => truncatePersistedText(line, PERSISTED_CONSOLE_LINE_MAX_LENGTH) || ""),
  };
}

export function toPersistedProjectState(
  state: PersistedProjectState
): PersistedProjectState {
  return {
    inputMode: state.inputMode,
    referenceImages: [],
    initialPrompt:
      truncatePersistedText(state.initialPrompt, PERSISTED_PROMPT_TEXT_MAX_LENGTH) || "",
    assetsById: {},
    commits: Object.fromEntries(
      Object.entries(state.commits).map(([hash, commit]) => [
        hash,
        sanitizePersistedCommit(commit),
      ])
    ),
    head: state.head,
    latestCommitHash: state.latestCommitHash,
    executionConsoles: sanitizePersistedExecutionConsoles(state.executionConsoles),
  };
}

const safeLocalStorage = {
  getItem: (name: string) => window.localStorage.getItem(name),
  setItem: (name: string, value: string) => {
    try {
      window.localStorage.setItem(name, value);
    } catch (error) {
      console.error("Failed to persist project state to localStorage.", error);
    }
  },
  removeItem: (name: string) => {
    try {
      window.localStorage.removeItem(name);
    } catch (error) {
      console.error("Failed to remove persisted project state.", error);
    }
  },
};

function normalizeAgentEvent(event: AgentEvent, nowMs: number): AgentEvent {
  if (event.status !== "running") {
    return event;
  }

  return {
    ...event,
    status: "error",
    endedAt: event.endedAt ?? nowMs,
  };
}

function normalizeVariant(variant: Variant, nowMs: number): Variant {
  const wasGenerating = variant.status === "generating";
  return {
    ...variant,
    history: variant.history || [],
    status: wasGenerating ? "error" : variant.status,
    completedAt: wasGenerating ? variant.completedAt ?? nowMs : variant.completedAt,
    errorMessage: wasGenerating
      ? variant.errorMessage || REFRESH_INTERRUPTED_MESSAGE
      : variant.errorMessage,
    thinkingStartTime: wasGenerating ? undefined : variant.thinkingStartTime,
    agentEvents: (variant.agentEvents || []).map((event) =>
      normalizeAgentEvent(event, nowMs)
    ),
  };
}

function rehydratePersistedCommit(commit: Commit, nowMs: number): Commit {
  const collapsedCommit = collapseCommitToSingleVariant(commit);
  const baseCommit = {
    ...collapsedCommit,
    dateCreated: new Date(commit.dateCreated),
    variants: collapsedCommit.variants.map((variant) =>
      normalizeVariant(variant, nowMs)
    ),
  };

  switch (commit.type) {
    case "ai_create":
      return {
        ...(baseCommit as Omit<AiCreateCommit, "type" | "inputs">),
        type: "ai_create",
        inputs: commit.inputs,
      };
    case "ai_edit":
      return {
        ...(baseCommit as Omit<AiEditCommit, "type" | "inputs">),
        type: "ai_edit",
        inputs: commit.inputs,
      };
    case "code_create":
      return {
        ...(baseCommit as Omit<CodeCreateCommit, "type" | "inputs">),
        type: "code_create",
        inputs: null,
      };
  }
}

export function rehydratePersistedCommits(
  commits: Record<string, Commit>,
  nowMs: number = Date.now()
): Record<string, Commit> {
  return Object.fromEntries(
    Object.entries(commits).map(([hash, commit]) => [
      hash,
      rehydratePersistedCommit(commit, nowMs),
    ])
  );
}

export function sanitizePersistedProjectState(
  persistedState: Partial<PersistedProjectState>,
  nowMs: number = Date.now()
): Partial<PersistedProjectState> {
  const commits = rehydratePersistedCommits(persistedState.commits || {}, nowMs);
  const commitHashes = new Set(Object.keys(commits));
  const latestCommitHash =
    persistedState.latestCommitHash && commitHashes.has(persistedState.latestCommitHash)
      ? persistedState.latestCommitHash
      : Object.keys(commits).at(-1) ?? null;
  const head =
    persistedState.head && commitHashes.has(persistedState.head)
      ? persistedState.head
      : latestCommitHash;

  return {
    inputMode: persistedState.inputMode ?? "image",
    referenceImages: persistedState.referenceImages ?? [],
    initialPrompt: persistedState.initialPrompt ?? "",
    assetsById: persistedState.assetsById ?? {},
    commits,
    head,
    latestCommitHash,
    executionConsoles: sanitizePersistedExecutionConsoles(
      persistedState.executionConsoles ?? {}
    ),
  };
}

export const useProjectStore = create<ProjectStore>()(
  persist(
    (set) => ({
  // Inputs and their setters
  inputMode: "image",
  setInputMode: (mode) => set({ inputMode: mode }),
  referenceImages: [],
  setReferenceImages: (images) => set({ referenceImages: images }),
  initialPrompt: "",
  setInitialPrompt: (prompt) => set({ initialPrompt: prompt }),
  assetsById: {},
  upsertPromptAssets: (assets) =>
    set((state) => {
      if (assets.length === 0) return state;
      const merged = { ...state.assetsById };
      for (const asset of assets) {
        merged[asset.id] = asset;
      }
      return { assetsById: merged };
    }),
  resetPromptAssets: () => set({ assetsById: {} }),

  // Outputs
  commits: {},
  head: null,
  latestCommitHash: null,

  addCommit: (commit: Commit) => {
    const requestStartedAt = new Date(commit.dateCreated).getTime();
    const singleVariantCommit = collapseCommitToSingleVariant(commit);
    // Initialize variant statuses as 'generating' and start thinking timer
    const commitsWithStatus = {
      ...singleVariantCommit,
      variants: singleVariantCommit.variants.map((variant) => ({
        ...variant,
        history: variant.history || [],
        requestStartedAt:
          variant.requestStartedAt ?? requestStartedAt,
        status: variant.status || ("generating" as VariantStatus),
        thinkingStartTime: Date.now(),
        agentEvents: [],
      })),
    };

    // When adding a new commit, make sure all existing commits are marked as committed
    set((state) => ({
      commits: {
        ...Object.fromEntries(
          Object.entries(state.commits).map(([hash, existingCommit]) => [
            hash,
            { ...existingCommit, isCommitted: true },
          ])
        ),
        [commitsWithStatus.hash]: commitsWithStatus,
      },
      latestCommitHash: commitsWithStatus.hash,
    }));
  },
  removeCommit: (hash: CommitHash) => {
    set((state) => {
      const removedCommit = state.commits[hash];
      const newCommits = { ...state.commits };
      delete newCommits[hash];

      // If removing the latest commit, fall back to its parent
      const newLatestCommitHash =
        state.latestCommitHash === hash
          ? (removedCommit?.parentHash ?? null)
          : state.latestCommitHash;

      return { commits: newCommits, latestCommitHash: newLatestCommitHash };
    });
  },
  resetCommits: () => set({ commits: {}, latestCommitHash: null }),

  appendCommitCode: (hash: CommitHash, numVariant: number, code: string) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit) {
        return state;
      }
      // Don't update if the commit is already committed
      if (commit.isCommitted) {
        return state;
      }
      const variant = commit.variants[numVariant];
      const isFirstCode = !variant.code && variant.thinkingStartTime;
      const duration = isFirstCode
        ? Math.round((Date.now() - variant.thinkingStartTime!) / 1000)
        : variant.thinkingDuration;
      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: commit.variants.map((v, index) =>
              index === numVariant
                ? { ...v, code: v.code + code, thinkingDuration: duration }
                : v
            ),
          },
        },
      };
    }),
  appendVariantThinking: (hash: CommitHash, numVariant: number, thinking: string) =>
    set((state) => {
      const commit = state.commits[hash];
      // Don't update if the commit is already committed
      if (commit.isCommitted) {
        throw new Error("Attempted to append thinking to a committed commit");
      }
      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: commit.variants.map((v, index) =>
              index === numVariant
                ? {
                    ...v,
                    thinking: (v.thinking || "") + thinking,
                  }
                : v
            ),
          },
        },
      };
    }),
  setCommitCode: (hash: CommitHash, numVariant: number, code: string) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit) {
        return state;
      }
      // Don't update if the commit is already committed
      if (commit.isCommitted) {
        return state;
      }
      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: commit.variants.map((variant, index) =>
              index === numVariant ? { ...variant, code } : variant
            ),
          },
        },
      };
    }),
  appendVariantHistoryMessage: (hash, numVariant, message) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit || commit.isCommitted) return state;
      const variants = commit.variants.map((variant, index) => {
        if (index !== numVariant) return variant;
        const history = variant.history || [];
        const last = history[history.length - 1];
        const isDuplicate =
          last &&
          last.role === message.role &&
          last.text === message.text &&
          last.imageAssetIds.join("|") === message.imageAssetIds.join("|") &&
          last.videoAssetIds.join("|") === message.videoAssetIds.join("|");
        if (isDuplicate) return variant;
        return { ...variant, history: [...history, message] };
      });
      return {
        commits: {
          ...state.commits,
          [hash]: { ...commit, variants },
        },
      };
    }),
  updateSelectedVariantIndex: (hash: CommitHash, index: number) =>
    set((state) => {
      const commit = state.commits[hash];
      // Don't update if the commit is already committed
      if (commit.isCommitted) {
        throw new Error(
          "Attempted to update selected variant index of a committed commit"
        );
      }

      // Just update the selected variant index without canceling other variants
      // This allows users to switch between variants even while they're still generating
      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            selectedVariantIndex: index,
          },
        },
      };
    }),
  updateVariantStatus: (
    hash: CommitHash,
    numVariant: number,
    status: VariantStatus,
    errorMessage?: string
  ) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit) return state; // No change if commit doesn't exist

      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: commit.variants.map((variant, index) =>
              index === numVariant 
                ? {
                    ...variant,
                    status,
                    completedAt:
                      status === "generating"
                        ? undefined
                        : variant.completedAt ?? Date.now(),
                    errorMessage: status === "error" ? errorMessage : undefined,
                  }
                : variant
            ),
          },
        },
      };
    }),
  setVariantResumableStop: (hash, numVariant, resumableStop) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit) return state;

      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: commit.variants.map((variant, index) =>
              index === numVariant ? { ...variant, resumableStop } : variant
            ),
          },
        },
      };
    }),
  setVariantArtifactLocation: (hash, numVariant, savedCodePath, savedRunDir) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit) return state;

      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: commit.variants.map((variant, index) =>
              index === numVariant
                ? { ...variant, savedCodePath, savedRunDir }
                : variant
            ),
          },
        },
      };
    }),
  resizeVariants: (hash: CommitHash, _count: number) =>
    set((state) => {
      void _count;
      const commit = state.commits[hash];
      if (!commit) return state; // No change if commit doesn't exist

      const normalizedCount = 1;
      const currentVariants = collapseCommitToSingleVariant(commit).variants;
      const requestStartedAt = new Date(commit.dateCreated).getTime();
      const seedHistory = currentVariants[0]?.history || [];
      const newVariants = Array(normalizedCount).fill(null).map((_, index) => 
        currentVariants[index] || {
          code: "",
          history: seedHistory.map((message) => ({
            ...message,
            imageAssetIds: [...message.imageAssetIds],
            videoAssetIds: [...message.videoAssetIds],
          })),
          requestStartedAt,
          status: "generating" as VariantStatus,
          agentEvents: [],
        }
      );

      return {
        commits: {
          ...state.commits,
          [hash]: {
            ...commit,
            variants: newVariants,
            selectedVariantIndex: 0,
          },
        },
      };
    }),
  setVariantModels: (hash: CommitHash, models: string[]) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit || commit.isCommitted) return state;
      const variants = commit.variants.map((variant, index) => ({
        ...variant,
        model: models[index] ?? variant.model,
      }));
      return {
        commits: {
          ...state.commits,
          [hash]: { ...commit, variants },
        },
      };
    }),

  startAgentEvent: (hash, numVariant, event) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit || commit.isCommitted) return state;
      const variants = commit.variants.map((variant, index) => {
        if (index !== numVariant) return variant;
        const events = variant.agentEvents || [];
        const existingIndex = events.findIndex((e) => e.id === event.id);
        if (existingIndex === -1) {
          return { ...variant, agentEvents: [...events, event] };
        }
        const updatedEvents = events.map((e) =>
          e.id === event.id
            ? {
                ...e,
                ...event,
                content: event.content ? event.content : e.content,
                startedAt: e.startedAt || event.startedAt,
              }
            : e
        );
        return { ...variant, agentEvents: updatedEvents };
      });
      return {
        commits: {
          ...state.commits,
          [hash]: { ...commit, variants },
        },
      };
    }),

  appendAgentEventContent: (hash, numVariant, eventId, content) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit || commit.isCommitted) return state;
      const variants = commit.variants.map((variant, index) => {
        if (index !== numVariant) return variant;
        const events = variant.agentEvents || [];
        const updatedEvents = events.map((event) =>
          event.id === eventId
            ? { ...event, content: (event.content || "") + content }
            : event
        );
        return { ...variant, agentEvents: updatedEvents };
      });
      return {
        commits: {
          ...state.commits,
          [hash]: { ...commit, variants },
        },
      };
    }),

  finishAgentEvent: (hash, numVariant, eventId, updates) =>
    set((state) => {
      const commit = state.commits[hash];
      if (!commit || commit.isCommitted) return state;
      const variants = commit.variants.map((variant, index) => {
        if (index !== numVariant) return variant;
        const events = variant.agentEvents || [];
        const updatedEvents = events.map((event) =>
          event.id === eventId
            ? {
                ...event,
                ...updates,
                // Preserve the original terminal timestamp/status once set.
                endedAt:
                  event.endedAt !== undefined ? event.endedAt : updates.endedAt,
                status:
                  event.status !== "running" ? event.status : updates.status ?? event.status,
              }
            : event
        );
        return { ...variant, agentEvents: updatedEvents };
      });
      return {
        commits: {
          ...state.commits,
          [hash]: { ...commit, variants },
        },
      };
    }),
  collapseCommitsToSingleVariant: () =>
    set((state) => ({
      commits: Object.fromEntries(
        Object.entries(state.commits).map(([hash, commit]) => [
          hash,
          collapseCommitToSingleVariant(commit),
        ])
      ),
    })),

  setHead: (hash: CommitHash) => set({ head: hash }),
  resetHead: () => set({ head: null }),

  executionConsoles: {},
  appendExecutionConsole: (variantIndex: number, line: string) =>
    set((state) => ({
      executionConsoles: {
        ...state.executionConsoles,
        [variantIndex]: [
          ...(state.executionConsoles[variantIndex] || []),
          line,
        ],
      },
    })),
  resetExecutionConsoles: () => set({ executionConsoles: {} }),
    }),
    {
      name: PROJECT_STORE_STORAGE_KEY,
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: (state): PersistedProjectState =>
        toPersistedProjectState({
          inputMode: state.inputMode,
          referenceImages: state.referenceImages,
          initialPrompt: state.initialPrompt,
          assetsById: state.assetsById,
          commits: state.commits,
          head: state.head,
          latestCommitHash: state.latestCommitHash,
          executionConsoles: state.executionConsoles,
        }),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...sanitizePersistedProjectState(
          (persistedState as Partial<PersistedProjectState>) || {}
        ),
      }),
    }
  )
);

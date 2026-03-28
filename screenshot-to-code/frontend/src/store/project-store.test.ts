import {
  sanitizePersistedProjectState,
  toPersistedProjectState,
} from "./project-store";
import { AiCreateCommit } from "../components/commits/types";

function buildPersistedCommit(
  overrides?: Partial<AiCreateCommit>
): AiCreateCommit {
  return {
    hash: "commit-1",
    type: "ai_create",
    parentHash: null,
    dateCreated: new Date("2026-03-17T12:00:00.000Z"),
    isCommitted: false,
    selectedVariantIndex: 0,
    inputs: {
      text: "Create this page",
      images: ["data:image/png;base64,abc"],
      videos: [],
    },
    variants: [
      {
        code: "<html></html>",
        history: [],
        status: "complete",
        agentEvents: [],
      },
    ],
    ...overrides,
  };
}

describe("sanitizePersistedProjectState", () => {
  it("falls back to the latest commit when the saved head is invalid", () => {
    const commit = buildPersistedCommit();
    const sanitized = sanitizePersistedProjectState({
      commits: { [commit.hash]: commit },
      head: "missing",
      latestCommitHash: commit.hash,
      executionConsoles: { 0: ["hello"] },
    });

    expect(sanitized.head).toBe(commit.hash);
    expect(sanitized.latestCommitHash).toBe(commit.hash);
    expect(sanitized.executionConsoles).toEqual({ 0: ["hello"] });
  });

  it("marks generating variants as interrupted after refresh", () => {
    const commit = buildPersistedCommit({
      variants: [
        {
          code: "<html></html>",
          history: [],
          status: "generating",
          agentEvents: [
            {
              id: "evt-1",
              type: "thinking",
              status: "running",
              startedAt: 1,
            },
          ],
        },
      ],
    });

    const sanitized = sanitizePersistedProjectState(
      {
        commits: { [commit.hash]: commit },
        head: commit.hash,
        latestCommitHash: commit.hash,
      },
      1234
    );

    const rehydratedCommit = sanitized.commits?.[commit.hash];
    const variant = rehydratedCommit?.variants[0];

    expect(rehydratedCommit?.dateCreated).toBeInstanceOf(Date);
    expect(variant?.status).toBe("error");
    expect(variant?.completedAt).toBe(1234);
    expect(variant?.errorMessage).toBe("Generation interrupted by refresh.");
    expect(variant?.agentEvents?.[0].status).toBe("error");
    expect(variant?.agentEvents?.[0].endedAt).toBe(1234);
  });

  it("collapses persisted multi-variant commits to a single canonical variant", () => {
    const commit = buildPersistedCommit({
      selectedVariantIndex: 0,
      variants: [
        {
          code: "",
          history: [],
          status: "error",
          errorMessage: "Earlier broken option",
          agentEvents: [],
        },
        {
          code: "<html>working output</html>",
          history: [],
          status: "complete",
          agentEvents: [],
        },
      ],
    });

    const sanitized = sanitizePersistedProjectState({
      commits: { [commit.hash]: commit },
      head: commit.hash,
      latestCommitHash: commit.hash,
      executionConsoles: { 0: ["failed"], 1: ["worked"] },
    });

    const rehydratedCommit = sanitized.commits?.[commit.hash];
    expect(rehydratedCommit?.variants).toHaveLength(1);
    expect(rehydratedCommit?.variants[0].code).toBe("<html>working output</html>");
    expect(rehydratedCommit?.variants[0].resumableStop).toEqual({
      stopReason: "generation_issue",
      canContinue: true,
    });
    expect(rehydratedCommit?.selectedVariantIndex).toBe(0);
    expect(sanitized.executionConsoles).toEqual({ 0: ["failed", "worked"] });
  });
});

describe("toPersistedProjectState", () => {
  it("drops heavy media and tool payloads before writing to localStorage", () => {
    const commit = buildPersistedCommit({
      inputs: {
        text: "Create this page",
        images: ["data:image/png;base64,abc"],
        videos: ["data:video/mp4;base64,xyz"],
        referenceUrl: "https://example.com/reference",
      },
      variants: [
        {
          code: "<html></html>",
          history: [],
          status: "complete",
          agentEvents: [
            {
              id: "evt-1",
              type: "tool",
              status: "complete",
              startedAt: 1,
              input: { huge: true },
              output: { alsoHuge: true },
              content: "tool content",
            },
          ],
        },
      ],
    });

    const persisted = toPersistedProjectState({
      inputMode: "video",
      referenceImages: ["data:image/png;base64,abc"],
      initialPrompt: "Initial prompt",
      assetsById: {
        asset1: {
          id: "asset1",
          type: "video",
          dataUrl: "data:video/mp4;base64,xyz",
        },
      },
      commits: { [commit.hash]: commit },
      head: commit.hash,
      latestCommitHash: commit.hash,
      executionConsoles: { 0: ["line 1"] },
    });

    const persistedCommit = persisted.commits[commit.hash];
    const persistedEvent = persistedCommit.variants[0].agentEvents?.[0];

    expect(persisted.referenceImages).toEqual([]);
    expect(persisted.assetsById).toEqual({});
    expect(persistedCommit.inputs?.images).toEqual([]);
    expect(persistedCommit.inputs?.videos).toEqual([]);
    expect(persistedCommit.inputs?.referenceUrl).toBe(
      "https://example.com/reference"
    );
    expect(persistedEvent?.input).toBeUndefined();
    expect(persistedEvent?.output).toBeUndefined();
  });
});

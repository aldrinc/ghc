import { useEffect, useRef, useState } from "react";
import { generateCode } from "./generateCode";
import { AppState, AppTheme, EditorTheme, Settings } from "./types";
import { HTTP_BACKEND_URL, IS_RUNNING_ON_CLOUD } from "./config";
import { PicoBadge } from "./components/messages/PicoBadge";
import { OnboardingNote } from "./components/messages/OnboardingNote";
import { usePersistedState } from "./hooks/usePersistedState";
import TermsOfServiceDialog from "./components/TermsOfServiceDialog";
import { USER_CLOSE_WEB_SOCKET_CODE } from "./constants";
import toast from "react-hot-toast";
import { nanoid } from "nanoid";
import { DEFAULT_STACK, Stack } from "./lib/stacks";
import { CodeGenerationModel } from "./lib/models";
import useBrowserTabIndicator from "./hooks/useBrowserTabIndicator";
import { LuChevronLeft } from "react-icons/lu";
import {
  buildAssistantHistoryMessage,
  buildUserHistoryMessage,
  cloneVariantHistory,
  GenerationRequest,
  registerAssetIds,
  toRequestHistory,
} from "./lib/prompt-history";
// import TipLink from "./components/messages/TipLink";
import { useAppStore } from "./store/app-store";
import { useProjectStore } from "./store/project-store";
import { removeHighlight } from "./components/select-and-edit/utils";
import Sidebar from "./components/sidebar/Sidebar";
import IconStrip from "./components/sidebar/IconStrip";
import HistoryDisplay from "./components/history/HistoryDisplay";
import PreviewPane from "./components/preview/PreviewPane";
import StartPane from "./components/start-pane/StartPane";
import SettingsTab from "./components/settings/SettingsTab";
import { Commit } from "./components/commits/types";
import { createCommit } from "./components/commits/utils";
import {
  buildContinuationPrompt,
  findContinuationCandidate,
  hasReferenceMediaForContinuation,
} from "./lib/validated-loop";

const DEFAULT_CODE_GENERATION_MODEL =
  CodeGenerationModel.GEMINI_3_1_PRO_PREVIEW_HIGH;
const PREVIOUS_DEFAULT_CODE_GENERATION_MODELS = new Set([
  CodeGenerationModel.CLAUDE_4_5_OPUS_2025_11_01,
  CodeGenerationModel.GEMINI_3_FLASH_PREVIEW_MINIMAL,
]);
const DEFAULT_MODEL_MIGRATION_KEY = "default-code-generation-model-migrated-v4";
const VALIDATED_LOOP_MAX_ITERATIONS = 10;
const PREPARE_VIDEO_TIMEOUT_MS = 15_000;

async function prepareVideoForGeneration(videoDataUrl: string): Promise<string> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    PREPARE_VIDEO_TIMEOUT_MS
  );

  const response = await fetch(`${HTTP_BACKEND_URL}/prepare-video`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ videoDataUrl }),
    signal: controller.signal,
  });
  window.clearTimeout(timeoutId);

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(
      errorPayload?.detail || "Video preprocessing failed before generation."
    );
  }

  const payload = (await response.json()) as { videoDataUrl: string };
  return payload.videoDataUrl;
}

function getPromptInputMode(prompt: {
  images: string[];
  videos?: string[];
}): "image" | "video" | "text" {
  if ((prompt.videos?.length || 0) > 0) {
    return "video";
  }
  if (prompt.images.length > 0) {
    return "image";
  }
  return "text";
}

function App() {
  const {
    // Inputs
    inputMode,
    setInputMode,
    referenceImages,
    setReferenceImages,
    initialPrompt,
    setInitialPrompt,
    upsertPromptAssets,
    resetPromptAssets,

    head,
    commits,
    addCommit,
    removeCommit,
    setHead,
    appendCommitCode,
    setCommitCode,
    resetCommits,
    resetHead,
    updateVariantStatus,
    setVariantResumableStop,
    setVariantArtifactLocation,
    resizeVariants,
    setVariantModels,
    appendVariantHistoryMessage,
    startAgentEvent,
    appendAgentEventContent,
    finishAgentEvent,
    collapseCommitsToSingleVariant,

    // Outputs
    appendExecutionConsole,
    resetExecutionConsoles,
  } = useProjectStore();

  const {
    disableInSelectAndEditMode,
    setUpdateInstruction,
    updateImages,
    setUpdateImages,
    updateVideos,
    setUpdateVideos,
    appState,
    setAppState,
    selectedElement,
    setSelectedElement,
  } = useAppStore();

  // Settings
  const [settings, setSettings] = usePersistedState<Settings>(
    {
      openAiApiKey: null,
      openAiBaseURL: null,
      anthropicApiKey: null,
      geminiApiKey: null,
      screenshotOneApiKey: null,
      isImageGenerationEnabled: true,
      editorTheme: EditorTheme.COBALT,
      generatedCodeConfig: DEFAULT_STACK,
      codeGenerationModel: DEFAULT_CODE_GENERATION_MODEL,
      // Only relevant for hosted version
      isTermOfServiceAccepted: false,
    },
    "setting"
  );
  const [appTheme, setAppTheme] = usePersistedState<AppTheme>(
    AppTheme.SYSTEM,
    "app-theme"
  );

  const wsRef = useRef<WebSocket>(null);
  const lastThinkingEventIdRef = useRef<Record<number, string>>({});
  const lastAssistantEventIdRef = useRef<Record<number, string>>({});
  const lastToolEventIdRef = useRef<Record<number, string>>({});
  const isClearingProjectRef = useRef(false);

  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [mobilePane, setMobilePane] = useState<"preview" | "chat">("preview");
  const showSelectAndEditFeature =
    settings.generatedCodeConfig === Stack.HTML_TAILWIND ||
    settings.generatedCodeConfig === Stack.HTML_CSS;

  // Indicate coding state using the browser tab's favicon and title
  useBrowserTabIndicator(appState === AppState.CODING);

  // When the user already has the settings in local storage, newly added keys
  // do not get added to the settings so if it's falsy, we populate it with the default
  // value
  useEffect(() => {
    if (!settings.generatedCodeConfig) {
      setSettings((prev) => ({
        ...prev,
        generatedCodeConfig: DEFAULT_STACK,
      }));
    }
  }, [settings.generatedCodeConfig, setSettings]);

  useEffect(() => {
    if (window.localStorage.getItem(DEFAULT_MODEL_MIGRATION_KEY)) {
      return;
    }

    if (
      !settings.codeGenerationModel ||
      PREVIOUS_DEFAULT_CODE_GENERATION_MODELS.has(settings.codeGenerationModel)
    ) {
      setSettings((prev) => ({
        ...prev,
        codeGenerationModel: DEFAULT_CODE_GENERATION_MODEL,
      }));
    }

    window.localStorage.setItem(DEFAULT_MODEL_MIGRATION_KEY, "true");
  }, [settings.codeGenerationModel, setSettings]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const isDark =
        appTheme === AppTheme.DARK ||
        (appTheme === AppTheme.SYSTEM && mediaQuery.matches);
      document.documentElement.classList.toggle("dark", isDark);
      document.body.classList.toggle("dark", isDark);
    };

    applyTheme();

    if (appTheme !== AppTheme.SYSTEM) {
      return;
    }

    const onChange = () => applyTheme();
    mediaQuery.addEventListener("change", onChange);

    return () => {
      mediaQuery.removeEventListener("change", onChange);
    };
  }, [appTheme]);

  const getAssetsById = () => useProjectStore.getState().assetsById;

  // Functions
  const reset = () => {
    setAppState(AppState.INITIAL);
    setUpdateInstruction("");
    setUpdateImages([]);
    setUpdateVideos([]);
    disableInSelectAndEditMode();
    resetExecutionConsoles();

    resetCommits();
    resetHead();
    resetPromptAssets();

    // Inputs
    setInputMode("image");
    setReferenceImages([]);
    setInitialPrompt("");
  };

  useEffect(() => {
    if (appState !== AppState.INITIAL) {
      return;
    }

    if (head && commits[head]) {
      setAppState(AppState.CODE_READY);
    }
  }, [appState, commits, head, setAppState]);

  useEffect(() => {
    if (Object.values(commits).some((commit) => commit.variants.length > 1)) {
      collapseCommitsToSingleVariant();
    }
  }, [collapseCommitsToSingleVariant, commits]);

  const regenerate = () => {
    if (head === null) {
      toast.error(
        "No current version set. Please contact support via chat or Github."
      );
      throw new Error("Regenerate called with no head");
    }

    // Retrieve the previous command
    const currentCommit = commits[head];
    if (currentCommit.type !== "ai_create") {
      toast.error("Only the first version can be regenerated.");
      return;
    }

    // Re-run the create
    if (inputMode === "image" || inputMode === "video") {
      doCreate(referenceImages, inputMode);
    } else {
      // TODO: Fix this
      doCreateFromText(initialPrompt);
    }
  };

  // Used when the user cancels the code generation
  const cancelCodeGeneration = () => {
    wsRef.current?.close?.(USER_CLOSE_WEB_SOCKET_CODE);
  };

  const clearProject = () => {
    const hadInFlightRequest = appState === AppState.CODING && Boolean(wsRef.current);
    isClearingProjectRef.current = hadInFlightRequest;
    wsRef.current?.close?.(USER_CLOSE_WEB_SOCKET_CODE);
    reset();
    setIsHistoryOpen(false);
    setIsSettingsOpen(false);
    setMobilePane("preview");
    if (!hadInFlightRequest) {
      isClearingProjectRef.current = false;
    }
  };

  // Used for user-initiated cancellation and failed edit rollbacks
  const cancelCodeGenerationAndReset = (commit: Commit) => {
    // When the current commit is the first version, reset the entire app state
    if (commit.type === "ai_create") {
      reset();
    } else {
      // Otherwise, remove current commit from commits
      removeCommit(commit.hash);

      // Revert to parent commit
      const parentCommitHash = commit.parentHash;
      if (parentCommitHash) {
        setHead(parentCommitHash);
      } else {
        throw new Error("Parent commit not found");
      }

      setAppState(AppState.CODE_READY);
    }
  };

  function doGenerateCode(params: GenerationRequest) {
    // Reset the execution console
    resetExecutionConsoles();

    // Set the app state to coding during generation
    setAppState(AppState.CODING);

    const { variantHistory, ...requestParams } = params;
    const requestedOrchestrationMode = requestParams.orchestrationMode;
    const shouldUseValidatedLoop =
      requestedOrchestrationMode === "validated_loop" ||
      (
        requestedOrchestrationMode === undefined &&
        (requestParams.inputMode === "image" || requestParams.inputMode === "video")
      );
    const validatedLoopParams =
      requestedOrchestrationMode !== undefined
        ? {}
        : shouldUseValidatedLoop
      ? {
          orchestrationMode: "validated_loop" as const,
          maxValidationIterations: VALIDATED_LOOP_MAX_ITERATIONS,
        }
      : {};

    // Merge settings with params
    const updatedParams = {
      ...requestParams,
      ...validatedLoopParams,
      ...settings,
    };

    // The app now uses a single generation flow across all request types.
    const initialVariantCount = 1;
    const baseCommitObject = {
      inputMode: requestParams.inputMode,
      variants: Array(initialVariantCount)
        .fill(null)
        .map(() => ({
          code: "",
          history: cloneVariantHistory(variantHistory),
        })),
    };

    const commitInputObject =
      requestParams.generationType === "create"
        ? {
            ...baseCommitObject,
            type: "ai_create" as const,
            parentHash: null,
            inputs: requestParams.prompt,
          }
        : {
            ...baseCommitObject,
            type: "ai_edit" as const,
            parentHash: head,
            inputs: requestParams.prompt,
          };

    // Create a new commit and set it as the head
    const commit = createCommit(commitInputObject);
    addCommit(commit);
    setHead(commit.hash);

    if (
      requestParams.generationType === "update" &&
      requestParams.fileState?.content?.trim()
    ) {
      const bootstrapEventId = `bootstrap-status-${Date.now()}`;
      startAgentEvent(commit.hash, 0, {
        id: bootstrapEventId,
        type: "thinking",
        status: "complete",
        source: "supervisor",
        title: "Supervisor status",
        content: "Loaded the current version as the starting point for this update.",
        startedAt: Date.now(),
        endedAt: Date.now(),
      });
    }

    lastThinkingEventIdRef.current = {};
    lastAssistantEventIdRef.current = {};
    lastToolEventIdRef.current = {};
    const finishThinkingEvent = (variantIndex: number, status: "complete" | "error") => {
      const eventId = lastThinkingEventIdRef.current[variantIndex];
      if (!eventId) return;
      finishAgentEvent(commit.hash, variantIndex, eventId, {
        status,
        endedAt: Date.now(),
      });
      delete lastThinkingEventIdRef.current[variantIndex];
    };

    const finishAssistantEvent = (variantIndex: number, status: "complete" | "error") => {
      const eventId = lastAssistantEventIdRef.current[variantIndex];
      if (!eventId) return;
      finishAgentEvent(commit.hash, variantIndex, eventId, {
        status,
        endedAt: Date.now(),
      });
      delete lastAssistantEventIdRef.current[variantIndex];
    };

    const finishToolEvent = (variantIndex: number, status: "complete" | "error") => {
      const eventId = lastToolEventIdRef.current[variantIndex];
      if (!eventId) return;
      finishAgentEvent(commit.hash, variantIndex, eventId, {
        status,
        endedAt: Date.now(),
      });
      delete lastToolEventIdRef.current[variantIndex];
    };

    const finishInFlightEvents = (status: "complete" | "error") => {
      Object.keys(lastThinkingEventIdRef.current).forEach((key) => {
        finishThinkingEvent(Number(key), status);
      });
      Object.keys(lastAssistantEventIdRef.current).forEach((key) => {
        finishAssistantEvent(Number(key), status);
      });
      Object.keys(lastToolEventIdRef.current).forEach((key) => {
        finishToolEvent(Number(key), status);
      });
    };

    generateCode(wsRef, updatedParams, {
      onChange: (token, variantIndex) => {
        appendCommitCode(commit.hash, variantIndex, token);
      },
      onSetCode: (code, variantIndex) => {
        setCommitCode(commit.hash, variantIndex, code);
      },
      onStatusUpdate: (line, variantIndex, meta) => {
        appendExecutionConsole(variantIndex, line);
        if (meta?.artifactPath || meta?.runDir) {
          setVariantArtifactLocation(
            commit.hash,
            variantIndex,
            meta.artifactPath,
            meta.runDir
          );
        }
        const statusEventId = `status-${variantIndex}-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2, 8)}`;
        startAgentEvent(commit.hash, variantIndex, {
          id: statusEventId,
          type: "thinking",
          status: "complete",
          source: "supervisor",
          title: "Supervisor status",
          content: line,
          startedAt: Date.now(),
          endedAt: Date.now(),
        });
      },
      onVariantComplete: (variantIndex, meta) => {
        console.log(`Variant ${variantIndex} complete event received`);
        updateVariantStatus(commit.hash, variantIndex, "complete");
        setVariantResumableStop(commit.hash, variantIndex, undefined);
        if (meta?.artifactPath || meta?.runDir) {
          setVariantArtifactLocation(
            commit.hash,
            variantIndex,
            meta?.artifactPath,
            meta?.runDir
          );
        }
        const currentCode =
          useProjectStore.getState().commits[commit.hash]?.variants[variantIndex]
            ?.code || "";
        if (currentCode.trim().length > 0) {
          appendVariantHistoryMessage(
            commit.hash,
            variantIndex,
            buildAssistantHistoryMessage(currentCode)
          );
        }
        finishThinkingEvent(variantIndex, "complete");
        finishAssistantEvent(variantIndex, "complete");
        finishToolEvent(variantIndex, "complete");
        if (commit.type === "ai_edit") {
          const {
            updateInstruction: currentInstruction,
            updateImages: currentImages,
          } = useAppStore.getState();
          const instructionUnchanged =
            currentInstruction === commit.inputs.text;
          const imagesUnchanged =
            currentImages.length === commit.inputs.images.length &&
            currentImages.every(
              (image, index) => image === commit.inputs.images[index]
            );

          // This conditional clear handles three UX scenarios:
          // 1) All variants fail: no completion event, so keep prompt/images for retry.
          // 2) A variant completes and user has typed/changed images: do not clear.
          // 3) A variant completes and user has not changed draft: clear for next edit.
          if (instructionUnchanged && imagesUnchanged) {
            setUpdateInstruction("");
            setUpdateImages([]);
            setUpdateVideos([]);
          }
        }
      },
      onVariantError: (variantIndex, error, meta) => {
        console.error(`Error in variant ${variantIndex}:`, error);
        const isResumableStop =
          meta?.canContinue === true && meta.stopReason === "max_iterations";
        updateVariantStatus(
          commit.hash,
          variantIndex,
          isResumableStop ? "paused" : "error",
          isResumableStop ? undefined : error
        );
        setVariantResumableStop(
          commit.hash,
          variantIndex,
          isResumableStop
            ? {
                stopReason: meta?.stopReason,
                iterationsCompleted: meta?.iterationsCompleted,
                maxIterations: meta?.maxIterations,
                canContinue: meta?.canContinue,
              }
            : undefined
        );
        if (meta?.artifactPath || meta?.runDir) {
          setVariantArtifactLocation(
            commit.hash,
            variantIndex,
            meta?.artifactPath,
            meta?.runDir
          );
        }
        const terminalEventStatus = isResumableStop ? "complete" : "error";
        finishThinkingEvent(variantIndex, terminalEventStatus);
        finishAssistantEvent(variantIndex, terminalEventStatus);
        finishToolEvent(variantIndex, terminalEventStatus);
      },
      onVariantCount: (count) => {
        console.log(`Backend is using ${count} variants`);
        resizeVariants(commit.hash, 1);
      },
      onVariantModels: (models) => {
        setVariantModels(commit.hash, models);
      },
      onThinking: (content, variantIndex, eventId, meta) => {
        if (!eventId) return;
        const previousThinking = lastThinkingEventIdRef.current[variantIndex];
        if (previousThinking && previousThinking !== eventId) {
          finishThinkingEvent(variantIndex, "complete");
        }
        lastThinkingEventIdRef.current[variantIndex] = eventId;
        startAgentEvent(commit.hash, variantIndex, {
          id: eventId,
          type: "thinking",
          status: "running",
          source: meta?.source === "supervisor" ? "supervisor" : "executor",
          title: typeof meta?.title === "string" ? meta.title : undefined,
          startedAt: Date.now(),
        });
        appendAgentEventContent(commit.hash, variantIndex, eventId, content);
      },
      onAssistant: (content, variantIndex, eventId, meta) => {
        if (!eventId) return;
        const lastThinking = lastThinkingEventIdRef.current[variantIndex];
        if (lastThinking && lastThinking !== eventId) {
          finishThinkingEvent(variantIndex, "complete");
        }
        const previousAssistant = lastAssistantEventIdRef.current[variantIndex];
        if (previousAssistant && previousAssistant !== eventId) {
          finishAssistantEvent(variantIndex, "complete");
        }
        lastAssistantEventIdRef.current[variantIndex] = eventId;
        startAgentEvent(commit.hash, variantIndex, {
          id: eventId,
          type: "assistant",
          status: "running",
          source: meta?.source === "supervisor" ? "supervisor" : "executor",
          title: typeof meta?.title === "string" ? meta.title : undefined,
          startedAt: Date.now(),
        });
        appendAgentEventContent(commit.hash, variantIndex, eventId, content);
      },
      onToolStart: (data, variantIndex, eventId) => {
        if (!eventId) return;
        const lastThinking = lastThinkingEventIdRef.current[variantIndex];
        if (lastThinking && lastThinking !== eventId) {
          finishThinkingEvent(variantIndex, "complete");
        }
        const lastAssistant = lastAssistantEventIdRef.current[variantIndex];
        if (lastAssistant && lastAssistant !== eventId) {
          finishAssistantEvent(variantIndex, "complete");
        }
        startAgentEvent(commit.hash, variantIndex, {
          id: eventId,
          type: "tool",
          status: "running",
          source: data?.source === "supervisor" ? "supervisor" : "executor",
          title: typeof data?.title === "string" ? data.title : undefined,
          toolName: data?.name,
          input: data?.input,
          startedAt: Date.now(),
        });
        lastToolEventIdRef.current[variantIndex] = eventId;
      },
      onToolResult: (data, variantIndex, eventId) => {
        if (!eventId) return;
        finishAgentEvent(commit.hash, variantIndex, eventId, {
          status: data?.ok === false ? "error" : "complete",
          output: data?.output,
          endedAt: Date.now(),
        });
        if (lastToolEventIdRef.current[variantIndex] === eventId) {
          delete lastToolEventIdRef.current[variantIndex];
        }
      },
      onCancel: (reason, errorMessage) => {
        if (isClearingProjectRef.current) {
          finishInFlightEvents("complete");
          isClearingProjectRef.current = false;
          return;
        }
        // Close any running agent events when the socket ends without per-event
        // terminal messages, otherwise they remain stuck in "running" state.
        finishInFlightEvents(reason === "request_failed" ? "error" : "complete");

        if (reason === "request_failed" && commit.type === "ai_create") {
          const latestCreateCommit = useProjectStore.getState().commits[commit.hash];
          latestCreateCommit?.variants.forEach((variant, variantIndex) => {
            if (variant.status === "generating") {
              updateVariantStatus(
                commit.hash,
                variantIndex,
                "error",
                errorMessage || "Generation failed. Please retry."
              );
            }
          });
          setAppState(AppState.CODE_READY);
          return;
        }

        cancelCodeGenerationAndReset(commit);
      },
      onComplete: () => {
        if (isClearingProjectRef.current) {
          finishInFlightEvents("complete");
          isClearingProjectRef.current = false;
          return;
        }
        finishInFlightEvents("complete");
        const latestCommit = useProjectStore.getState().commits[commit.hash];
        if (latestCommit?.type !== "code_create") {
          latestCommit.variants.forEach((variant, variantIndex) => {
            if (variant.status === "generating" && variant.code.trim()) {
              updateVariantStatus(commit.hash, variantIndex, "complete");
            }
          });
        }
        setAppState(AppState.CODE_READY);
      },
    });
  }

  // Initial version creation
  async function doCreate(
    referenceImages: string[],
    inputMode: "image" | "video",
    textPrompt: string = "",
    referenceUrl?: string
  ) {
    // Reset any existing state
    reset();

    let media = inputMode === "video" ? [referenceImages[0]] : referenceImages;

    if (inputMode === "video" && media[0]) {
      const toastId = "prepare-video";
      toast.loading("Preparing video for Gemini.", { id: toastId });
      try {
        media = [await prepareVideoForGeneration(media[0])];
        toast.dismiss(toastId);
      } catch (error) {
        console.warn(
          "Frontend video preprocessing failed; falling back to backend normalization during generation.",
          error
        );
        toast.dismiss(toastId);
        toast("Using backend-side video normalization instead.", {
          id: toastId,
        });
      }
    }

    // Set the input states
    setReferenceImages(media);
    setInputMode(inputMode);

    // Kick off the code generation
    if (media.length > 0) {
      const imageAssetIds =
        inputMode === "image"
          ? registerAssetIds(
              "image",
              media,
              getAssetsById,
              upsertPromptAssets,
              nanoid
            )
          : [];
      const videoAssetIds =
        inputMode === "video"
          ? registerAssetIds(
              "video",
              media,
              getAssetsById,
              upsertPromptAssets,
              nanoid
            )
          : [];
      const variantHistory = [
        buildUserHistoryMessage(textPrompt, imageAssetIds, videoAssetIds),
      ];
      doGenerateCode({
        generationType: "create",
        inputMode,
        prompt: {
          text: textPrompt,
          images: inputMode === "image" ? media : [],
          videos: inputMode === "video" ? media : [],
          referenceUrl,
        },
        variantHistory,
      });
    }
  }

  function doCreateFromText(text: string) {
    // Reset any existing state
    reset();

    setInputMode("text");
    setInitialPrompt(text);
    doGenerateCode({
      generationType: "create",
      inputMode: "text",
      prompt: { text, images: [], videos: [] },
      variantHistory: [buildUserHistoryMessage(text)],
    });
  }

  // Subsequent updates
  async function doUpdate(updateInstruction: string) {
    const hasUpdateMedia = updateImages.length > 0 || updateVideos.length > 0;
    const normalizedInstruction = updateInstruction.trim();

    if (normalizedInstruction === "" && !hasUpdateMedia) {
      toast.error("Add instructions or attach reference media for the update.");
      return;
    }

    if (head === null) {
      toast.error(
        "No current version set. Contact support or open a Github issue."
      );
      throw new Error("Update called with no head");
    }

    const currentCommit = commits[head];
    const currentCode =
      currentCommit?.variants[currentCommit.selectedVariantIndex]?.code || "";
    const optionCodes = currentCode ? [currentCode] : [];
    const updateInputMode =
      updateVideos.length > 0
        ? "video"
        : updateImages.length > 0
          ? "image"
          : inputMode;

    const fallbackMediaInstruction =
      updateVideos.length > 0
        ? "Use the attached reference video to continue improving the current implementation."
        : updateImages.length > 0
          ? "Use the attached reference media to continue improving the current implementation."
          : "";

    const promptInstruction =
      normalizedInstruction || fallbackMediaInstruction;

    let modifiedUpdateInstruction = promptInstruction;
    let selectedElementHtml: string | undefined;

    // Send in a reference to the selected element if it exists
    if (selectedElement) {
      const elementHtml = removeHighlight(selectedElement).outerHTML;
      selectedElementHtml = elementHtml;
      modifiedUpdateInstruction =
        promptInstruction +
        " referring to this element specifically: " +
        elementHtml;
      setSelectedElement(null);
    }

    let preparedUpdateVideos = updateVideos;
    if (updateInputMode === "video" && updateVideos[0]) {
      const toastId = "prepare-update-video";
      toast.loading("Preparing video for Gemini.", { id: toastId });
      try {
        preparedUpdateVideos = [await prepareVideoForGeneration(updateVideos[0])];
        toast.dismiss(toastId);
      } catch (error) {
        console.warn(
          "Frontend video preprocessing failed for update flow; falling back to backend normalization during generation.",
          error
        );
        toast.dismiss(toastId);
        toast("Using backend-side video normalization instead.", {
          id: toastId,
        });
      }
    }

    const selectedVariant = currentCommit.variants[currentCommit.selectedVariantIndex];
    const baseVariantHistory = selectedVariant.history;
    const updateImageAssetIds = registerAssetIds(
      "image",
      updateImages,
      getAssetsById,
      upsertPromptAssets,
      nanoid
    );
    const updateVideoAssetIds = registerAssetIds(
      "video",
      preparedUpdateVideos,
      getAssetsById,
      upsertPromptAssets,
      nanoid
    );
    const updatedVariantHistory = [
      ...cloneVariantHistory(baseVariantHistory),
      buildUserHistoryMessage(
        modifiedUpdateInstruction,
        updateImageAssetIds,
        updateVideoAssetIds
      ),
    ];
    const shouldBootstrapFromFileState =
      baseVariantHistory.length === 0 && currentCode.trim().length > 0;
    const updatedHistory = shouldBootstrapFromFileState
      ? []
      : toRequestHistory(updatedVariantHistory, getAssetsById);

    doGenerateCode({
      generationType: "update",
      inputMode: updateInputMode,
      prompt: {
        text: promptInstruction,
        images: updateImages,
        videos: preparedUpdateVideos,
        selectedElementHtml,
      },
      history: updatedHistory,
      optionCodes,
      variantHistory: updatedVariantHistory,
      fileState: currentCode
        ? {
            path: "index.html",
            content: currentCode,
          }
        : undefined,
    });
  }

  function continueValidatedLoop() {
    if (head === null) {
      toast.error("No active generation found to continue.");
      return;
    }

    const allCommits = useProjectStore.getState().commits;
    const latestCommit = allCommits[head];
    const continuationCandidate = findContinuationCandidate(latestCommit, allCommits);
    const selectedVariantIndex =
      continuationCandidate?.issueIndex ?? latestCommit?.selectedVariantIndex ?? 0;
    const currentCode = continuationCandidate?.baseCode || "";
    const hasReferenceMedia = hasReferenceMediaForContinuation(
      latestCommit,
      continuationCandidate?.savedRunDir
    );
    const resumeInputMode =
      latestCommit?.inputMode ?? getPromptInputMode(latestCommit?.inputs || { images: [], videos: [] });

    if (
      !latestCommit ||
      latestCommit.type === "code_create" ||
      !continuationCandidate ||
      !currentCode.trim()
    ) {
      toast.error("Could not continue from the current generated code.");
      return;
    }

    const shouldUseSavedReferenceRunDir = Boolean(continuationCandidate.savedRunDir);
    const continuationPrompt = buildContinuationPrompt(latestCommit, {
      useSavedReferenceRunDir: shouldUseSavedReferenceRunDir,
    });

    setVariantResumableStop(latestCommit.hash, selectedVariantIndex, undefined);
    const continuationRequest = {
      generationType: "update" as const,
      inputMode: resumeInputMode,
      prompt: continuationPrompt,
      variantHistory: cloneVariantHistory(continuationCandidate.history),
      fileState: {
        path: "index.html",
        content: currentCode,
      },
    };

    if (continuationCandidate.mode === "validated_loop" && hasReferenceMedia) {
      doGenerateCode({
        ...continuationRequest,
        orchestrationMode: "validated_loop",
        validatedLoopReferenceRunDir: continuationCandidate.savedRunDir,
        validatedLoopDesignSystemMode: continuationCandidate.savedRunDir
          ? "reuse_if_available"
          : "generate",
        validatedLoopDesignSystemRunDir: continuationCandidate.savedRunDir,
      });
      return;
    }

    if (continuationCandidate.mode === "validated_loop" && !hasReferenceMedia) {
      toast("Original reference media is unavailable. Continuing from current code without the supervisor.", {
        id: "continue-without-supervisor",
      });
    }

    const shouldBootstrapFromFileState =
      continuationCandidate.history.length === 0 && currentCode.trim().length > 0;
    const history = shouldBootstrapFromFileState
      ? []
      : toRequestHistory(continuationCandidate.history, getAssetsById);

    doGenerateCode({
      ...continuationRequest,
      inputMode: hasReferenceMedia ? resumeInputMode : "text",
      orchestrationMode: "standard",
      history,
      optionCodes: currentCode ? [currentCode] : [],
    });
  }

  const handleTermDialogOpenChange = (open: boolean) => {
    setSettings((s) => ({
      ...s,
      isTermOfServiceAccepted: !open,
    }));
  };

  function setStack(stack: Stack) {
    setSettings((prev) => ({
      ...prev,
      generatedCodeConfig: stack,
    }));
  }

  function importFromCode(code: string, stack: Stack) {
    // Reset any existing state
    reset();

    // Set up this project
    setStack(stack);

    // Create a new commit and set it as the head
    const commit = createCommit({
      type: "code_create",
      parentHash: null,
      variants: [{ code, history: [] }],
      inputs: null,
    });
    addCommit(commit);
    setHead(commit.hash);

    // Set the app state
    setAppState(AppState.CODE_READY);
  }

  const showContentPanel =
    appState === AppState.CODING ||
    appState === AppState.CODE_READY ||
    isHistoryOpen;
  const isCodingOrReady =
    appState === AppState.CODING || appState === AppState.CODE_READY;
  const showMobileChatPane = showContentPanel && mobilePane === "chat";

  return (
    <div
      className={`dark:bg-black dark:text-white ${
        appState === AppState.CODING || appState === AppState.CODE_READY
          ? "flex h-dvh flex-col overflow-hidden lg:block lg:h-screen"
          : "min-h-screen"
      }`}
    >
      {IS_RUNNING_ON_CLOUD && <PicoBadge />}
      {IS_RUNNING_ON_CLOUD && (
        <TermsOfServiceDialog
          open={!settings.isTermOfServiceAccepted}
          onOpenChange={handleTermDialogOpenChange}
        />
      )}

      {/* Icon strip - always visible */}
      <div
        className="sticky top-0 z-50 lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-16 lg:flex-col"
      >
        <IconStrip
          isHistoryOpen={isHistoryOpen}
          isEditorOpen={!isHistoryOpen && !isSettingsOpen}
          isSettingsOpen={isSettingsOpen}
          showHistory={isCodingOrReady}
          showEditor={isCodingOrReady}
          onToggleHistory={() => {
            setIsHistoryOpen((prev) => !prev);
            setIsSettingsOpen(false);
            setMobilePane("chat");
          }}
          onToggleEditor={() => {
            setIsHistoryOpen(false);
            setIsSettingsOpen(false);
            setMobilePane("preview");
          }}
          onLogoClick={() => {
            setIsHistoryOpen(false);
            setIsSettingsOpen(false);
            setMobilePane("preview");
          }}
          onNewProject={() => {
            clearProject();
          }}
          onOpenSettings={() => {
            setIsSettingsOpen(true);
            setIsHistoryOpen(false);
          }}
        />
      </div>

      {isCodingOrReady && !isSettingsOpen && (
        <div className="border-b border-gray-200 bg-white px-4 py-2 dark:border-zinc-800 dark:bg-zinc-950 lg:hidden">
          <div className="grid grid-cols-2 rounded-xl bg-gray-100 p-1 dark:bg-zinc-800">
            <button
              onClick={() => {
                setIsHistoryOpen(false);
                setMobilePane("preview");
              }}
              className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                mobilePane === "preview"
                  ? "bg-white text-gray-900 shadow-sm dark:bg-zinc-700 dark:text-white"
                  : "text-gray-500 dark:text-zinc-400"
              }`}
            >
              Preview
            </button>
            <button
              onClick={() => setMobilePane("chat")}
              className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                mobilePane === "chat"
                  ? "bg-white text-gray-900 shadow-sm dark:bg-zinc-700 dark:text-white"
                  : "text-gray-500 dark:text-zinc-400"
              }`}
            >
              Chat
            </button>
          </div>
        </div>
      )}

      {/* Content panel - shows sidebar, history, or editor */}
      {showContentPanel && !isSettingsOpen && (
        <div
          className={`border-b border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 dark:text-white lg:fixed lg:inset-y-0 lg:left-16 lg:z-40 lg:flex lg:w-[calc(28rem-4rem)] lg:flex-col lg:border-b-0 lg:border-r ${
            showMobileChatPane ? "block" : "hidden lg:flex"
          }`}
        >
            {isHistoryOpen ? (
              <div className="flex-1 overflow-y-auto sidebar-scrollbar-stable px-4">
                <div className="mt-3">
                  <div className="flex items-center justify-between mb-3 px-1">
                    <h2 className="text-xs font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500">Versions</h2>
                    <button
                      onClick={() => setIsHistoryOpen(false)}
                      className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                    >
                      <LuChevronLeft className="w-3.5 h-3.5" />
                      Back to editor
                    </button>
                  </div>
                  <HistoryDisplay />
                </div>
              </div>
            ) : (
              <>
                {IS_RUNNING_ON_CLOUD && !settings.openAiApiKey && (
                  <div className="px-6 mt-4">
                    <OnboardingNote />
                  </div>
                )}

                {(appState === AppState.CODING ||
                  appState === AppState.CODE_READY) && (
                  <Sidebar
                    showSelectAndEditFeature={showSelectAndEditFeature}
                    doUpdate={doUpdate}
                    continueValidatedLoop={continueValidatedLoop}
                    regenerate={regenerate}
                    cancelCodeGeneration={cancelCodeGeneration}
                    onClearVersions={clearProject}
                    onOpenVersions={() => {
                      setIsHistoryOpen(true);
                      setMobilePane("chat");
                    }}
                  />
                )}
              </>
            )}
        </div>
      )}

      <main
        className={`${
          isSettingsOpen
            ? "flex flex-1 min-h-0 flex-col lg:h-full lg:pl-16"
            : showContentPanel
              ? "flex flex-1 min-h-0 flex-col lg:h-full lg:pl-[28rem]"
              : "lg:pl-16"
        } ${isCodingOrReady && !isSettingsOpen && mobilePane === "chat" ? "hidden lg:flex" : ""}`}
      >
        {isSettingsOpen ? (
          <SettingsTab
            settings={settings}
            setSettings={setSettings}
            appTheme={appTheme}
            setAppTheme={setAppTheme}
          />
        ) : (
          <>
            {appState === AppState.INITIAL && (
              <StartPane
                doCreate={doCreate}
                doCreateFromText={doCreateFromText}
                importFromCode={importFromCode}
                settings={settings}
                setSettings={setSettings}
              />
            )}

            {isCodingOrReady && (
              <PreviewPane
                settings={settings}
                onOpenVersions={() => {
                  setIsHistoryOpen(true);
                  setMobilePane("chat");
                }}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default App;

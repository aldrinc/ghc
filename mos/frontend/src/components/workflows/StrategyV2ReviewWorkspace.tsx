import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ChevronRight, Loader2 } from "lucide-react";
import { useApiClient, type ApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { MarkdownViewer } from "@/components/ui/MarkdownViewer";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { ActivityLog, ResearchArtifactRef, StrategyV2State } from "@/types/common";

export type StrategyV2PendingSignal =
  | "strategy_v2_proceed_research"
  | "strategy_v2_confirm_competitor_assets"
  | "strategy_v2_select_angle"
  | "strategy_v2_select_ump_ums"
  | "strategy_v2_select_offer_winner"
  | "strategy_v2_approve_final_copy";

export type StrategyV2Candidate = {
  id: string;
  label: string;
  assetRef?: string;
  raw?: Record<string, unknown>;
};

type StrategyV2ReviewWorkspaceProps = {
  workflowId?: string;
  runStatus: string;
  pendingSignal: StrategyV2PendingSignal | null;
  pendingPayload: Record<string, unknown>;
  strategyState?: StrategyV2State | null;
  candidates: StrategyV2Candidate[];
  candidateIds: string[];
  researchArtifacts: ResearchArtifactRef[];
  stepSummaries: Record<string, string>;
  logs: ActivityLog[];
  disabled: boolean;
  isSubmitting: boolean;
  onSubmitSignal: (signalPath: string, body: Record<string, unknown>) => void;
};

type ReviewFileKind = "research" | "artifact" | "candidate" | "copy_field";
type CopyField = "headline" | "body_markdown" | "presell_markdown" | "sales_page_markdown" | "quality_report";

type ReviewFile = {
  id: string;
  title: string;
  subtitle?: string;
  kind: ReviewFileKind;
  required: boolean;
  stepKey?: string;
  artifactId?: string;
  candidateId?: string;
  candidateRaw?: Record<string, unknown>;
  copyField?: CopyField;
  missingReason?: string;
};

type FileLoadStatus = "idle" | "loading" | "loaded" | "error";
type FileRuntimeState = {
  status: FileLoadStatus;
  reviewed: boolean;
  content: string;
  error: string;
};

const GATE_SEQUENCE: StrategyV2PendingSignal[] = [
  "strategy_v2_proceed_research",
  "strategy_v2_confirm_competitor_assets",
  "strategy_v2_select_angle",
  "strategy_v2_select_ump_ums",
  "strategy_v2_select_offer_winner",
  "strategy_v2_approve_final_copy",
];

const OPERATOR_NOTE_MIN_LENGTH = 20;
const FOUNDATIONAL_DOC_SPECS = [
  {
    stepSuffix: "01",
    title: "Competitor Research",
    fallbackSubtitle: "Foundational Step 01 full markdown",
  },
  {
    stepSuffix: "03",
    title: "Deep Research Meta-Prompt",
    fallbackSubtitle: "Foundational Step 03 full markdown",
  },
  {
    stepSuffix: "04",
    title: "Deep Research Corpus",
    fallbackSubtitle: "Foundational Step 04 full markdown",
  },
  {
    stepSuffix: "06",
    title: "Avatar Brief",
    fallbackSubtitle: "Foundational Step 06 full markdown",
  },
] as const;

function strategyV2SignalPath(signal: StrategyV2PendingSignal): string {
  if (signal === "strategy_v2_proceed_research") return "strategy-v2/proceed-research";
  if (signal === "strategy_v2_confirm_competitor_assets") return "strategy-v2/confirm-competitor-assets";
  if (signal === "strategy_v2_select_angle") return "strategy-v2/select-angle";
  if (signal === "strategy_v2_select_ump_ums") return "strategy-v2/select-ump-ums";
  if (signal === "strategy_v2_select_offer_winner") return "strategy-v2/select-offer-winner";
  return "strategy-v2/approve-final-copy";
}

function strategyV2SignalLabel(signal: StrategyV2PendingSignal): string {
  if (signal === "strategy_v2_proceed_research") return "Proceed Research";
  if (signal === "strategy_v2_confirm_competitor_assets") return "Confirm Competitor Assets";
  if (signal === "strategy_v2_select_angle") return "Select Angle";
  if (signal === "strategy_v2_select_ump_ums") return "Select UMP/UMS";
  if (signal === "strategy_v2_select_offer_winner") return "Select Offer Winner";
  return "Approve Final Copy";
}

function formatReceiptDate(value?: string): string {
  if (!value) return "Unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseArtifactIdFromRef(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("artifact://")) {
    const parsed = trimmed.slice("artifact://".length).trim();
    return parsed || null;
  }
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(trimmed)) {
    return trimmed;
  }
  return null;
}

function resolveStepPayloadArtifactId(
  artifactRefs: Record<string, unknown>,
  stepKey: string,
): string | null {
  // Fallback state shape: artifact_refs[stepKey] = "artifact://<id>" | "<uuid>"
  const direct = parseArtifactIdFromRef(artifactRefs[stepKey]);
  if (direct) return direct;

  // Live workflow query shape: artifact_refs.step_payload_artifact_ids[stepKey] = "<uuid>"
  const nested = artifactRefs.step_payload_artifact_ids;
  if (isRecord(nested)) {
    const nestedId = parseArtifactIdFromRef(nested[stepKey]);
    if (nestedId) return nestedId;
  }

  // Live workflow query denormalized key: step_payload_v2_02i_artifact_id
  const normalizedStepKey = stepKey.replace(/-/g, "_");
  return parseArtifactIdFromRef(artifactRefs[`step_payload_${normalizedStepKey}_artifact_id`]);
}

function toErrorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object") {
    const maybeError = error as Partial<ApiError> & { message?: unknown };
    if (typeof maybeError.message === "string" && maybeError.message.trim()) {
      return maybeError.message;
    }
  }
  return "Failed to load file content.";
}

function toJsonMarkdown(title: string, value: unknown): string {
  let body = "";
  try {
    body = JSON.stringify(value, null, 2) || "null";
  } catch {
    body = String(value);
  }
  return `# ${title}\n\n\`\`\`json\n${body}\n\`\`\`\n`;
}

function normalizeStepKey(value: string): string {
  return value.trim().toUpperCase();
}

function findResearchArtifactByStepKeys(
  artifacts: ResearchArtifactRef[],
  stepKeys: string[],
): ResearchArtifactRef | undefined {
  if (!stepKeys.length) return undefined;
  const keySet = new Set(stepKeys.map(normalizeStepKey).filter(Boolean));
  return artifacts.find((artifact) => keySet.has(normalizeStepKey(String(artifact.step_key || ""))));
}

function inferCompletedGateCount(currentStage?: string | null, runStatus?: string): number {
  if (runStatus === "completed") return GATE_SEQUENCE.length;
  if (!currentStage) return 0;
  if (currentStage === "completed") return GATE_SEQUENCE.length;
  if (currentStage === "v2-02.foundation") return 0;
  if (currentStage === "v2-02a") return 0;
  if (currentStage === "v2-02b") return 1;
  if (currentStage === "v2-02") return 2;
  if (currentStage === "v2-03") return 2;
  if (currentStage === "v2-04") return 2;
  if (currentStage === "v2-05") return 2;
  if (currentStage === "v2-06") return 2;
  if (currentStage === "v2-03..v2-06") return 2;
  if (currentStage === "v2-07") return 2;
  if (currentStage === "v2-08") return 3;
  if (currentStage === "v2-08b") return 4;
  if (currentStage === "v2-09") return 5;
  if (currentStage === "v2-10") return 5;
  if (currentStage === "v2-11") return 5;
  return 0;
}

type GateReceipt = {
  signal: StrategyV2PendingSignal;
  createdAt: string;
  payload: Record<string, unknown>;
};

function toTimestamp(value: string): number {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
}

function findLatestGateReceipt(logs: ActivityLog[], signal: StrategyV2PendingSignal): GateReceipt | null {
  const candidateLogs = logs
    .filter((log) => log.step === signal && isRecord(log.payload_in))
    .sort((a, b) => toTimestamp(b.created_at) - toTimestamp(a.created_at));
  const latest = candidateLogs[0];
  if (!latest || !isRecord(latest.payload_in)) return null;
  return {
    signal,
    createdAt: latest.created_at,
    payload: latest.payload_in,
  };
}

function resolveCopyPayload(artifactData: unknown): Record<string, unknown> | null {
  if (!isRecord(artifactData)) return null;
  if (isRecord(artifactData.copy_payload)) return artifactData.copy_payload;
  if (isRecord(artifactData.approved_copy)) return artifactData.approved_copy;
  return artifactData;
}

function resolveResearchMarkdown(title: string, value: unknown): string {
  if (typeof value === "string") {
    return value.trim() ? value : `# ${title}\n\n_No content available._`;
  }
  if (isRecord(value)) {
    const payload = isRecord(value.payload) ? value.payload : null;
    const payloadContent = payload?.content;
    if (typeof payloadContent === "string" && payloadContent.trim()) {
      return payloadContent;
    }
    const directContent = value.content;
    if (typeof directContent === "string" && directContent.trim()) {
      return directContent;
    }
  }
  return toJsonMarkdown(title, value);
}

function hasNonEmptyValue(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (isRecord(value)) return Object.keys(value).length > 0;
  return value !== undefined && value !== null;
}

export function StrategyV2ReviewWorkspace({
  workflowId,
  runStatus,
  pendingSignal,
  pendingPayload,
  strategyState,
  candidates,
  candidateIds,
  researchArtifacts,
  stepSummaries,
  logs,
  disabled,
  isSubmitting,
  onSubmitSignal,
}: StrategyV2ReviewWorkspaceProps) {
  const { get } = useApiClient();

  const [showAllArtifacts, setShowAllArtifacts] = useState(false);
  const [selectedCompletedGate, setSelectedCompletedGate] = useState<StrategyV2PendingSignal | null>(null);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [fileStateById, setFileStateById] = useState<Record<string, FileRuntimeState>>({});
  const [artifactDataCache, setArtifactDataCache] = useState<Record<string, Record<string, unknown>>>({});

  const [strategyReviewedEvidence, setStrategyReviewedEvidence] = useState(true);
  const [strategyUnderstandsImpact, setStrategyUnderstandsImpact] = useState(true);
  const [strategyOperatorNote, setStrategyOperatorNote] = useState("");

  const [reviewedCandidateIds, setReviewedCandidateIds] = useState<string[]>([]);
  const [strategyConfirmedAssetRefs, setStrategyConfirmedAssetRefs] = useState<string[]>([]);
  const [strategyProceedResearch, setStrategyProceedResearch] = useState(true);
  const [strategySelectedAngleId, setStrategySelectedAngleId] = useState("");
  const [strategySelectedPairId, setStrategySelectedPairId] = useState("");
  const [strategySelectedVariantId, setStrategySelectedVariantId] = useState("");
  const [strategyFinalCopyApproved, setStrategyFinalCopyApproved] = useState(true);
  const [submitError, setSubmitError] = useState("");

  const gateSeed = useMemo(() => {
    const copyArtifactId = String(pendingPayload.copy_artifact_id || "").trim();
    return `${pendingSignal || "none"}:${candidateIds.join("|")}:${copyArtifactId}`;
  }, [candidateIds, pendingPayload.copy_artifact_id, pendingSignal]);

  useEffect(() => {
    setStrategyReviewedEvidence(true);
    setStrategyUnderstandsImpact(true);
    setStrategyOperatorNote("");
    setReviewedCandidateIds([]);
    setStrategyConfirmedAssetRefs([]);
    setStrategyProceedResearch(true);
    setStrategySelectedAngleId(candidateIds[0] || "");
    setStrategySelectedPairId(candidateIds[0] || "");
    setStrategySelectedVariantId(candidateIds[0] || "");
    setStrategyFinalCopyApproved(true);
    setActiveFileId(null);
    setFileStateById({});
    setArtifactDataCache({});
    setSubmitError("");
    setShowAllArtifacts(false);
    setSelectedCompletedGate(null);
  }, [candidateIds, gateSeed]);

  const artifactRefs = useMemo<Record<string, unknown>>(() => {
    if (!isRecord(strategyState?.artifact_refs)) return {};
    return strategyState?.artifact_refs as Record<string, unknown>;
  }, [strategyState?.artifact_refs]);

  const foundationalReviewFiles = useMemo<ReviewFile[]>(
    () =>
      FOUNDATIONAL_DOC_SPECS.map((spec) => {
        const expectedStepKey = `v2-02.foundation.${spec.stepSuffix}`;
        const artifact = findResearchArtifactByStepKeys(researchArtifacts, [
          expectedStepKey,
          spec.stepSuffix,
          spec.stepSuffix.padStart(2, "0"),
        ]);
        const summary = artifact ? artifact.summary || stepSummaries[artifact.step_key] || "" : "";
        return {
          id: `research-foundation-${spec.stepSuffix}`,
          title: spec.title,
          subtitle: summary ? summary.slice(0, 120) : spec.fallbackSubtitle,
          kind: "research" as const,
          required: true,
          stepKey: artifact?.step_key,
          missingReason: artifact
            ? undefined
            : `Missing foundational document '${spec.title}' (expected step key ${expectedStepKey}).`,
        };
      }),
    [researchArtifacts, stepSummaries],
  );

  const requiredFiles = useMemo<ReviewFile[]>(() => {
    if (!pendingSignal) return [];

    const files: ReviewFile[] = [];

    const pushStepPayloadFile = (stepKey: string, title: string, required = true) => {
      const artifactId = resolveStepPayloadArtifactId(artifactRefs, stepKey);
      files.push({
        id: `artifact-${stepKey}`,
        title,
        subtitle: `Step payload: ${stepKey}`,
        kind: "artifact",
        required,
        artifactId: artifactId || undefined,
        missingReason: artifactId ? undefined : `Missing artifact ref for ${stepKey}.`,
      });
    };

    if (pendingSignal === "strategy_v2_proceed_research") {
      return foundationalReviewFiles.map((file) => ({ ...file }));
    }

    if (pendingSignal === "strategy_v2_confirm_competitor_assets") {
      pushStepPayloadFile("v2-02i", "Competitor Candidate Dossier");
      candidates.forEach((candidate) => {
        const assetRef = String(candidate.assetRef || "").trim();
        files.push({
          id: `candidate-${candidate.id}`,
          title: candidate.label,
          subtitle: assetRef ? `Candidate dossier - ${assetRef}` : "Candidate dossier",
          kind: "candidate",
          required: false,
          candidateId: candidate.id,
          candidateRaw: candidate.raw,
          missingReason: candidate.raw ? undefined : `Candidate payload is missing for ${candidate.id}.`,
        });
      });
      return files;
    }

    if (pendingSignal === "strategy_v2_select_angle") {
      pushStepPayloadFile("v2-06", "Angle Synthesis Full File");
      candidates.forEach((candidate) => {
        files.push({
          id: `candidate-${candidate.id}`,
          title: candidate.label,
          subtitle: "Angle candidate dossier",
          kind: "candidate",
          required: false,
          candidateId: candidate.id,
          candidateRaw: candidate.raw,
          missingReason: candidate.raw ? undefined : `Angle payload is missing for ${candidate.id}.`,
        });
      });
      return files;
    }

    if (pendingSignal === "strategy_v2_select_ump_ums") {
      pushStepPayloadFile("v2-08", "UMP/UMS Scoring Full File");
      candidates.forEach((candidate) => {
        files.push({
          id: `candidate-${candidate.id}`,
          title: candidate.label,
          subtitle: "UMP/UMS pair dossier",
          kind: "candidate",
          required: false,
          candidateId: candidate.id,
          candidateRaw: candidate.raw,
          missingReason: candidate.raw ? undefined : `Pair payload is missing for ${candidate.id}.`,
        });
      });
      return files;
    }

    if (pendingSignal === "strategy_v2_select_offer_winner") {
      pushStepPayloadFile("v2-08b", "Offer Variant Evaluation Full File");
      candidates.forEach((candidate) => {
        files.push({
          id: `candidate-${candidate.id}`,
          title: candidate.label,
          subtitle: "Offer variant dossier",
          kind: "candidate",
          required: false,
          candidateId: candidate.id,
          candidateRaw: candidate.raw,
          missingReason: candidate.raw ? undefined : `Variant payload is missing for ${candidate.id}.`,
        });
      });
      return files;
    }

    const copyArtifactId = String(pendingPayload.copy_artifact_id || "").trim();
    const copyMissingReason = copyArtifactId ? undefined : "Missing copy_artifact_id in pending decision payload.";
    files.push(
      {
        id: "copy-headline",
        title: "Headline",
        subtitle: "Final headline",
        kind: "copy_field",
        required: true,
        copyField: "headline",
        artifactId: copyArtifactId || undefined,
        missingReason: copyMissingReason,
      },
      {
        id: "copy-body",
        title: "Body",
        subtitle: "Long-form body markdown",
        kind: "copy_field",
        required: true,
        copyField: "body_markdown",
        artifactId: copyArtifactId || undefined,
        missingReason: copyMissingReason,
      },
      {
        id: "copy-presell",
        title: "Advertorial/Presell",
        subtitle: "Presell markdown",
        kind: "copy_field",
        required: true,
        copyField: "presell_markdown",
        artifactId: copyArtifactId || undefined,
        missingReason: copyMissingReason,
      },
      {
        id: "copy-sales",
        title: "Sales Page",
        subtitle: "Sales page markdown",
        kind: "copy_field",
        required: true,
        copyField: "sales_page_markdown",
        artifactId: copyArtifactId || undefined,
        missingReason: copyMissingReason,
      },
      {
        id: "copy-quality",
        title: "Quality Report",
        subtitle: "QA and scoring details",
        kind: "copy_field",
        required: true,
        copyField: "quality_report",
        artifactId: copyArtifactId || undefined,
        missingReason: copyMissingReason,
      },
    );
    return files;
  }, [artifactRefs, candidates, foundationalReviewFiles, pendingPayload.copy_artifact_id, pendingSignal]);

  const candidateFileIdByCandidateId = useMemo(() => {
    const out: Record<string, string> = {};
    requiredFiles.forEach((file) => {
      if (file.candidateId) out[file.candidateId] = file.id;
    });
    return out;
  }, [requiredFiles]);

  const reviewChecklistItems = useMemo(() => {
    if (!pendingSignal) return [] as string[];
    if (pendingSignal === "strategy_v2_proceed_research") {
      return [
        "Read the full Competitor Research, Meta-Prompt, Deep Research, and Avatar Brief files.",
        "Verify category and segment coherence across foundational outputs before proceeding.",
        "Confirm evidence depth and traceability are sufficient to enter competitor asset review.",
      ];
    }
    if (pendingSignal === "strategy_v2_confirm_competitor_assets") {
      return [
        "Review candidate dossier(s) you intend to confirm.",
        "Validate source references and evidence quality for each selected asset.",
        "Confirm 3 to 15 asset refs and document rationale.",
      ];
    }
    if (pendingSignal === "strategy_v2_select_angle") {
      return [
        "Review the full angle synthesis file and contender dossiers.",
        "Confirm supporting evidence quality and contradiction handling.",
        "Select one angle and ensure it is explicitly reviewed.",
      ];
    }
    if (pendingSignal === "strategy_v2_select_ump_ums") {
      return [
        "Review the full pair scoring file and contender dossiers.",
        "Inspect the seven scoring dimensions and evidence quality.",
        "Select one pair and ensure it is explicitly reviewed.",
      ];
    }
    if (pendingSignal === "strategy_v2_select_offer_winner") {
      return [
        "Review the full variant evaluation file and contender dossiers.",
        "Check value, objection coverage, novelty, and risk tradeoffs.",
        "Select one variant and ensure it is explicitly reviewed.",
      ];
    }
    return [
      "Review all required final copy files in full markdown.",
      "Verify readiness and unresolved quality or compliance risk.",
      "Approve or reject with rationale in operator note.",
    ];
  }, [pendingSignal]);

  const getFileRuntime = (fileId: string): FileRuntimeState => {
    const current = fileStateById[fileId];
    if (current) return current;
    return {
      status: "idle",
      reviewed: false,
      content: "",
      error: "",
    };
  };

  const requiredFilesOnly = useMemo(() => requiredFiles.filter((file) => file.required), [requiredFiles]);

  const missingRequiredFiles = useMemo(
    () => requiredFilesOnly.filter((file) => Boolean(file.missingReason)),
    [requiredFilesOnly],
  );

  const unreviewedRequiredFiles = useMemo(
    () =>
      requiredFilesOnly.filter((file) => {
        if (file.missingReason) return false;
        return !getFileRuntime(file.id).reviewed;
      }),
    [requiredFilesOnly, fileStateById],
  );

  const fetchArtifactData = async (artifactId: string): Promise<Record<string, unknown>> => {
    const cached = artifactDataCache[artifactId];
    if (cached) return cached;
    const artifactResponse = await get<Record<string, unknown>>(`/artifacts/${artifactId}`);
    const artifactData = isRecord(artifactResponse.data)
      ? (artifactResponse.data as Record<string, unknown>)
      : artifactResponse;
    setArtifactDataCache((prev) => ({ ...prev, [artifactId]: artifactData }));
    return artifactData;
  };

  const loadFileContent = async (file: ReviewFile): Promise<string> => {
    if (file.missingReason) {
      throw new Error(file.missingReason);
    }

    if (file.kind === "research") {
      if (!workflowId) {
        throw new Error("Workflow ID is required to load research documents.");
      }
      if (!file.stepKey) {
        throw new Error(`Missing step key for ${file.title}.`);
      }
      const response = await get<Record<string, unknown>>(
        `/workflows/${workflowId}/research/${encodeURIComponent(file.stepKey)}`,
      );
      if (!("content" in response)) {
        throw new Error(`Research document ${file.title} returned no content.`);
      }
      return resolveResearchMarkdown(file.title, response.content);
    }

    if (file.kind === "artifact") {
      if (!file.artifactId) {
        throw new Error(`Missing artifact id for ${file.title}.`);
      }
      const artifactData = await fetchArtifactData(file.artifactId);
      return toJsonMarkdown(file.title, artifactData);
    }

    if (file.kind === "candidate") {
      if (!file.candidateRaw) {
        throw new Error(`Candidate payload is missing for ${file.title}.`);
      }
      return toJsonMarkdown(file.title, file.candidateRaw);
    }

    if (!file.artifactId) {
      throw new Error(`Missing artifact id for ${file.title}.`);
    }
    const artifactData = await fetchArtifactData(file.artifactId);
    const copyPayload = resolveCopyPayload(artifactData);
    if (!copyPayload) {
      throw new Error("Copy artifact payload is missing.");
    }

    if (file.copyField === "headline") {
      const headline = copyPayload.headline;
      if (typeof headline !== "string" || !headline.trim()) {
        throw new Error("Copy headline is missing.");
      }
      return `# Headline\n\n${headline.trim()}\n`;
    }

    if (file.copyField === "body_markdown") {
      const value = copyPayload.body_markdown;
      if (typeof value !== "string" || !value.trim()) {
        throw new Error("Copy body markdown is missing.");
      }
      return value;
    }

    if (file.copyField === "presell_markdown") {
      const value = copyPayload.presell_markdown;
      if (typeof value !== "string" || !value.trim()) {
        throw new Error("Copy presell markdown is missing.");
      }
      return value;
    }

    if (file.copyField === "sales_page_markdown") {
      const value = copyPayload.sales_page_markdown;
      if (typeof value !== "string" || !value.trim()) {
        throw new Error("Copy sales page markdown is missing.");
      }
      return value;
    }

    const qualityReport: Record<string, unknown> = {
      headline_qa: copyPayload.headline_qa,
      headline_scoring: copyPayload.headline_scoring,
      congruency: copyPayload.congruency,
      promise_contract: copyPayload.promise_contract,
      promise_contracts: copyPayload.promise_contracts,
    };
    const hasQualityPayload = Object.values(qualityReport).some((value) => hasNonEmptyValue(value));
    if (!hasQualityPayload) {
      throw new Error("Copy quality report fields are missing.");
    }
    return toJsonMarkdown("Copy Quality Report", qualityReport);
  };

  const openFile = async (file: ReviewFile) => {
    setActiveFileId(file.id);
    const runtime = getFileRuntime(file.id);
    if (runtime.status === "loaded" || runtime.status === "loading") return;

    setFileStateById((prev) => ({
      ...prev,
      [file.id]: {
        status: "loading",
        reviewed: prev[file.id]?.reviewed || false,
        content: prev[file.id]?.content || "",
        error: "",
      },
    }));

    try {
      const content = await loadFileContent(file);
      setFileStateById((prev) => ({
        ...prev,
        [file.id]: {
          status: "loaded",
          reviewed: prev[file.id]?.reviewed || false,
          content,
          error: "",
        },
      }));
    } catch (error) {
      setFileStateById((prev) => ({
        ...prev,
        [file.id]: {
          status: "error",
          reviewed: false,
          content: "",
          error: toErrorMessage(error),
        },
      }));
    }
  };

  const markActiveFileReviewed = () => {
    if (!activeFileId) return;
    const activeFile = requiredFiles.find((file) => file.id === activeFileId);
    if (!activeFile) return;

    setFileStateById((prev) => {
      const runtime = prev[activeFile.id] || {
        status: "idle",
        reviewed: false,
        content: "",
        error: "",
      };
      return {
        ...prev,
        [activeFile.id]: {
          ...runtime,
          reviewed: true,
        },
      };
    });

    if (activeFile.candidateId) {
      setReviewedCandidateIds((prev) =>
        prev.includes(activeFile.candidateId as string) ? prev : [...prev, activeFile.candidateId as string],
      );
    }

    if (pendingSignal === "strategy_v2_approve_final_copy" && candidateIds.length) {
      setReviewedCandidateIds((prev) => {
        const next = new Set(prev);
        candidateIds.forEach((id) => next.add(id));
        return Array.from(next);
      });
    }
  };

  const openNextRequiredFile = () => {
    if (!activeFileId) {
      return;
    }
    const orderedRequired = requiredFilesOnly.filter((file) => !file.missingReason);
    const currentIndex = orderedRequired.findIndex((file) => file.id === activeFileId);
    const nextFile = orderedRequired.slice(currentIndex + 1).find((file) => !getFileRuntime(file.id).reviewed);
    if (!nextFile) {
      setActiveFileId(null);
      return;
    }
    void openFile(nextFile);
  };

  const toggleConfirmedAssetRef = (id: string) => {
    setStrategyConfirmedAssetRefs((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const openCandidateFile = (candidateId: string) => {
    const fileId = candidateFileIdByCandidateId[candidateId];
    if (!fileId) return;
    const file = requiredFiles.find((row) => row.id === fileId);
    if (!file) return;
    void openFile(file);
  };

  const selectedAngleCandidate = useMemo(
    () => candidates.find((candidate) => candidate.id === strategySelectedAngleId),
    [candidates, strategySelectedAngleId],
  );

  const reviewedSet = useMemo(() => new Set(reviewedCandidateIds), [reviewedCandidateIds]);

  const candidateIdByAssetRef = useMemo(() => {
    const out: Record<string, string> = {};
    candidates.forEach((candidate) => {
      const assetRef = String(candidate.assetRef || "").trim();
      if (!assetRef) return;
      out[assetRef] = candidate.id;
    });
    return out;
  }, [candidates]);

  const validationMessages = useMemo(() => {
    if (!pendingSignal) return ["No pending Strategy V2 manual gate detected."];

    const messages: string[] = [];

    if (missingRequiredFiles.length) {
      messages.push(
        `Missing required file(s): ${missingRequiredFiles.map((file) => file.title).join(", ")}.`,
      );
    }
    if (unreviewedRequiredFiles.length) {
      messages.push(
        `Review required file(s): ${unreviewedRequiredFiles.map((file) => file.title).join(", ")}.`,
      );
    }

    if (!strategyReviewedEvidence) {
      messages.push("Attestation is required: reviewed evidence.");
    }
    if (!strategyUnderstandsImpact) {
      messages.push("Attestation is required: understands impact.");
    }
    if (strategyOperatorNote.trim().length < OPERATOR_NOTE_MIN_LENGTH) {
      messages.push(`Operator note must be at least ${OPERATOR_NOTE_MIN_LENGTH} characters.`);
    }

    if (pendingSignal === "strategy_v2_confirm_competitor_assets") {
      if (!candidates.length) {
        messages.push("No competitor candidates were provided for this gate.");
      }
      if (strategyConfirmedAssetRefs.length < 3 || strategyConfirmedAssetRefs.length > 15) {
        messages.push("Select between 3 and 15 competitor assets.");
      }
      const unknownConfirmedRefs = strategyConfirmedAssetRefs.filter((assetRef) => !candidateIdByAssetRef[assetRef]);
      if (unknownConfirmedRefs.length) {
        messages.push("One or more confirmed assets do not map to provided candidate source refs.");
      }
      const unreviewedSelections = strategyConfirmedAssetRefs.filter((assetRef) => {
        const candidateId = candidateIdByAssetRef[assetRef];
        if (!candidateId) return true;
        return !reviewedSet.has(candidateId);
      });
      if (unreviewedSelections.length) {
        messages.push("Each confirmed asset must be reviewed before submission.");
      }
      if (!reviewedCandidateIds.length) {
        messages.push("Review at least one competitor candidate dossier.");
      }
    }

    if (pendingSignal === "strategy_v2_select_angle") {
      if (!candidates.length) {
        messages.push("No angle candidates were provided for this gate.");
      }
      if (!strategySelectedAngleId) {
        messages.push("Select one angle.");
      }
      if (strategySelectedAngleId && !reviewedSet.has(strategySelectedAngleId)) {
        messages.push("Selected angle must be reviewed before submission.");
      }
      if (!selectedAngleCandidate?.raw) {
        messages.push("Selected angle payload is missing.");
      }
    }

    if (pendingSignal === "strategy_v2_select_ump_ums") {
      if (!candidates.length) {
        messages.push("No UMP/UMS candidates were provided for this gate.");
      }
      if (!strategySelectedPairId) {
        messages.push("Select one UMP/UMS pair.");
      }
      if (strategySelectedPairId && !reviewedSet.has(strategySelectedPairId)) {
        messages.push("Selected pair must be reviewed before submission.");
      }
    }

    if (pendingSignal === "strategy_v2_select_offer_winner") {
      if (!candidates.length) {
        messages.push("No offer variants were provided for this gate.");
      }
      if (!strategySelectedVariantId) {
        messages.push("Select one winning variant.");
      }
      if (strategySelectedVariantId && !reviewedSet.has(strategySelectedVariantId)) {
        messages.push("Selected variant must be reviewed before submission.");
      }
    }

    if (pendingSignal === "strategy_v2_approve_final_copy") {
      if (!candidateIds.length) {
        messages.push("Copy candidate id is missing for final approval.");
      }
      if (!reviewedCandidateIds.length) {
        messages.push("Review final copy files before approval submission.");
      }
    }

    return messages;
  }, [
    pendingSignal,
    missingRequiredFiles,
    unreviewedRequiredFiles,
    strategyReviewedEvidence,
    strategyUnderstandsImpact,
    strategyOperatorNote,
    candidates,
    strategyConfirmedAssetRefs,
    reviewedSet,
    reviewedCandidateIds.length,
    strategySelectedAngleId,
    selectedAngleCandidate?.raw,
    strategySelectedPairId,
    strategySelectedVariantId,
    candidateIds.length,
    candidateIdByAssetRef,
  ]);

  const canSubmit = Boolean(pendingSignal) && !disabled && !isSubmitting && validationMessages.length === 0;

  const handleSubmit = () => {
    if (!pendingSignal || !canSubmit) return;

    setSubmitError("");

    const baseDecision: Record<string, unknown> = {
      decision_mode: "manual",
      attestation: {
        reviewed_evidence: strategyReviewedEvidence,
        understands_impact: strategyUnderstandsImpact,
      },
      operator_note: strategyOperatorNote.trim(),
    };

    const reviewedIds = Array.from(new Set(reviewedCandidateIds));

    if (pendingSignal === "strategy_v2_proceed_research") {
      onSubmitSignal(strategyV2SignalPath(pendingSignal), {
        ...baseDecision,
        proceed: strategyProceedResearch,
      });
      return;
    }

    if (pendingSignal === "strategy_v2_confirm_competitor_assets") {
      const confirmedRefs = Array.from(new Set(strategyConfirmedAssetRefs));
      onSubmitSignal(strategyV2SignalPath(pendingSignal), {
        ...baseDecision,
        confirmed_asset_refs: confirmedRefs,
        reviewed_candidate_ids: reviewedIds,
      });
      return;
    }

    if (pendingSignal === "strategy_v2_select_angle") {
      const selected = selectedAngleCandidate?.raw;
      if (!selected) {
        setSubmitError("Selected angle payload is missing. Open and review a valid angle dossier.");
        return;
      }
      onSubmitSignal(strategyV2SignalPath(pendingSignal), {
        ...baseDecision,
        selected_angle: selected,
        rejected_angle_ids: candidateIds.filter((id) => id !== strategySelectedAngleId),
        reviewed_candidate_ids: reviewedIds,
      });
      return;
    }

    if (pendingSignal === "strategy_v2_select_ump_ums") {
      onSubmitSignal(strategyV2SignalPath(pendingSignal), {
        ...baseDecision,
        pair_id: strategySelectedPairId,
        rejected_pair_ids: candidateIds.filter((id) => id !== strategySelectedPairId),
        reviewed_candidate_ids: reviewedIds,
      });
      return;
    }

    if (pendingSignal === "strategy_v2_select_offer_winner") {
      onSubmitSignal(strategyV2SignalPath(pendingSignal), {
        ...baseDecision,
        variant_id: strategySelectedVariantId,
        rejected_variant_ids: candidateIds.filter((id) => id !== strategySelectedVariantId),
        reviewed_candidate_ids: reviewedIds,
      });
      return;
    }

    onSubmitSignal(strategyV2SignalPath(pendingSignal), {
      ...baseDecision,
      approved: strategyFinalCopyApproved,
      reviewed_candidate_ids: reviewedIds,
    });
  };

  const activeFile = activeFileId ? requiredFiles.find((file) => file.id === activeFileId) : undefined;
  const resolvedActiveFile = activeFile || foundationalReviewFiles.find((file) => file.id === activeFileId);
  const activeRuntime = resolvedActiveFile ? getFileRuntime(resolvedActiveFile.id) : undefined;
  const availableFoundationalFiles = foundationalReviewFiles.filter((file) => !file.missingReason);
  const missingFoundationalFiles = foundationalReviewFiles.filter((file) => Boolean(file.missingReason));

  const pendingGateIndex = pendingSignal ? GATE_SEQUENCE.indexOf(pendingSignal) : -1;
  const completedGateCount =
    pendingGateIndex >= 0
      ? pendingGateIndex
      : inferCompletedGateCount(strategyState?.current_stage || null, runStatus);
  const completedGates = useMemo(
    () => GATE_SEQUENCE.slice(0, Math.max(completedGateCount, 0)),
    [completedGateCount],
  );

  useEffect(() => {
    if (!selectedCompletedGate) return;
    if (completedGates.includes(selectedCompletedGate)) return;
    setSelectedCompletedGate(null);
  }, [completedGates, selectedCompletedGate]);

  const gateReceiptBySignal = useMemo(() => {
    const receipts: Partial<Record<StrategyV2PendingSignal, GateReceipt | null>> = {};
    GATE_SEQUENCE.forEach((signal) => {
      receipts[signal] = findLatestGateReceipt(logs, signal);
    });
    return receipts;
  }, [logs]);
  const selectedReceipt =
    selectedCompletedGate && completedGates.includes(selectedCompletedGate)
      ? gateReceiptBySignal[selectedCompletedGate] || null
      : null;

  const isViewingCompletedReceipt =
    Boolean(selectedCompletedGate) && selectedCompletedGate !== pendingSignal && completedGates.includes(selectedCompletedGate as StrategyV2PendingSignal);

  const selectedReceiptSummaryRows = useMemo(() => {
    if (!selectedReceipt) return [] as Array<{ label: string; value: string }>;
    const payload = selectedReceipt.payload;
    const attestation = isRecord(payload.attestation) ? payload.attestation : null;
    const reviewedIds = Array.isArray(payload.reviewed_candidate_ids)
      ? payload.reviewed_candidate_ids.filter((row): row is string => typeof row === "string" && row.trim().length > 0)
      : [];
    const rows: Array<{ label: string; value: string }> = [
      { label: "Submitted", value: formatReceiptDate(selectedReceipt.createdAt) },
      {
        label: "Operator",
        value: typeof payload.operator_user_id === "string" && payload.operator_user_id.trim()
          ? payload.operator_user_id
          : "Unknown",
      },
      {
        label: "Decision mode",
        value: typeof payload.decision_mode === "string" && payload.decision_mode.trim()
          ? payload.decision_mode
          : "manual",
      },
      {
        label: "Reviewed evidence",
        value: attestation && typeof attestation.reviewed_evidence === "boolean"
          ? String(attestation.reviewed_evidence)
          : "Unknown",
      },
      {
        label: "Understands impact",
        value: attestation && typeof attestation.understands_impact === "boolean"
          ? String(attestation.understands_impact)
          : "Unknown",
      },
      { label: "Reviewed candidates", value: String(reviewedIds.length) },
    ];

    if (selectedReceipt.signal === "strategy_v2_proceed_research") {
      rows.push({
        label: "Decision",
        value: payload.proceed === true ? "Proceed" : payload.proceed === false ? "Hold" : "Unknown",
      });
    } else if (selectedReceipt.signal === "strategy_v2_confirm_competitor_assets") {
      const refs = Array.isArray(payload.confirmed_asset_refs)
        ? payload.confirmed_asset_refs.filter((row): row is string => typeof row === "string" && row.trim().length > 0)
        : [];
      rows.push({ label: "Confirmed assets", value: String(refs.length) });
    } else if (selectedReceipt.signal === "strategy_v2_select_angle") {
      const selectedAngle = isRecord(payload.selected_angle) ? payload.selected_angle : null;
      const angleLabel =
        (selectedAngle && typeof selectedAngle.angle_name === "string" && selectedAngle.angle_name.trim()) ||
        (selectedAngle && typeof selectedAngle.angle_id === "string" && selectedAngle.angle_id.trim()) ||
        "Unknown";
      rows.push({ label: "Selected angle", value: angleLabel });
    } else if (selectedReceipt.signal === "strategy_v2_select_ump_ums") {
      rows.push({
        label: "Selected pair",
        value: typeof payload.pair_id === "string" && payload.pair_id.trim() ? payload.pair_id : "Unknown",
      });
    } else if (selectedReceipt.signal === "strategy_v2_select_offer_winner") {
      rows.push({
        label: "Selected variant",
        value: typeof payload.variant_id === "string" && payload.variant_id.trim() ? payload.variant_id : "Unknown",
      });
    } else {
      rows.push({
        label: "Decision",
        value: payload.approved === true ? "Approved" : payload.approved === false ? "Rejected" : "Unknown",
      });
    }

    if (typeof payload.operator_note === "string" && payload.operator_note.trim()) {
      rows.push({ label: "Operator note", value: payload.operator_note.trim() });
    }

    return rows;
  }, [selectedReceipt]);

  return (
    <div className="mt-3 space-y-4">
      {pendingSignal ? (
        <Callout variant="warning" title={`Review required: ${strategyV2SignalLabel(pendingSignal)}`}>
          Complete required file review in the center panel, then decide and submit.
        </Callout>
      ) : (
        <Callout variant="neutral" title="No pending Strategy V2 gate">
          The workflow is running automatic stages or has completed all human checkpoints. Foundational docs remain
          available below when persisted for this run.
        </Callout>
      )}

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <div className="space-y-2">
          {GATE_SEQUENCE.map((gate, index) => {
            const status = index < completedGateCount ? "completed" : index === pendingGateIndex ? "current" : "upcoming";
            const isSelected = gate === selectedCompletedGate;
            return (
              <button
                key={gate}
                type="button"
                className={cn(
                  "ds-card ds-card--sm w-full text-left",
                  status === "upcoming" ? "bg-surface-2 opacity-70 cursor-default" : "bg-surface-2 hover:bg-hover",
                  isSelected ? "ring-1 ring-accent" : "",
                )}
                onClick={() => {
                  if (status === "upcoming") return;
                  setActiveFileId(null);
                  if (status === "completed") {
                    setSelectedCompletedGate(gate);
                    return;
                  }
                  setSelectedCompletedGate(null);
                }}
                disabled={status === "upcoming"}
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold text-content">Step {index + 1}</div>
                    <div className="text-xs text-content-muted">{strategyV2SignalLabel(gate)}</div>
                  </div>
                  <Badge tone={status === "completed" ? "success" : status === "current" ? "accent" : "neutral"}>
                    {status === "completed" ? "Completed" : status === "current" ? "Current" : "Upcoming"}
                  </Badge>
                </div>
              </button>
            );
          })}

          <Button
            variant="secondary"
            size="xs"
            className="w-full"
            onClick={() => setShowAllArtifacts((value) => !value)}
          >
            {showAllArtifacts ? "Hide all artifacts" : "All artifacts"}
          </Button>
        </div>

        <div className="space-y-4">
          {showAllArtifacts ? (
            <div className="ds-card ds-card--md">
              <div className="text-sm font-semibold text-content">All artifact references</div>
              {Object.keys(artifactRefs).length ? (
                <div className="mt-2 space-y-1 text-xs text-content-muted">
                  {Object.entries(artifactRefs)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([key, value]) => (
                      <div key={key} className="flex items-start justify-between gap-3">
                        <span className="font-mono text-[11px] text-content">{key}</span>
                        <span className="font-mono text-[11px] break-all">{String(value)}</span>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="mt-2 text-xs text-content-muted">No artifact references are available for this run.</div>
              )}
            </div>
          ) : null}

          {isViewingCompletedReceipt ? (
            <div className="ds-card ds-card--md space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                <div>
                  <div className="text-sm font-semibold text-content">
                    Decision receipt: {strategyV2SignalLabel(selectedCompletedGate as StrategyV2PendingSignal)}
                  </div>
                  <div className="text-xs text-content-muted">Read-only audit view for completed gate submission.</div>
                </div>
                {pendingSignal ? (
                  <Button variant="secondary" size="xs" onClick={() => setSelectedCompletedGate(null)}>
                    Back to current gate
                  </Button>
                ) : null}
              </div>

              {!selectedReceipt ? (
                <Callout variant="danger" title="Decision receipt unavailable">
                  No receipt payload was found for this completed gate.
                </Callout>
              ) : (
                <>
                  <div className="grid gap-2 md:grid-cols-2">
                    {selectedReceiptSummaryRows.map((row) => (
                      <div key={`${row.label}-${row.value}`} className="ds-card ds-card--sm bg-surface-2">
                        <div className="text-[11px] text-content-muted">{row.label}</div>
                        <div className="text-xs text-content break-words">{row.value}</div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="mb-2 text-xs font-semibold text-content">Raw payload</div>
                    <MarkdownViewer content={toJsonMarkdown("Decision Payload", selectedReceipt.payload)} />
                  </div>
                </>
              )}
            </div>
          ) : resolvedActiveFile ? (
            <div className="ds-card ds-card--md space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                <Button variant="ghost" size="xs" onClick={() => setActiveFileId(null)}>
                  <ArrowLeft className="h-4 w-4" />
                  {pendingSignal ? "Back to gate review" : "Back to foundational docs"}
                </Button>
                <div className="text-right">
                  <div className="text-xs font-semibold text-content">{resolvedActiveFile.title}</div>
                  <div className="text-[11px] text-content-muted font-mono">
                    {resolvedActiveFile.stepKey ? `step=${resolvedActiveFile.stepKey}` : ""}
                    {resolvedActiveFile.artifactId ? ` artifact=${resolvedActiveFile.artifactId}` : ""}
                  </div>
                </div>
              </div>

              {activeRuntime?.status === "loading" ? (
                <div className="flex items-center gap-2 text-sm text-content-muted">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading full file...
                </div>
              ) : activeRuntime?.status === "error" ? (
                <Callout variant="danger" title="Failed to load file">
                  {activeRuntime.error || "The selected file could not be loaded."}
                </Callout>
              ) : (
                <MarkdownViewer content={activeRuntime?.content || ""} />
              )}

              <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={markActiveFileReviewed}
                  disabled={activeRuntime?.status !== "loaded"}
                >
                  Mark reviewed
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={openNextRequiredFile}
                  disabled={activeRuntime?.status !== "loaded"}
                >
                  Next required file
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ) : !pendingSignal ? (
            <div className="ds-card ds-card--md space-y-3">
              <div>
                <div className="text-sm font-semibold text-content">Foundational docs</div>
                <div className="text-xs text-content-muted">
                  Stage 1 full files expected by source of truth: competitor research, meta-prompt, deep research, and
                  avatar brief.
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                {foundationalReviewFiles.map((file) => {
                  const runtime = getFileRuntime(file.id);
                  const statusTone = file.missingReason
                    ? "danger"
                    : runtime.reviewed
                      ? "success"
                      : runtime.status === "loading"
                        ? "accent"
                        : runtime.status === "loaded"
                          ? "accent"
                          : "neutral";
                  const statusText = file.missingReason
                    ? "Missing"
                    : runtime.reviewed
                      ? "Reviewed"
                      : runtime.status === "loading"
                        ? "Loading"
                        : runtime.status === "loaded"
                          ? "Loaded"
                          : "Not opened";
                  return (
                    <button
                      key={file.id}
                      type="button"
                      className={cn(
                        "ds-card ds-card--sm text-left transition",
                        file.missingReason ? "bg-danger/5 border-danger/30" : "bg-surface-2 hover:bg-hover",
                      )}
                      onClick={() => {
                        if (file.missingReason) return;
                        void openFile(file);
                      }}
                      disabled={Boolean(file.missingReason)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-xs font-semibold text-content truncate">{file.title}</div>
                          <div className="text-[11px] text-content-muted">{file.subtitle || ""}</div>
                          {file.missingReason ? (
                            <div className="mt-1 text-[11px] text-danger">{file.missingReason}</div>
                          ) : null}
                        </div>
                        <Badge tone={statusTone}>{statusText}</Badge>
                      </div>
                    </button>
                  );
                })}
              </div>

              {!availableFoundationalFiles.length ? (
                <Callout variant="danger" title="Foundational docs are unavailable for this workflow run">
                  This run does not contain persisted Stage 1 foundational files in research artifacts.
                </Callout>
              ) : null}
              {missingFoundationalFiles.length ? (
                <Callout variant="warning" title="Some foundational docs are missing">
                  {missingFoundationalFiles.map((file) => (
                    <div key={file.id}>• {file.title}</div>
                  ))}
                </Callout>
              ) : null}
            </div>
          ) : (
            <>
              <div className="ds-card ds-card--md space-y-3">
                <div>
                  <div className="text-sm font-semibold text-content">Required files</div>
                  <div className="text-xs text-content-muted">
                    Open each file in the center reader and mark it reviewed before submission.
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  {requiredFiles.map((file) => {
                    const runtime = getFileRuntime(file.id);
                    const statusTone = file.missingReason
                      ? "danger"
                      : runtime.reviewed
                        ? "success"
                        : runtime.status === "loading"
                          ? "accent"
                          : runtime.status === "loaded"
                            ? "accent"
                            : "neutral";
                    const statusText = file.missingReason
                      ? "Missing"
                      : runtime.reviewed
                        ? "Reviewed"
                        : runtime.status === "loading"
                          ? "Loading"
                          : runtime.status === "loaded"
                            ? "Loaded"
                            : "Not opened";
                    return (
                      <button
                        key={file.id}
                        type="button"
                        className={cn(
                          "ds-card ds-card--sm text-left transition",
                          file.missingReason ? "bg-danger/5 border-danger/30" : "bg-surface-2 hover:bg-hover",
                        )}
                        onClick={() => {
                          void openFile(file);
                        }}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-content truncate">{file.title}</div>
                            <div className="text-[11px] text-content-muted">{file.subtitle || ""}</div>
                            {file.missingReason ? (
                              <div className="mt-1 text-[11px] text-danger">{file.missingReason}</div>
                            ) : null}
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            {file.required ? <Badge tone="accent">Required</Badge> : <Badge tone="neutral">Optional</Badge>}
                            <Badge tone={statusTone}>{statusText}</Badge>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="ds-card ds-card--md">
                <div className="text-sm font-semibold text-content">Review checklist</div>
                <div className="mt-2 space-y-1 text-xs text-content-muted">
                  {reviewChecklistItems.map((item) => (
                    <div key={item}>• {item}</div>
                  ))}
                </div>
              </div>

              <div className="ds-card ds-card--md space-y-3">
                <div className="text-sm font-semibold text-content">Decide</div>

                {pendingSignal === "strategy_v2_proceed_research" ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant={strategyProceedResearch ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => setStrategyProceedResearch(true)}
                    >
                      Proceed
                    </Button>
                    <Button
                      type="button"
                      variant={!strategyProceedResearch ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => setStrategyProceedResearch(false)}
                    >
                      Hold
                    </Button>
                  </div>
                ) : null}

                {pendingSignal === "strategy_v2_confirm_competitor_assets" ? (
                  <div className="space-y-2">
                    {candidates.map((candidate) => {
                      const reviewed = reviewedSet.has(candidate.id);
                      const assetRef = String(candidate.assetRef || "").trim();
                      const canConfirm = Boolean(assetRef);
                      return (
                        <label key={candidate.id} className="flex items-center justify-between gap-3 text-xs text-content">
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="checkbox"
                              className="h-4 w-4 rounded border border-border bg-surface text-accent"
                              checked={canConfirm ? strategyConfirmedAssetRefs.includes(assetRef) : false}
                              onChange={() => {
                                if (!canConfirm) return;
                                toggleConfirmedAssetRef(assetRef);
                              }}
                              disabled={!canConfirm}
                            />
                            <div className="min-w-0">
                              <span className="truncate block">{candidate.label}</span>
                              <span className="block text-[11px] text-content-muted font-mono">
                                {assetRef || "Missing source_ref in candidate payload"}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge tone={reviewed ? "success" : "neutral"}>{reviewed ? "Reviewed" : "Not reviewed"}</Badge>
                            <Button
                              type="button"
                              variant="secondary"
                              size="xs"
                              onClick={() => openCandidateFile(candidate.id)}
                            >
                              Open dossier
                            </Button>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                ) : null}

                {pendingSignal === "strategy_v2_select_angle" ? (
                  <div className="space-y-2">
                    {candidates.map((candidate) => {
                      const reviewed = reviewedSet.has(candidate.id);
                      return (
                        <label key={candidate.id} className="flex items-center justify-between gap-3 text-xs text-content">
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="radio"
                              name="strategy-angle"
                              className="h-4 w-4 border border-border bg-surface text-accent"
                              checked={strategySelectedAngleId === candidate.id}
                              onChange={() => setStrategySelectedAngleId(candidate.id)}
                            />
                            <span className="truncate">{candidate.label}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge tone={reviewed ? "success" : "neutral"}>{reviewed ? "Reviewed" : "Not reviewed"}</Badge>
                            <Button
                              type="button"
                              variant="secondary"
                              size="xs"
                              onClick={() => openCandidateFile(candidate.id)}
                            >
                              Open dossier
                            </Button>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                ) : null}

                {pendingSignal === "strategy_v2_select_ump_ums" ? (
                  <div className="space-y-2">
                    {candidates.map((candidate) => {
                      const reviewed = reviewedSet.has(candidate.id);
                      return (
                        <label key={candidate.id} className="flex items-center justify-between gap-3 text-xs text-content">
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="radio"
                              name="strategy-pair"
                              className="h-4 w-4 border border-border bg-surface text-accent"
                              checked={strategySelectedPairId === candidate.id}
                              onChange={() => setStrategySelectedPairId(candidate.id)}
                            />
                            <span className="truncate">{candidate.label}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge tone={reviewed ? "success" : "neutral"}>{reviewed ? "Reviewed" : "Not reviewed"}</Badge>
                            <Button
                              type="button"
                              variant="secondary"
                              size="xs"
                              onClick={() => openCandidateFile(candidate.id)}
                            >
                              Open dossier
                            </Button>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                ) : null}

                {pendingSignal === "strategy_v2_select_offer_winner" ? (
                  <div className="space-y-2">
                    {candidates.map((candidate) => {
                      const reviewed = reviewedSet.has(candidate.id);
                      return (
                        <label key={candidate.id} className="flex items-center justify-between gap-3 text-xs text-content">
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="radio"
                              name="strategy-variant"
                              className="h-4 w-4 border border-border bg-surface text-accent"
                              checked={strategySelectedVariantId === candidate.id}
                              onChange={() => setStrategySelectedVariantId(candidate.id)}
                            />
                            <span className="truncate">{candidate.label}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge tone={reviewed ? "success" : "neutral"}>{reviewed ? "Reviewed" : "Not reviewed"}</Badge>
                            <Button
                              type="button"
                              variant="secondary"
                              size="xs"
                              onClick={() => openCandidateFile(candidate.id)}
                            >
                              Open dossier
                            </Button>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                ) : null}

                {pendingSignal === "strategy_v2_approve_final_copy" ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant={strategyFinalCopyApproved ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => setStrategyFinalCopyApproved(true)}
                    >
                      Approve
                    </Button>
                    <Button
                      type="button"
                      variant={!strategyFinalCopyApproved ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => setStrategyFinalCopyApproved(false)}
                    >
                      Reject
                    </Button>
                  </div>
                ) : null}
              </div>

              <div className="ds-card ds-card--md space-y-3">
                <div className="text-sm font-semibold text-content">Attest and submit</div>
                <label className="flex items-center gap-2 text-xs text-content">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border border-border bg-surface text-accent"
                    checked={strategyReviewedEvidence}
                    onChange={() => setStrategyReviewedEvidence((value) => !value)}
                  />
                  <span>I reviewed the evidence required for this decision.</span>
                </label>
                <label className="flex items-center gap-2 text-xs text-content">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border border-border bg-surface text-accent"
                    checked={strategyUnderstandsImpact}
                    onChange={() => setStrategyUnderstandsImpact((value) => !value)}
                  />
                  <span>I understand the impact of this decision.</span>
                </label>

                <div>
                  <div className="text-xs text-content-muted mb-1">
                    Operator note (minimum {OPERATOR_NOTE_MIN_LENGTH} characters)
                  </div>
                  <Textarea
                    rows={4}
                    value={strategyOperatorNote}
                    onChange={(event) => setStrategyOperatorNote(event.target.value)}
                    placeholder="Explain what you reviewed and why this decision is correct."
                  />
                </div>

                {submitError ? (
                  <Callout variant="danger" title="Cannot submit">
                    {submitError}
                  </Callout>
                ) : null}

                {validationMessages.length ? (
                  <Callout variant="danger" title="Submission blocked until the following are resolved">
                    {validationMessages.map((message) => (
                      <div key={message}>• {message}</div>
                    ))}
                  </Callout>
                ) : (
                  <Callout variant="success" title="Ready to submit">
                    All required files are reviewed and decision payload validation checks pass.
                  </Callout>
                )}

                <div className="flex justify-end">
                  <Button variant="primary" size="sm" onClick={handleSubmit} disabled={!canSubmit}>
                    {isSubmitting ? "Sending..." : `Send ${strategyV2SignalLabel(pendingSignal)}`}
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

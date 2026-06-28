import { useEffect, useMemo, useState, type ComponentProps, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  ImageIcon,
  ImagePlus,
  Link2,
  ListChecks,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

import { useClientPostizChannels, useClientPostizPostingProfiles } from "@/api/clients";
import {
  useAgentActionProposals,
  useApproveAgentActionProposal,
  useApproveContentVariant,
  useContentExperiments,
  useContentVariants,
  useConversionSources,
  useCreateContentExperiment,
  useCreateContentVariant,
  useCreateConversionSource,
  useCreateGrowthProgram,
  useCreatePostizHandoffProposal,
  useGrowthPrograms,
  useSocialProviderAssets,
} from "@/api/socialAgents";
import { EmptyState } from "@/components/layout/EmptyState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useApiClient } from "@/api/client";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import { cn } from "@/lib/utils";
import type { ContentVariant } from "@/types/socialAgents";

type BadgeTone = NonNullable<ComponentProps<typeof Badge>["tone"]>;

const LARRY_SLIDE_FORMULA = [
  {
    visualRole: "hook",
    purpose: "HOOK",
    defaultText: "POV: your routine looks calm\nbut your brain missed the memo",
    stylePrompt: "Same subject and camera angle. Tired, slightly messy starting point. Natural phone photo.",
  },
  {
    visualRole: "problem",
    purpose: "PROBLEM",
    defaultText: "You tried every fix\nand still end the day wired",
    stylePrompt: "Same subject and camera angle. Amplify the pain with small signs of friction and fatigue.",
  },
  {
    visualRole: "discovery",
    purpose: "DISCOVERY",
    defaultText: "So I tried a cleaner\nwind-down loop",
    stylePrompt: "Same subject and camera angle. First turning point. Cleaner composition, still realistic.",
  },
  {
    visualRole: "transformation_1",
    purpose: "TRANSFORMATION",
    defaultText: "Wait...\nthis actually feels doable?",
    stylePrompt: "Same subject and camera angle. First clear improvement. Warm, believable, not over-polished.",
  },
  {
    visualRole: "transformation_2",
    purpose: "ESCALATION",
    defaultText: "Okay I'm obsessed\nwith this reset",
    stylePrompt: "Same subject and camera angle. Strongest transformation. More polished, aspirational, still phone-shot.",
  },
  {
    visualRole: "cta",
    purpose: "CTA",
    defaultText: "Try the app\nlink in bio",
    stylePrompt: "Same subject and camera angle. Clean final result with space for CTA overlay.",
  },
] as const;

const DEFAULT_BASE_PROMPT = [
  "iPhone photo of the same lived-in evening routine setup, portrait orientation.",
  "Same subject, same camera angle, same lighting direction, realistic phone camera quality.",
  "No text, no watermark, no logos. Leave clean space in the upper third for overlay copy.",
].join(" ");

const RENDERED_ASSET_WIDTH = 1080;
const RENDERED_ASSET_HEIGHT = 1920;

type RenderedCarouselAsset = {
  slideIndex: number;
  dataUrl: string;
  filename: string;
};

type GeneratedImageAsset = {
  assetId: string;
  publicId: string;
  url: string;
  width?: number | null;
  height?: number | null;
};

function splitLines(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function splitSlideEntries(value: string) {
  if (value.includes("---")) {
    return value
      .split(/\n\s*---\s*\n/g)
      .map((entry) => entry.trim())
      .filter(Boolean);
  }
  return splitLines(value);
}

function toneForStatus(status?: string | null): BadgeTone {
  const normalized = String(status || "").toLowerCase();
  if (["approved", "active", "published", "complete"].includes(normalized)) return "success";
  if (["pending", "draft", "review"].includes(normalized)) return "warning";
  if (["failed", "error", "rejected"].includes(normalized)) return "danger";
  return "neutral";
}

function latestVariant(variants: ContentVariant[]) {
  return variants[0] || null;
}

function textForSlide(lines: string[], index: number) {
  return lines[index] || LARRY_SLIDE_FORMULA[index]?.defaultText || "";
}

function IconActionButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex size-8 items-center justify-center rounded-full border border-border bg-surface text-content shadow-sm transition hover:border-primary hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 disabled:pointer-events-none disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function CarouselSlideCard({
  index,
  purpose,
  text,
  mediaUrl,
  assetStatus,
  draftStatus,
  onEdit,
  onAsset,
  onRegenerate,
  onApprove,
  regenerateDisabled,
  approveDisabled,
}: {
  index: number;
  purpose: string;
  text: string;
  mediaUrl?: string;
  assetStatus: string;
  draftStatus: string;
  onEdit: () => void;
  onAsset: () => void;
  onRegenerate: () => void;
  onApprove: () => void;
  regenerateDisabled: boolean;
  approveDisabled: boolean;
}) {
  const visualBackgrounds = [
    "linear-gradient(135deg, var(--content), var(--surface-2))",
    "linear-gradient(135deg, var(--content), var(--accent))",
    "linear-gradient(135deg, var(--content), var(--primary))",
    "linear-gradient(135deg, var(--content), var(--success))",
    "linear-gradient(135deg, var(--content), var(--warning))",
    "linear-gradient(135deg, var(--content), var(--danger))",
  ];
  return (
    <article data-testid="slide-preview-card" className="group overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      <div
        className="relative aspect-[9/16] bg-surface-2"
        style={{ background: visualBackgrounds[(index - 1) % visualBackgrounds.length] }}
      >
        {mediaUrl ? (
          <img src={mediaUrl} alt={`Carousel source media for slide ${index}`} className="absolute inset-0 size-full object-cover" />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-white/70">
            <ImageIcon className="size-10" />
          </div>
        )}
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.12),rgba(0,0,0,0.42))]" />
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          <span className="rounded-sm bg-black/55 px-2 py-1 text-[10px] font-semibold uppercase tracking-normal text-white">
            S{index}
          </span>
          <span className="rounded-sm bg-black/55 px-2 py-1 text-[10px] font-semibold uppercase tracking-normal text-white">
            {draftStatus}
          </span>
        </div>
        <div className="absolute left-4 right-4 top-[26%] text-center text-[clamp(18px,4vw,30px)] font-black leading-[1.06] tracking-normal text-white [text-shadow:0_2px_0_#000,0_0_10px_rgba(0,0,0,0.65)]">
          {text.split("\n").map((line) => (
            <div key={line}>{line}</div>
          ))}
        </div>
        <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between text-[11px] font-semibold uppercase tracking-normal text-white/85">
          <span>Slide {index}</span>
          <span>{purpose}</span>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-divider p-2">
        <div className="flex min-w-0 flex-wrap gap-1.5">
          <Badge tone={mediaUrl ? "success" : "warning"}>{assetStatus}</Badge>
          <Badge tone="neutral">{purpose}</Badge>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconActionButton label={`Edit slide ${index}`} onClick={onEdit}>
            <Pencil className="size-4" />
          </IconActionButton>
          <IconActionButton label={`Add asset for slide ${index}`} onClick={onAsset}>
            <ImagePlus className="size-4" />
          </IconActionButton>
          <IconActionButton label={`Regenerate slide ${index}`} onClick={onRegenerate} disabled={regenerateDisabled}>
            <RefreshCw className="size-4" />
          </IconActionButton>
          <IconActionButton label={`Approve slide ${index}`} onClick={onApprove} disabled={approveDisabled}>
            <Check className="size-4" />
          </IconActionButton>
        </div>
      </div>
    </article>
  );
}

type PanelKey = "connected" | "queue" | "dossier" | null;

type AgentScreenId = "setup" | "review";

type ReviewEditorTab = "test" | "draft" | "assets" | "postiz";

const REVIEW_EDITOR_TABS: { id: ReviewEditorTab; label: string }[] = [
  { id: "draft", label: "Draft" },
  { id: "assets", label: "Assets" },
  { id: "postiz", label: "Postiz" },
  { id: "test", label: "Test" },
];

type AgentScreen = {
  id: AgentScreenId;
  title: string;
};

const AGENT_SCREENS: AgentScreen[] = [
  { id: "setup", title: "Setup" },
  { id: "review", title: "Review" },
];

type ProviderAssetSummary = {
  id: string;
  provider: string;
  displayName: string;
  assetType: string;
  status: string;
  capabilityFlags?: string[] | null;
};

type ActionProposalSummary = {
  id: string;
  actionType: string;
  targetProvider: string;
  targetAssetId?: string | null;
  targetAssetType?: string | null;
  riskLabel?: string | null;
  status: string;
};

function AgentScreenButton({
  active,
  status,
  screen,
  onClick,
}: {
  active: boolean;
  status: string;
  screen: AgentScreen;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={`${screen.title} screen`}
      className={cn(
        "min-h-10 rounded-md border px-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20",
        active ? "border-primary bg-surface text-content shadow-sm" : "border-border bg-surface-2 text-content hover:border-primary hover:bg-surface",
      )}
    >
      <span className="block text-sm font-semibold">{screen.title}</span>
      <span className="block text-xs text-content-muted">
        {status}
      </span>
    </button>
  );
}

function ReviewEditorTabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-md border px-3 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20",
        active ? "border-primary bg-surface text-content shadow-sm" : "border-border bg-surface-2 text-content-muted hover:border-primary hover:text-content",
      )}
    >
      {label}
    </button>
  );
}

function ConnectedSocialPanel({ assets, onClose }: { assets: ProviderAssetSummary[]; onClose: () => void }) {
  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-divider p-4">
        <div>
          <h2 className="text-md font-semibold text-content">Connected Social</h2>
          <p className="text-sm text-content-muted">Provider assets synced into MOS for agent-visible context.</p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Close connected social panel" onClick={onClose}>
          <X className="size-4" />
        </Button>
      </div>
      <div className="p-4">
        <Table variant="surface">
          <TableHeader>
            <TableRow>
              <TableHeadCell>Provider</TableHeadCell>
              <TableHeadCell>Asset</TableHeadCell>
              <TableHeadCell>Type</TableHeadCell>
              <TableHeadCell>Status</TableHeadCell>
              <TableHeadCell>Capabilities</TableHeadCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {assets.map((asset) => (
              <TableRow key={asset.id}>
                <TableCell>{asset.provider}</TableCell>
                <TableCell>{asset.displayName}</TableCell>
                <TableCell>{asset.assetType}</TableCell>
                <TableCell>
                  <Badge tone={toneForStatus(asset.status)}>{asset.status}</Badge>
                </TableCell>
                <TableCell>{asset.capabilityFlags?.length ? asset.capabilityFlags.join(", ") : "none"}</TableCell>
              </TableRow>
            ))}
            {!assets.length ? (
              <TableRow>
                <TableCell colSpan={5} className="text-content-muted">
                  No connected social assets have been synced into MOS yet.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

function ActionQueuePanel({
  proposals,
  approvePending,
  onApprove,
  onClose,
}: {
  proposals: ActionProposalSummary[];
  approvePending: boolean;
  onApprove: (proposalId: string) => void;
  onClose: () => void;
}) {
  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-divider p-4">
        <div>
          <h2 className="text-md font-semibold text-content">Action Queue</h2>
          <p className="text-sm text-content-muted">Agent proposals stay approval-gated before Postiz work happens.</p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Close action queue panel" onClick={onClose}>
          <X className="size-4" />
        </Button>
      </div>
      <div className="p-4">
        <Table variant="surface">
          <TableHeader>
            <TableRow>
              <TableHeadCell>Action</TableHeadCell>
              <TableHeadCell>Provider</TableHeadCell>
              <TableHeadCell>Risk</TableHeadCell>
              <TableHeadCell>Status</TableHeadCell>
              <TableHeadCell>Target</TableHeadCell>
              <TableHeadCell>Review</TableHeadCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {proposals.map((proposal) => (
              <TableRow key={proposal.id}>
                <TableCell>{proposal.actionType}</TableCell>
                <TableCell>{proposal.targetProvider}</TableCell>
                <TableCell>{proposal.riskLabel || "unlabeled"}</TableCell>
                <TableCell>
                  <Badge tone={toneForStatus(proposal.status)}>{proposal.status}</Badge>
                </TableCell>
                <TableCell>{proposal.targetAssetId || proposal.targetAssetType || "Postiz"}</TableCell>
                <TableCell>
                  <Button
                    size="xs"
                    variant="secondary"
                    onClick={() => onApprove(proposal.id)}
                    disabled={proposal.status !== "pending" || approvePending}
                  >
                    Approve
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!proposals.length ? (
              <TableRow>
                <TableCell colSpan={6} className="text-content-muted">
                  No action proposals yet.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

function AgentDossierRail({
  missionName,
  missionObjective,
  postizReady,
  selectedChannelName,
  selectedVariantStatus,
  assetCount,
  requiredAssetCount,
  blocker,
  pendingProposalCount,
}: {
  missionName: string;
  missionObjective: string;
  postizReady: boolean;
  selectedChannelName: string;
  selectedVariantStatus: string;
  assetCount: number;
  requiredAssetCount: number;
  blocker: string;
  pendingProposalCount: number;
}) {
  const assetTotal = requiredAssetCount || 6;
  const rows = [
    { label: "Mission", value: missionName || "Not set" },
    { label: "Channel", value: selectedChannelName || "No channel" },
    { label: "Draft", value: selectedVariantStatus || "Not created" },
    { label: "Assets", value: `${assetCount}/${assetTotal}` },
  ];

  return (
    <aside className="min-w-0 space-y-4 rounded-lg border border-border bg-surface p-4 xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:self-start xl:overflow-y-auto">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-normal text-content-muted">Agent</div>
          <h2 className="mt-1 text-lg font-semibold text-content">TikTok carousel</h2>
        </div>
        <Badge tone="neutral">Postiz</Badge>
      </div>

      <div className="flex flex-wrap gap-2">
        <Badge tone={postizReady ? "success" : "warning"}>{postizReady ? "Connected" : "Needs channel"}</Badge>
        <Badge tone="neutral">Approval required</Badge>
        {pendingProposalCount ? <Badge tone="warning">{pendingProposalCount} pending</Badge> : null}
      </div>

      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.label} className="border-t border-divider pt-3">
            <div className="text-xs font-medium uppercase tracking-normal text-content-muted">{row.label}</div>
            <div className="mt-1 line-clamp-2 text-sm font-medium text-content">{row.value}</div>
          </div>
        ))}
      </div>

      {missionObjective ? (
        <div className="rounded-md border border-border bg-surface-2 p-3">
          <div className="text-xs font-medium uppercase tracking-normal text-content-muted">Goal</div>
          <p className="mt-1 line-clamp-3 text-sm text-content">{missionObjective}</p>
        </div>
      ) : null}

      <div className="rounded-md border border-warning/30 bg-warning-bg p-3 text-sm">
        <div className="font-semibold text-content">Next</div>
        <div className="mt-1 text-content-muted">{blocker}</div>
      </div>
    </aside>
  );
}

function stripEmoji(value: string) {
  return value.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "").trim();
}

function wrapCanvasText(context: CanvasRenderingContext2D, value: string, maxWidth: number) {
  const lines: string[] = [];
  const manualLines = stripEmoji(value)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  for (const manualLine of manualLines) {
    if (context.measureText(manualLine).width <= maxWidth) {
      lines.push(manualLine);
      continue;
    }
    const words = manualLine.split(/\s+/);
    let currentLine = "";
    for (const word of words) {
      const candidate = currentLine ? `${currentLine} ${word}` : word;
      if (context.measureText(candidate).width <= maxWidth) {
        currentLine = candidate;
      } else {
        if (currentLine) lines.push(currentLine);
        currentLine = word;
      }
    }
    if (currentLine) lines.push(currentLine);
  }
  return lines;
}

function loadImageFromUrl(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    if (!src.startsWith("data:")) image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Unable to load source image: ${src.slice(0, 80)}`));
    image.src = src;
  });
}

function drawImageCover(context: CanvasRenderingContext2D, image: HTMLImageElement, width: number, height: number) {
  const imageRatio = image.width / image.height;
  const canvasRatio = width / height;
  const drawHeight = imageRatio > canvasRatio ? height : width / imageRatio;
  const drawWidth = imageRatio > canvasRatio ? height * imageRatio : width;
  const x = (width - drawWidth) / 2;
  const y = (height - drawHeight) / 2;
  context.drawImage(image, x, y, drawWidth, drawHeight);
}

async function renderCarouselAsset({
  imageSrc,
  overlayText,
  slideIndex,
}: {
  imageSrc: string;
  overlayText: string;
  slideIndex: number;
}) {
  const image = await loadImageFromUrl(imageSrc);
  const canvas = document.createElement("canvas");
  canvas.width = RENDERED_ASSET_WIDTH;
  canvas.height = RENDERED_ASSET_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Browser canvas renderer is unavailable.");

  drawImageCover(context, image, canvas.width, canvas.height);

  const fontSize = Math.round(canvas.width * 0.065);
  const outlineWidth = Math.round(fontSize * 0.15);
  const maxWidth = canvas.width * 0.75;
  const lineHeight = fontSize * 1.25;

  context.font = `900 ${fontSize}px Inter, Arial, sans-serif`;
  context.textAlign = "center";
  context.textBaseline = "top";

  const lines = wrapCanvasText(context, overlayText, maxWidth);
  const totalTextHeight = lines.length * lineHeight;
  const centeredY = canvas.height * 0.3 - totalTextHeight / 2 + lineHeight / 2;
  const minY = canvas.height * 0.1;
  const maxY = canvas.height * 0.8 - totalTextHeight;
  const safeY = Math.max(minY, Math.min(centeredY, maxY));
  const x = canvas.width / 2;

  for (let index = 0; index < lines.length; index += 1) {
    const y = safeY + index * lineHeight;
    context.strokeStyle = "#000000";
    context.lineWidth = outlineWidth;
    context.lineJoin = "round";
    context.miterLimit = 2;
    context.strokeText(lines[index], x, y);
    context.fillStyle = "#ffffff";
    context.fillText(lines[index], x, y);
  }

  return {
    slideIndex,
    dataUrl: canvas.toDataURL("image/png"),
    filename: `tiktok-carousel-slide-${slideIndex}.png`,
  };
}

export function SocialAgentsPage() {
  const { workspace } = useWorkspace();
  const { post } = useApiClient();
  const clientId = workspace?.id;

  const { data: programs = [] } = useGrowthPrograms(clientId);
  const { data: postizChannels = [] } = useClientPostizChannels(clientId);
  const { data: postizProfiles = [] } = useClientPostizPostingProfiles(clientId);
  const { data: providerAssets = [] } = useSocialProviderAssets(clientId);
  const { data: proposals = [] } = useAgentActionProposals(clientId);

  const [selectedProgramId, setSelectedProgramId] = useState("");
  const selectedProgram = useMemo(
    () => programs.find((program) => program.id === selectedProgramId) || programs[0] || null,
    [programs, selectedProgramId],
  );
  const programId = selectedProgram?.id;

  const { data: conversionSources = [] } = useConversionSources(clientId, programId);
  const { data: experiments = [] } = useContentExperiments(clientId, programId);
  const { data: variants = [] } = useContentVariants(clientId, programId);
  const selectedVariant = latestVariant(variants);

  const createProgram = useCreateGrowthProgram(clientId);
  const createConversionSource = useCreateConversionSource(clientId, programId);
  const createExperiment = useCreateContentExperiment(clientId, programId);
  const createVariant = useCreateContentVariant(clientId, programId);
  const approveVariant = useApproveContentVariant(clientId, programId);
  const approveProposal = useApproveAgentActionProposal(clientId);
  const createHandoff = useCreatePostizHandoffProposal(clientId, programId);

  const [programName, setProgramName] = useState("TikTok Carousel Growth Loop");
  const [programObjective, setProgramObjective] = useState("Find carousel hooks that create source-backed conversions.");
  const [sourceProvider, setSourceProvider] = useState("custom_webhook");
  const [sourceName, setSourceName] = useState("Primary conversion event");
  const [goalEvents, setGoalEvents] = useState("trial_started\npurchase_completed");
  const [experimentName, setExperimentName] = useState("Hook test batch");
  const [hypothesis, setHypothesis] = useState("Problem-aware hooks will outperform generic feature hooks.");
  const [hookFamily, setHookFamily] = useState("problem_aware");
  const [ctaFamily, setCtaFamily] = useState("soft_app_name");
  const [variantTitle, setVariantTitle] = useState("Larry-style six-slide carousel");
  const [variantCaption, setVariantCaption] = useState(
    "POV: your routine looks calm but your brain missed the memo. So I found this app that helps turn the reset into a cleaner loop. Try the app - link in bio.",
  );
  const [variantCta, setVariantCta] = useState("Try the app - link in bio");
  const [basePrompt, setBasePrompt] = useState(DEFAULT_BASE_PROMPT);
  const [slideText, setSlideText] = useState(LARRY_SLIDE_FORMULA.map((slide) => slide.defaultText).join("\n---\n"));
  const [sourceImageUrls, setSourceImageUrls] = useState("");
  const [isGeneratingSourceImages, setIsGeneratingSourceImages] = useState(false);
  const [renderedAssets, setRenderedAssets] = useState<RenderedCarouselAsset[]>([]);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isRenderingAssets, setIsRenderingAssets] = useState(false);
  const [mediaUrls, setMediaUrls] = useState("");
  const [selectedChannelIds, setSelectedChannelIds] = useState<string[]>([]);
  const [postType, setPostType] = useState<"draft" | "schedule" | "now">("draft");
  const [activePanel, setActivePanel] = useState<PanelKey>(null);
  const [activeScreenId, setActiveScreenId] = useState<AgentScreenId>("setup");
  const [reviewEditorOpen, setReviewEditorOpen] = useState(false);
  const [reviewEditorTab, setReviewEditorTab] = useState<ReviewEditorTab>("assets");

  useEffect(() => {
    if (!selectedProgramId && programs[0]) setSelectedProgramId(programs[0].id);
  }, [programs, selectedProgramId]);

  useEffect(() => {
    if (!selectedChannelIds.length && postizChannels[0]) {
      setSelectedChannelIds([postizChannels[0].id]);
    }
  }, [postizChannels, selectedChannelIds.length]);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Social Agents" description="Select a workspace to manage connected social agents." />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to open the agent workbench."
          actions={<InlineWorkspacePicker />}
        />
      </div>
    );
  }

  const postizReady = postizChannels.length > 0 || postizProfiles.length > 0;
  const slideLines = splitSlideEntries(slideText).slice(0, 6);
  const sourceImageUrlLines = splitLines(sourceImageUrls);
  const mediaUrlLines = splitLines(mediaUrls);
  const canCreateVariant = Boolean(programId && experiments[0] && slideLines.length === 6);
  const canRenderAssets = Boolean(slideLines.length === 6 && sourceImageUrlLines.length === 6);
  const requiredMediaUrlCount = selectedVariant?.slideCount || 0;
  const handoffMediaReady = Boolean(
    selectedVariant && requiredMediaUrlCount > 0 && mediaUrlLines.length === requiredMediaUrlCount,
  );
  const canCreateHandoff = Boolean(programId && selectedVariant?.status === "approved" && handoffMediaReady);
  const draftPreviewSlides = LARRY_SLIDE_FORMULA.map((slide, index) => ({
    ...slide,
    overlayText: textForSlide(slideLines, index),
  }));
  const pendingProposalCount = proposals.filter((proposal) => proposal.status === "pending").length;
  const handoffBlockReason = !selectedVariant
    ? "Create a draft before sending to Postiz."
    : selectedVariant.status !== "approved"
      ? "Approve the draft before sending to Postiz."
      : !handoffMediaReady
        ? `Add ${requiredMediaUrlCount || 6} assets.`
        : null;
  const selectedChannelName =
    postizChannels.find((channel) => channel.id === selectedChannelIds[0])?.name || postizChannels[0]?.name || "";
  const setupStatus = programId ? "Mission set" : "Needs mission";
  const reviewStatus = canCreateHandoff
    ? "Ready"
    : selectedVariant
      ? selectedVariant.status
      : experiments[0]
        ? "Draft needed"
        : "Test needed";
  const assetCount = handoffMediaReady ? mediaUrlLines.length : renderedAssets.length || sourceImageUrlLines.length;
  const primaryBlocker = !programId
    ? "Set the mission."
    : !experiments[0]
      ? "Create the first test."
      : !selectedVariant
        ? "Create the draft."
        : selectedVariant.status !== "approved"
          ? "Approve the draft."
          : !handoffMediaReady
            ? `Add ${requiredMediaUrlCount || 6} assets.`
            : "Ready for Postiz.";
  const reviewPrimaryLabel = !programId
    ? "Set mission"
    : !experiments[0]
      ? "Start test"
      : !selectedVariant
        ? "Build draft"
        : selectedVariant.status !== "approved"
          ? "Approve draft"
          : renderedAssets.length === 6 && !handoffMediaReady
            ? "Use assets"
            : sourceImageUrlLines.length === 6 && !handoffMediaReady
              ? "Render assets"
              : !handoffMediaReady
                ? "Add assets"
                : "Send to Postiz";
  const reviewPrimaryPending =
    createExperiment.isPending ||
    createVariant.isPending ||
    approveVariant.isPending ||
    createHandoff.isPending ||
    isGeneratingSourceImages ||
    isRenderingAssets;
  const reviewPrimaryShortLabel =
    reviewPrimaryLabel === "Set mission"
      ? "Setup"
      : reviewPrimaryLabel === "Start test"
        ? "Test"
        : reviewPrimaryLabel === "Build draft"
          ? "Draft"
          : reviewPrimaryLabel === "Approve draft"
            ? "Approve"
            : reviewPrimaryLabel === "Use assets"
              ? "Use"
              : reviewPrimaryLabel === "Render assets"
                ? "Render"
                : reviewPrimaryLabel === "Add assets"
                  ? "Assets"
                  : "Send";
  const visualSlides = draftPreviewSlides.map((slide, index) => {
    const renderedAsset = renderedAssets.find((asset) => asset.slideIndex === index + 1);
    const sourceImageUrl = sourceImageUrlLines[index];
    const mediaUrl = renderedAsset?.dataUrl || sourceImageUrl;
    return {
      ...slide,
      mediaUrl,
      assetStatus: renderedAsset ? "Rendered" : sourceImageUrl ? "Image" : "Missing",
    };
  });

  const openReviewEditor = (tab: ReviewEditorTab) => {
    setReviewEditorTab(tab);
    setReviewEditorOpen(true);
  };

  const handleCreateProgram = async () => {
    const program = await createProgram.mutateAsync({
      name: programName,
      objective: programObjective,
      platformKey: "tiktok",
      formatKey: "tiktok_carousel",
      authorityMode: "approval_required",
      settings: { postizSystemOfRecord: true },
      metadata: { source: "social_agents_page" },
    });
    setSelectedProgramId(program.id);
    setActiveScreenId("review");
  };

  const handleCreateSource = async () => {
    await createConversionSource.mutateAsync({
      provider: sourceProvider,
      name: sourceName,
      goalEvents: splitLines(goalEvents),
      config: {},
      credentialsMetadata: { configuredIn: "mos" },
    });
  };

  const handleCreateExperiment = async () => {
    await createExperiment.mutateAsync({
      name: experimentName,
      hypothesis,
      hookFamily,
      ctaFamily,
      audience: "workspace audience",
    });
    setActiveScreenId("review");
  };

  const handleCreateVariant = async () => {
    await createVariant.mutateAsync({
      experimentId: experiments[0]?.id,
      title: variantTitle,
      caption: variantCaption,
      cta: variantCta,
      slideCount: 6,
      storyboard: {
        source: "larry_style_operator_draft",
        formula: "larry_tiktok_six_slide_v1",
        basePrompt,
        slideStructure: LARRY_SLIDE_FORMULA.map(({ visualRole, purpose, stylePrompt }) => ({
          visualRole,
          purpose,
          stylePrompt,
        })),
      },
      slides: LARRY_SLIDE_FORMULA.map((slide, index) => ({
        slideIndex: index + 1,
        visualRole: slide.visualRole,
        prompt: `${basePrompt}\n\n${slide.stylePrompt}`,
        overlayText: textForSlide(slideLines, index),
        metadata: { purpose: slide.purpose, formula: "larry_tiktok_six_slide_v1" },
      })),
    });
    setActiveScreenId("review");
  };

  const handleApproveVariant = async () => {
    if (!selectedVariant) return;
    await approveVariant.mutateAsync({ variantId: selectedVariant.id, notes: "Approved from Social Agents page" });
  };

  const handleGenerateSourceImages = async () => {
    setRenderError(null);
    if (slideLines.length !== 6) {
      setRenderError("Add exactly six slide text entries separated by --- before generating source images.");
      return;
    }
    if (!clientId) {
      setRenderError("Workspace client ID is required to generate source images.");
      return;
    }
    setIsGeneratingSourceImages(true);
    try {
      const apiBaseUrl = resolveRequiredApiBaseUrl();
      const outputs = await Promise.all(
        LARRY_SLIDE_FORMULA.map((slide, index) =>
          post<GeneratedImageAsset>("/assets/generate-image", {
            clientId,
            prompt: `${basePrompt}\n\n${slide.stylePrompt}`,
            aspectRatio: "9:16",
            usageContext: {
              source: "social_agents_page",
              formula: "larry_tiktok_six_slide_v1",
              slideIndex: index + 1,
              visualRole: slide.visualRole,
            },
          }),
        ),
      );
      setSourceImageUrls(outputs.map((asset) => new URL(asset.url, apiBaseUrl).toString()).join("\n"));
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : "Failed to generate source images.");
    } finally {
      setIsGeneratingSourceImages(false);
    }
  };

  const handleRenderAssets = async () => {
    setRenderError(null);
    setRenderedAssets([]);
    if (slideLines.length !== 6) {
      setRenderError("Add exactly six slide text entries separated by --- before rendering assets.");
      return;
    }
    if (sourceImageUrlLines.length !== 6) {
      setRenderError("Add exactly six source image URLs or data URLs before rendering final assets.");
      return;
    }
    setIsRenderingAssets(true);
    try {
      const outputs = await Promise.all(
        sourceImageUrlLines.map((imageSrc, index) =>
          renderCarouselAsset({
            imageSrc,
            overlayText: textForSlide(slideLines, index),
            slideIndex: index + 1,
          }),
        ),
      );
      setRenderedAssets(outputs);
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : "Failed to render carousel assets.");
    } finally {
      setIsRenderingAssets(false);
    }
  };

  const handleUseRenderedDataUrls = () => {
    if (!renderedAssets.length) return;
    setMediaUrls(renderedAssets.map((asset) => asset.dataUrl).join("\n"));
    setActiveScreenId("review");
  };

  const handleCreateHandoff = async () => {
    if (!selectedVariant) return;
    await createHandoff.mutateAsync({
      variantId: selectedVariant.id,
      payload: {
        content: variantCaption,
        postType,
        channelIds: selectedChannelIds,
        mediaUrls: mediaUrlLines,
        providerSettingsByIdentifier: {},
        metadata: { createdFrom: "social_agents_page" },
      },
    });
  };

  const handleApproveProposal = async (proposalId: string) => {
    await approveProposal.mutateAsync({ proposalId, notes: "Approved from Social Agents action queue" });
  };

  const handleSetupPrimaryAction = async () => {
    if (programId) {
      setActiveScreenId("review");
      return;
    }
    await handleCreateProgram();
  };

  const handleReviewPrimaryAction = async () => {
    if (!programId) {
      setActiveScreenId("setup");
      return;
    }
    if (!experiments[0]) {
      await handleCreateExperiment();
      return;
    }
    if (!selectedVariant) {
      await handleCreateVariant();
      return;
    }
    if (selectedVariant.status !== "approved") {
      await handleApproveVariant();
      return;
    }
    if (renderedAssets.length === 6 && !handoffMediaReady) {
      handleUseRenderedDataUrls();
      return;
    }
    if (sourceImageUrlLines.length === 6 && !handoffMediaReady) {
      await handleRenderAssets();
      return;
    }
    if (!handoffMediaReady) {
      openReviewEditor("assets");
      return;
    }
    await handleCreateHandoff();
  };

  const agentDossier = (
    <AgentDossierRail
      missionName={selectedProgram?.name || programName}
      missionObjective={selectedProgram?.objective || programObjective}
      postizReady={postizReady}
      selectedChannelName={selectedChannelName}
      selectedVariantStatus={selectedVariant?.status || ""}
      assetCount={assetCount}
      requiredAssetCount={requiredMediaUrlCount}
      blocker={primaryBlocker}
      pendingProposalCount={pendingProposalCount}
    />
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Marketing Agent"
        description={`Approval-gated TikTok carousel work for ${workspace.name}.`}
        actions={
          <Button asChild variant="secondary" size="sm">
            <Link to="/workspaces/execution/postiz">
              <ExternalLink className="size-4" />
              Postiz
            </Link>
          </Button>
        }
      />

      <section className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <Badge tone={postizReady ? "success" : "warning"}>
            <ShieldCheck className="size-3.5" />
            {postizReady ? "Postiz ready" : "Postiz needs channels"}
          </Badge>
          <span className="text-sm text-content-muted">
            {postizChannels.length} channels, {postizProfiles.length} profiles
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="xs"
            variant="secondary"
            onClick={() => setActivePanel(activePanel === "queue" ? null : "queue")}
          >
            <ListChecks className="size-4" />
            Approvals
            <Badge tone={pendingProposalCount ? "warning" : "success"}>{pendingProposalCount}</Badge>
          </Button>
          <Button
            size="xs"
            variant="secondary"
            onClick={() => setActivePanel(activePanel === "connected" ? null : "connected")}
          >
            <Bot className="size-4" />
            Channels
          </Button>
          <Button
            size="xs"
            variant="secondary"
            onClick={() => setActivePanel(activePanel === "dossier" ? null : "dossier")}
          >
            <Settings2 className="size-4" />
            Agent
          </Button>
        </div>
      </section>

      {activePanel === "connected" ? (
        <ConnectedSocialPanel assets={providerAssets} onClose={() => setActivePanel(null)} />
      ) : null}
      {activePanel === "queue" ? (
        <ActionQueuePanel
          proposals={proposals}
          approvePending={approveProposal.isPending}
          onApprove={handleApproveProposal}
          onClose={() => setActivePanel(null)}
        />
      ) : null}
      {activePanel === "dossier" ? agentDossier : null}

      <section className={cn("grid gap-5", activeScreenId === "setup" ? "xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]" : "")}>
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <div className="border-b border-divider p-4 lg:p-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{activeScreenId === "setup" ? "Step 1 of 2" : "Step 2 of 2"}</Badge>
                  <Badge tone={activeScreenId === "setup" ? (programId ? "success" : "warning") : canCreateHandoff ? "success" : "warning"}>
                    {activeScreenId === "setup" ? setupStatus : reviewStatus}
                  </Badge>
                </div>
                <h2 className="text-xl font-semibold text-content">
                  {activeScreenId === "setup" ? "Set mission" : "Review carousel"}
                </h2>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {AGENT_SCREENS.map((screen) => (
                  <AgentScreenButton
                    key={screen.id}
                    active={screen.id === activeScreenId}
                    status={screen.id === "setup" ? setupStatus : reviewStatus}
                    screen={screen}
                    onClick={() => setActiveScreenId(screen.id)}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="p-4 lg:p-6">
            {activeScreenId === "setup" ? (
              <div className="space-y-6">
                <div className="grid gap-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium uppercase tracking-normal text-content-muted">Name</div>
                      <Input aria-label="Agent name" value={programName} onChange={(event) => setProgramName(event.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium uppercase tracking-normal text-content-muted">Saved mission</div>
                      <Select
                        aria-label="Saved mission"
                        value={selectedProgram?.id || ""}
                        onValueChange={setSelectedProgramId}
                        options={[
                          { label: programs.length ? "Select mission" : "No missions yet", value: "", disabled: true },
                          ...programs.map((program) => ({ label: program.name, value: program.id })),
                        ]}
                      />
                    </div>
                    <div className="space-y-1.5 md:col-span-2">
                      <div className="text-xs font-medium uppercase tracking-normal text-content-muted">Mission</div>
                      <Textarea
                        aria-label="Agent mission"
                        value={programObjective}
                        onChange={(event) => setProgramObjective(event.target.value)}
                        className="min-h-[92px]"
                      />
                    </div>
                  </div>

                  <div className="rounded-md border border-border bg-surface-2 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-content">Current</span>
                      {selectedProgram ? <Badge tone={toneForStatus(selectedProgram.status)}>{selectedProgram.status}</Badge> : <Badge tone="warning">Needed</Badge>}
                    </div>
                    {selectedProgram ? (
                      <div className="mt-3 space-y-2 text-sm">
                        <div className="font-medium text-content">{selectedProgram.name}</div>
                        <div className="line-clamp-4 text-content-muted">{selectedProgram.objective}</div>
                      </div>
                    ) : (
                      <div className="mt-3 text-sm text-content-muted">No mission saved.</div>
                    )}
                  </div>
                </div>

                <div className="border-t border-divider pt-5">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-md font-semibold text-content">Success signal</h3>
                      <div className="mt-1 text-sm text-content-muted">{conversionSources[0]?.name || "Optional until you connect live results."}</div>
                    </div>
                    <Badge tone={conversionSources.length ? "success" : "neutral"}>
                      {conversionSources.length ? "Linked" : "Not linked"}
                    </Badge>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <Input aria-label="Signal provider" value={sourceProvider} onChange={(event) => setSourceProvider(event.target.value)} />
                    <Input aria-label="Signal name" value={sourceName} onChange={(event) => setSourceName(event.target.value)} />
                    <Textarea aria-label="Goal events" value={goalEvents} onChange={(event) => setGoalEvents(event.target.value)} className="min-h-20 md:col-span-2" />
                    <Button className="md:justify-self-start" variant="secondary" onClick={handleCreateSource} disabled={!programId || createConversionSource.isPending}>
                      <Link2 className="size-4" />
                      Save signal
                    </Button>
                  </div>
                </div>

                <Button onClick={handleSetupPrimaryAction} disabled={createProgram.isPending || !programName.trim() || !programObjective.trim()}>
                  <Plus className="size-4" />
                  Continue
                </Button>
              </div>
            ) : null}

            {activeScreenId === "review" ? (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="flex min-w-0 flex-wrap gap-2">
                    <Badge data-testid="review-status-badge" className="justify-center" tone={experiments[0] ? "success" : "warning"}>{experiments[0] ? "Test" : "No test"}</Badge>
                    <Badge data-testid="review-status-badge" className="justify-center" tone={selectedVariant ? toneForStatus(selectedVariant.status) : "warning"}>{selectedVariant?.status || "Draft"}</Badge>
                    <Badge data-testid="review-status-badge" className="justify-center" tone={handoffMediaReady ? "success" : "warning"}>{assetCount}/{requiredMediaUrlCount || 6}</Badge>
                    <Badge data-testid="review-status-badge" className="justify-center" tone={canCreateHandoff ? "success" : "warning"}>Postiz</Badge>
                  </div>
                  <Button
                    data-testid="review-primary-cta"
                    aria-label={reviewPrimaryLabel}
                    onClick={handleReviewPrimaryAction}
                    disabled={reviewPrimaryPending || (reviewPrimaryLabel === "Build draft" && !canCreateVariant)}
                  >
                    {reviewPrimaryLabel === "Send to Postiz" ? (
                      <Send className="size-4" />
                    ) : reviewPrimaryLabel === "Approve draft" ? (
                      <CheckCircle2 className="size-4" />
                    ) : reviewPrimaryLabel === "Render assets" ? (
                      <Sparkles className="size-4" />
                    ) : (
                      <Plus className="size-4" />
                    )}
                    {reviewPrimaryShortLabel}
                  </Button>
                </div>

                {programId ? (
                  <>
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))] gap-4">
                      {visualSlides.map((slide, index) => (
                        <CarouselSlideCard
                          key={slide.visualRole}
                          index={index + 1}
                          purpose={slide.purpose}
                          text={slide.overlayText}
                          mediaUrl={slide.mediaUrl}
                          assetStatus={slide.assetStatus}
                          draftStatus={selectedVariant?.status === "approved" ? "Approved" : selectedVariant ? "Draft" : "Needed"}
                          onEdit={() => openReviewEditor("draft")}
                          onAsset={() => openReviewEditor("assets")}
                          onRegenerate={handleGenerateSourceImages}
                          onApprove={handleApproveVariant}
                          regenerateDisabled={slideLines.length !== 6 || isGeneratingSourceImages}
                          approveDisabled={!selectedVariant || selectedVariant.status === "approved" || approveVariant.isPending}
                        />
                      ))}
                    </div>

                    <div className="sticky bottom-4 z-10 rounded-lg border border-border bg-surface/95 p-2 shadow-lg backdrop-blur">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap gap-2">
                          <Button size="xs" variant="secondary" onClick={() => openReviewEditor("assets")}>
                            <ImagePlus className="size-4" />
                            Media
                          </Button>
                          <Button
                            data-testid="review-generate-images"
                            size="xs"
                            variant="secondary"
                            onClick={handleGenerateSourceImages}
                            disabled={slideLines.length !== 6 || isGeneratingSourceImages}
                          >
                            <RefreshCw className="size-4" />
                            Generate
                          </Button>
                          <Button
                            data-testid="review-render-assets"
                            size="xs"
                            variant="secondary"
                            onClick={handleRenderAssets}
                            disabled={!canRenderAssets || isRenderingAssets}
                          >
                            <Sparkles className="size-4" />
                            Render
                          </Button>
                          <Button
                            data-testid="review-use-rendered"
                            size="xs"
                            variant="secondary"
                            onClick={handleUseRenderedDataUrls}
                            disabled={renderedAssets.length !== 6}
                          >
                            <Check className="size-4" />
                            Use
                          </Button>
                        </div>
                        <Button size="xs" variant="ghost" onClick={() => setReviewEditorOpen((open) => !open)} aria-expanded={reviewEditorOpen}>
                          <Settings2 className="size-4" />
                          Editor
                          <ChevronDown className={cn("size-4 transition", reviewEditorOpen ? "rotate-180" : "")} />
                        </Button>
                      </div>
                      {renderError ? <div className="mt-2 text-sm text-danger">{renderError}</div> : null}
                    </div>

                    {reviewEditorOpen ? (
                      <section className="rounded-lg border border-border bg-surface-2 p-3">
                        <div className="mb-3 flex flex-wrap gap-2">
                          {REVIEW_EDITOR_TABS.map((tab) => (
                            <ReviewEditorTabButton
                              key={tab.id}
                              active={reviewEditorTab === tab.id}
                              label={tab.label}
                              onClick={() => setReviewEditorTab(tab.id)}
                            />
                          ))}
                        </div>

                        {reviewEditorTab === "test" ? (
                          <div className="grid gap-3 md:grid-cols-2">
                            <Input aria-label="Test name" value={experimentName} onChange={(event) => setExperimentName(event.target.value)} />
                            <Input aria-label="Test hypothesis" value={hypothesis} onChange={(event) => setHypothesis(event.target.value)} />
                            <Input aria-label="Hook family" value={hookFamily} onChange={(event) => setHookFamily(event.target.value)} />
                            <Input aria-label="CTA family" value={ctaFamily} onChange={(event) => setCtaFamily(event.target.value)} />
                          </div>
                        ) : null}

                        {reviewEditorTab === "draft" ? (
                          <div className="grid gap-3 md:grid-cols-3">
                            <Input aria-label="Draft title" value={variantTitle} onChange={(event) => setVariantTitle(event.target.value)} />
                            <Input aria-label="Draft caption" value={variantCaption} onChange={(event) => setVariantCaption(event.target.value)} />
                            <Input aria-label="Draft CTA" value={variantCta} onChange={(event) => setVariantCta(event.target.value)} />
                            <Textarea
                              aria-label="Slide overlay text"
                              value={slideText}
                              onChange={(event) => setSlideText(event.target.value)}
                              className="min-h-[180px] md:col-span-3"
                            />
                            <Textarea
                              aria-label="Base image prompt"
                              value={basePrompt}
                              onChange={(event) => setBasePrompt(event.target.value)}
                              className="min-h-[96px] md:col-span-3"
                            />
                          </div>
                        ) : null}

                        {reviewEditorTab === "assets" ? (
                          <div className="grid gap-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge tone={canRenderAssets ? "success" : "warning"}>{sourceImageUrlLines.length}/6 source</Badge>
                              <Badge tone={handoffMediaReady ? "success" : "warning"}>{mediaUrlLines.length}/{requiredMediaUrlCount || 6} media</Badge>
                            </div>
                            <Textarea
                              aria-label="Source image URLs"
                              value={sourceImageUrls}
                              onChange={(event) => setSourceImageUrls(event.target.value)}
                              className="min-h-[120px]"
                            />
                            <Textarea
                              id="carousel-media-urls"
                              aria-label="Carousel media URLs"
                              value={mediaUrls}
                              onChange={(event) => setMediaUrls(event.target.value)}
                              className="min-h-[120px]"
                            />
                          </div>
                        ) : null}

                        {reviewEditorTab === "postiz" ? (
                          <div className="grid gap-3 md:grid-cols-2">
                            {handoffBlockReason ? <span className="text-sm text-warning md:col-span-2">{handoffBlockReason}</span> : null}
                            <Select
                              aria-label="Post type"
                              value={postType}
                              onValueChange={(value) => setPostType(value as "draft" | "schedule" | "now")}
                              options={[
                                { label: "Draft", value: "draft" },
                                { label: "Schedule", value: "schedule" },
                                { label: "Now", value: "now" },
                              ]}
                            />
                            <Select
                              aria-label="Postiz channel"
                              value={selectedChannelIds[0] || ""}
                              onValueChange={(value) => setSelectedChannelIds(value ? [value] : [])}
                              options={[
                                { label: postizChannels.length ? "Select channel" : "No synced channels", value: "", disabled: true },
                                ...postizChannels.map((channel) => ({ label: channel.name, value: channel.id, disabled: channel.disabled })),
                              ]}
                            />
                            <Button
                              data-testid="review-postiz-handoff"
                              className="md:justify-self-start"
                              variant="secondary"
                              onClick={handleCreateHandoff}
                              disabled={!canCreateHandoff || createHandoff.isPending}
                            >
                              <Send className="size-4" />
                              Send
                            </Button>
                          </div>
                        ) : null}
                      </section>
                    ) : null}
                  </>
                ) : (
                  <div className="border-t border-divider pt-6">
                    <h3 className="text-md font-semibold text-content">Mission needed</h3>
                    <p className="mt-2 text-sm text-content-muted">
                      Set the mission before reviewing drafts, assets, or Postiz delivery.
                    </p>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>

        {activeScreenId === "setup" ? agentDossier : null}
      </section>
    </div>
  );
}

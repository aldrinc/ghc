import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { StrategyV2Candidate, StrategyV2PendingSignal } from "../StrategyV2ReviewWorkspace";

type GateDecisionControlsProps = {
  pendingSignal: StrategyV2PendingSignal;
  candidates: StrategyV2Candidate[];
  reviewedSet: Set<string>;

  // Gate 1: proceed/hold
  proceedResearch: boolean;
  onProceedResearchChange: (value: boolean) => void;

  // Gate 2: confirm competitor assets
  confirmedAssetRefs: string[];
  onToggleAssetRef: (ref: string) => void;
  competitorAssetPolicy: { min: number; max: number; target?: number };

  // Gate 3: select angle
  selectedAngleId: string;
  onAngleChange: (id: string) => void;

  // Gate 4: select UMP/UMS
  selectedPairId: string;
  onPairChange: (id: string) => void;

  // Gate 5: select offer winner
  selectedVariantId: string;
  onVariantChange: (id: string) => void;

  // Gate 6: approve/reject final copy
  finalCopyApproved: boolean;
  onFinalCopyChange: (value: boolean) => void;

  // Shared
  onOpenCandidate: (candidateId: string) => void;
};

/**
 * Renders the gate-specific decision controls (radio, checkbox, toggle)
 * for each of the 6 Strategy V2 gates.
 */
export function GateDecisionControls(props: GateDecisionControlsProps) {
  const { pendingSignal, candidates, reviewedSet, onOpenCandidate } = props;

  return (
    <div className="ds-card ds-card--md space-y-3">
      <div className="text-sm font-semibold text-content">Decide</div>

      {/* Gate 1: Proceed Research */}
      {pendingSignal === "strategy_v2_proceed_research" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={props.proceedResearch ? "primary" : "secondary"}
            size="sm"
            onClick={() => props.onProceedResearchChange(true)}
          >
            Proceed
          </Button>
          <Button
            type="button"
            variant={!props.proceedResearch ? "primary" : "secondary"}
            size="sm"
            onClick={() => props.onProceedResearchChange(false)}
          >
            Hold
          </Button>
        </div>
      ) : null}

      {/* Gate 2: Confirm Competitor Assets */}
      {pendingSignal === "strategy_v2_confirm_competitor_assets" ? (
        <div className="space-y-2">
          <div className="text-[11px] text-content-muted">
            Confirm {props.competitorAssetPolicy.min}-{props.competitorAssetPolicy.max} assets
            {props.competitorAssetPolicy.target ? ` (target ${props.competitorAssetPolicy.target})` : ""}.
          </div>
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
                    checked={canConfirm ? props.confirmedAssetRefs.includes(assetRef) : false}
                    onChange={() => canConfirm && props.onToggleAssetRef(assetRef)}
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
                  <Button type="button" variant="secondary" size="xs" onClick={() => onOpenCandidate(candidate.id)}>
                    Open dossier
                  </Button>
                </div>
              </label>
            );
          })}
        </div>
      ) : null}

      {/* Gate 3: Select Angle */}
      {pendingSignal === "strategy_v2_select_angle" ? (
        <RadioCandidateList
          name="strategy-angle"
          candidates={candidates}
          selectedId={props.selectedAngleId}
          onSelect={props.onAngleChange}
          reviewedSet={reviewedSet}
          onOpenCandidate={onOpenCandidate}
        />
      ) : null}

      {/* Gate 4: Select UMP/UMS */}
      {pendingSignal === "strategy_v2_select_ump_ums" ? (
        <RadioCandidateList
          name="strategy-pair"
          candidates={candidates}
          selectedId={props.selectedPairId}
          onSelect={props.onPairChange}
          reviewedSet={reviewedSet}
          onOpenCandidate={onOpenCandidate}
        />
      ) : null}

      {/* Gate 5: Select Offer Winner */}
      {pendingSignal === "strategy_v2_select_offer_winner" ? (
        <RadioCandidateList
          name="strategy-variant"
          candidates={candidates}
          selectedId={props.selectedVariantId}
          onSelect={props.onVariantChange}
          reviewedSet={reviewedSet}
          onOpenCandidate={onOpenCandidate}
        />
      ) : null}

      {/* Gate 6: Approve Final Copy */}
      {pendingSignal === "strategy_v2_approve_final_copy" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={props.finalCopyApproved ? "primary" : "secondary"}
            size="sm"
            onClick={() => props.onFinalCopyChange(true)}
          >
            Approve
          </Button>
          <Button
            type="button"
            variant={!props.finalCopyApproved ? "primary" : "secondary"}
            size="sm"
            onClick={() => props.onFinalCopyChange(false)}
          >
            Reject
          </Button>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared radio list for gates 3, 4, 5
// ---------------------------------------------------------------------------

function RadioCandidateList({
  name,
  candidates,
  selectedId,
  onSelect,
  reviewedSet,
  onOpenCandidate,
}: {
  name: string;
  candidates: StrategyV2Candidate[];
  selectedId: string;
  onSelect: (id: string) => void;
  reviewedSet: Set<string>;
  onOpenCandidate: (id: string) => void;
}) {
  return (
    <div className="space-y-2">
      {candidates.map((candidate) => {
        const reviewed = reviewedSet.has(candidate.id);
        return (
          <label key={candidate.id} className="flex items-center justify-between gap-3 text-xs text-content">
            <div className="flex items-center gap-2 min-w-0">
              <input
                type="radio"
                name={name}
                className="h-4 w-4 border border-border bg-surface text-accent"
                checked={selectedId === candidate.id}
                onChange={() => onSelect(candidate.id)}
              />
              <span className="truncate">{candidate.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={reviewed ? "success" : "neutral"}>{reviewed ? "Reviewed" : "Not reviewed"}</Badge>
              <Button type="button" variant="secondary" size="xs" onClick={() => onOpenCandidate(candidate.id)}>
                Open dossier
              </Button>
            </div>
          </label>
        );
      })}
    </div>
  );
}

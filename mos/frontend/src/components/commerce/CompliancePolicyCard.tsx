import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useClientComplianceProfile,
  useUpsertClientComplianceProfile,
  useSyncComplianceShopifyPolicyPages,
  COMPLIANCE_RULESET_VERSION,
  type ComplianceBusinessModel,
  type ComplianceShopifyPolicySyncResponse,
} from "@/api/compliance";
import {
  type ComplianceProfileFormState,
  buildComplianceProfileFormState,
  parseComplianceBusinessModels,
  normalizeComplianceOptionalText,
  ALLOWED_COMPLIANCE_BUSINESS_MODELS,
} from "@/lib/complianceUtils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";

type CompliancePolicyCardProps = {
  workspaceId: string;
  workspaceName: string;
  shopifySyncShopDomain: string;
  selectedShopDomainOption: { storefrontDomain?: string; value?: string } | null;
  hasShopifyConnectionTarget: boolean;
};

export function CompliancePolicyCard({
  workspaceId,
  workspaceName,
  shopifySyncShopDomain,
  selectedShopDomainOption,
  hasShopifyConnectionTarget,
}: CompliancePolicyCardProps) {
  const { data: complianceProfile, isLoading: isLoadingComplianceProfile } =
    useClientComplianceProfile(workspaceId);
  const upsertComplianceProfile = useUpsertClientComplianceProfile(workspaceId);
  const syncCompliancePolicyPages = useSyncComplianceShopifyPolicyPages(workspaceId);

  const [policySyncResult, setPolicySyncResult] = useState<ComplianceShopifyPolicySyncResponse | null>(null);
  const [complianceProfileForm, setComplianceProfileForm] = useState<ComplianceProfileFormState>(() =>
    buildComplianceProfileFormState(null, workspaceName)
  );

  const hasSavedComplianceProfile = Boolean(complianceProfile?.id);
  const [expanded, setExpanded] = useState(false);

  const complianceProfileUpdatedAtLabel = useMemo(() => {
    if (!complianceProfile?.updatedAt) return "";
    const parsed = new Date(complianceProfile.updatedAt);
    if (Number.isNaN(parsed.getTime())) return complianceProfile.updatedAt;
    return parsed.toLocaleString();
  }, [complianceProfile?.updatedAt]);

  const complianceProfileFormSeedRef = useRef("");

  // Reset form when workspace changes.
  useEffect(() => {
    setPolicySyncResult(null);
    complianceProfileFormSeedRef.current = "";
    setComplianceProfileForm(buildComplianceProfileFormState(null, workspaceName));
  }, [workspaceId, workspaceName]);

  // Seed form from API data once loaded.
  useEffect(() => {
    const profileVersion = complianceProfile?.updatedAt || "missing";
    const nextSeed = `${workspaceId}:${profileVersion}`;
    if (!workspaceId || complianceProfileFormSeedRef.current === nextSeed) return;
    complianceProfileFormSeedRef.current = nextSeed;
    setComplianceProfileForm(buildComplianceProfileFormState(complianceProfile, workspaceName));
  }, [complianceProfile, workspaceId, workspaceName]);

  const handleComplianceProfileFieldChange = (
    field: keyof ComplianceProfileFormState,
    value: string
  ) => {
    setComplianceProfileForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const handleSaveComplianceProfile = async () => {
    if (!workspaceId) return;
    const trimmedName = workspaceName?.trim() || "";
    if (!trimmedName) {
      toast.error("Workspace name is required before saving a compliance profile.");
      return;
    }

    let businessModels: ComplianceBusinessModel[];
    try {
      businessModels = parseComplianceBusinessModels(complianceProfileForm.businessModelsCsv);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Invalid business models.";
      toast.error(message);
      return;
    }

    try {
      const saved = await upsertComplianceProfile.mutateAsync({
        rulesetVersion: COMPLIANCE_RULESET_VERSION,
        businessModels,
        legalBusinessName: normalizeComplianceOptionalText(complianceProfileForm.legalBusinessName),
        companyAddressText: normalizeComplianceOptionalText(complianceProfileForm.companyAddressText),
        supportEmail: normalizeComplianceOptionalText(complianceProfileForm.supportEmail),
        supportPhone: normalizeComplianceOptionalText(complianceProfileForm.supportPhone),
        supportHoursText: normalizeComplianceOptionalText(complianceProfileForm.supportHoursText),
        metadata: {},
      });
      setComplianceProfileForm(buildComplianceProfileFormState(saved, workspaceName));
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleSyncCompliancePolicyPages = async () => {
    if (!workspaceId) return;
    if (!hasSavedComplianceProfile) {
      toast.error("Save a compliance profile before generating policy pages.");
      return;
    }
    const payload = shopifySyncShopDomain
      ? {
          shopDomain: shopifySyncShopDomain,
          storefrontDomain: selectedShopDomainOption?.storefrontDomain || undefined,
        }
      : {};
    try {
      const response = await syncCompliancePolicyPages.mutateAsync(payload);
      setPolicySyncResult(response);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  return (
    <div className="ds-card ds-card--md space-y-4">
      {/* Header — clickable to expand/collapse */}
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div>
          <div className="text-sm font-semibold text-content">Compliance</div>
          <div className="text-xs text-content-muted">
            {isLoadingComplianceProfile
              ? "Loading\u2026"
              : hasSavedComplianceProfile
                ? `Profile saved${complianceProfileUpdatedAtLabel ? ` · ${complianceProfileUpdatedAtLabel}` : ""} · Ruleset ${COMPLIANCE_RULESET_VERSION}`
                : "No profile saved yet"}
          </div>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-content-muted transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded ? (
        <>
          {/* Form */}
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium text-content">Business models</label>
              <Input
                value={complianceProfileForm.businessModelsCsv}
                onChange={(event) => handleComplianceProfileFieldChange("businessModelsCsv", event.target.value)}
                placeholder="ecommerce"
              />
              <div className="text-[11px] text-content-muted">
                Comma-separated. Allowed: {ALLOWED_COMPLIANCE_BUSINESS_MODELS.join(", ")}.
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-content">Legal business name</label>
              <Input
                value={complianceProfileForm.legalBusinessName}
                onChange={(event) => handleComplianceProfileFieldChange("legalBusinessName", event.target.value)}
                placeholder="The Honest Herbalist LLC"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-content">Support email</label>
              <Input
                value={complianceProfileForm.supportEmail}
                onChange={(event) => handleComplianceProfileFieldChange("supportEmail", event.target.value)}
                placeholder="support@company.com"
              />
            </div>
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium text-content">Company address</label>
              <textarea
                rows={2}
                value={complianceProfileForm.companyAddressText}
                onChange={(event) => handleComplianceProfileFieldChange("companyAddressText", event.target.value)}
                placeholder="123 Main St, Suite 10, Austin, TX 78701, United States"
                className={cn(
                  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
                )}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-content">Support phone (optional)</label>
              <Input
                value={complianceProfileForm.supportPhone}
                onChange={(event) => handleComplianceProfileFieldChange("supportPhone", event.target.value)}
                placeholder="+1 555 010 1000"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-content">Support hours</label>
              <Input
                value={complianceProfileForm.supportHoursText}
                onChange={(event) => handleComplianceProfileFieldChange("supportHoursText", event.target.value)}
                placeholder="Mon-Fri 9:00 AM-5:00 PM CST"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 border-t border-divider pt-3">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                void handleSaveComplianceProfile();
              }}
              disabled={upsertComplianceProfile.isPending || isLoadingComplianceProfile || !workspaceId}
            >
              {upsertComplianceProfile.isPending ? "Saving\u2026" : "Save profile"}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                void handleSyncCompliancePolicyPages();
              }}
              disabled={
                syncCompliancePolicyPages.isPending ||
                !hasShopifyConnectionTarget ||
                !hasSavedComplianceProfile ||
                isLoadingComplianceProfile
              }
            >
              {syncCompliancePolicyPages.isPending ? "Generating\u2026" : "Generate policy pages"}
            </Button>
          </div>

          {/* Sync result */}
          {policySyncResult ? (
            <div className="space-y-2">
              <div className="text-xs text-content-muted">
                Synced to{" "}
                <span className="font-semibold text-content">
                  {policySyncResult.storefrontDomain || policySyncResult.shopDomain}
                </span>
                {" · "}
                <span className="font-semibold text-content">{policySyncResult.pages.length}</span> page(s)
              </div>
              <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                <TableHeader>
                  <TableRow>
                    <TableHeadCell className="w-[220px]">Page</TableHeadCell>
                    <TableHeadCell>URL</TableHeadCell>
                    <TableHeadCell className="w-[120px]">Operation</TableHeadCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {policySyncResult.pages.map((page) => (
                    <TableRow key={page.pageId}>
                      <TableCell className="text-xs text-content">{page.title}</TableCell>
                      <TableCell className="text-xs">
                        <a href={page.url} target="_blank" rel="noreferrer" className="break-all text-accent hover:underline">
                          {page.url}
                        </a>
                      </TableCell>
                      <TableCell className="text-xs text-content-muted">{page.operation}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

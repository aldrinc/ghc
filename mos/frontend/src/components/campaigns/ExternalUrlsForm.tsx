import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CampaignDeliveryConfig } from "@/types/delivery";

type UrlField = {
  key: "preSalesUrl" | "salesUrl" | "checkoutUrl" | "thankYouUrl";
  label: string;
  required: boolean;
  placeholder: string;
};

const URL_FIELDS: UrlField[] = [
  { key: "preSalesUrl", label: "Pre-Sales Landing Page", required: true, placeholder: "https://example.com/presale" },
  { key: "salesUrl", label: "Sales Page", required: true, placeholder: "https://example.com/sales" },
  { key: "checkoutUrl", label: "Checkout (optional)", required: false, placeholder: "https://example.com/checkout" },
  { key: "thankYouUrl", label: "Thank You (optional)", required: false, placeholder: "https://example.com/thank-you" },
];

function isValidUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

/**
 * Form for entering and validating external destination URLs.
 */
export function ExternalUrlsForm({
  config,
  onChange,
  onValidate,
  validating,
  disabled,
}: {
  config: CampaignDeliveryConfig;
  onChange: (next: CampaignDeliveryConfig) => void;
  onValidate: () => void;
  validating: boolean;
  disabled?: boolean;
}) {
  const update = (key: UrlField["key"], value: string) => {
    onChange({ ...config, [key]: value, validationStatus: "not_validated" });
  };

  const requiredFilled = URL_FIELDS.filter((f) => f.required).every((f) => {
    const value = config[f.key];
    return value && isValidUrl(value);
  });

  return (
    <div className="max-w-2xl space-y-4">
      {URL_FIELDS.map((field) => {
        const value = config[field.key] || "";
        const hasValue = value.trim().length > 0;
        const valid = !hasValue || isValidUrl(value);
        return (
          <div key={field.key} className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">
              {field.label} {field.required ? "*" : ""}
            </label>
            <Input
              value={value}
              onChange={(e) => update(field.key, e.target.value)}
              placeholder={field.placeholder}
              disabled={disabled}
              className={!valid ? "border-danger" : undefined}
            />
            {hasValue && !valid ? (
              <div className="text-xs text-danger">Must be a valid public HTTP or HTTPS URL.</div>
            ) : null}
          </div>
        );
      })}

      <div className="flex items-center gap-3 pt-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={onValidate}
          disabled={disabled || validating || !requiredFilled}
        >
          {validating ? "Validating…" : "Validate URLs"}
        </Button>

        {config.validationStatus === "valid" ? (
          <Badge tone="success">Validated</Badge>
        ) : config.validationStatus === "invalid" ? (
          <Badge tone="danger">Invalid</Badge>
        ) : config.validationStatus === "not_applicable" ? (
          <Badge tone="neutral">Internal routing</Badge>
        ) : (
          <Badge tone="neutral">Not validated</Badge>
        )}

        {config.validationError ? (
          <span className="text-xs text-danger">{config.validationError}</span>
        ) : null}

        {config.validatedAt ? (
          <span className="text-xs text-content-muted">
            Last validated {new Date(config.validatedAt).toLocaleString()}
          </span>
        ) : null}
      </div>
    </div>
  );
}

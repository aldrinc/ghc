import { Button } from "@/components/ui/button";
import {
  META_DEFAULT_BROAD_INT_COUNTRIES,
  META_COUNTRY_TIER_1,
  META_COUNTRY_TIER_2,
  META_COUNTRY_TIER_3,
  parseCountriesFromTargetingJson,
  mergeCountriesIntoTargetingJson,
  clearCountriesFromTargetingJson,
} from "@/lib/metaAdsConstants";

interface CountryTierButtonsProps {
  targetingJson: string;
  onTargetingJsonChange: (value: string) => void;
}

function tierActive(current: string[], tier: readonly string[]): boolean {
  return tier.length > 0 && tier.every((c) => current.includes(c));
}

export function CountryTierButtons({ targetingJson, onTargetingJsonChange }: CountryTierButtonsProps) {
  const current = parseCountriesFromTargetingJson(targetingJson);
  const defaultBroadIntActive = tierActive(current, META_DEFAULT_BROAD_INT_COUNTRIES);
  const t1Active = tierActive(current, META_COUNTRY_TIER_1);
  const t2Active = tierActive(current, META_COUNTRY_TIER_2);
  const t3Active = tierActive(current, META_COUNTRY_TIER_3);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-content-muted">Quick-fill:</span>
      <Button
        type="button"
        variant={defaultBroadIntActive ? "primary" : "secondary"}
        size="xs"
        onClick={() => onTargetingJsonChange(mergeCountriesIntoTargetingJson(targetingJson, META_DEFAULT_BROAD_INT_COUNTRIES))}
      >
        Broad/Int ({META_DEFAULT_BROAD_INT_COUNTRIES.length})
      </Button>
      <Button
        type="button"
        variant={t1Active ? "primary" : "secondary"}
        size="xs"
        onClick={() => onTargetingJsonChange(mergeCountriesIntoTargetingJson(targetingJson, META_COUNTRY_TIER_1))}
      >
        Tier 1 ({META_COUNTRY_TIER_1.length})
      </Button>
      <Button
        type="button"
        variant={t2Active ? "primary" : "secondary"}
        size="xs"
        onClick={() => onTargetingJsonChange(mergeCountriesIntoTargetingJson(targetingJson, META_COUNTRY_TIER_2))}
      >
        Tier 2 ({META_COUNTRY_TIER_2.length})
      </Button>
      <Button
        type="button"
        variant={t3Active ? "primary" : "secondary"}
        size="xs"
        onClick={() => onTargetingJsonChange(mergeCountriesIntoTargetingJson(targetingJson, META_COUNTRY_TIER_3))}
      >
        Tier 3 ({META_COUNTRY_TIER_3.length})
      </Button>
      {current.length > 0 ? (
        <Button
          type="button"
          variant="secondary"
          size="xs"
          onClick={() => onTargetingJsonChange(clearCountriesFromTargetingJson(targetingJson))}
        >
          Clear
        </Button>
      ) : null}
      {current.length > 0 ? (
        <span className="text-xs text-content-muted">{current.length} countries</span>
      ) : null}
    </div>
  );
}

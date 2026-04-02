import { ImportedRuntimeSection } from "@/components/imported-site/ImportedRuntimeSection";
import { augmentImportedSourceSectionProps } from "@/components/imported-site/importedGlobalNavigation";

type SlotRecord = Record<string, unknown>;

type ImportedSourceSectionProps = {
  id?: string;
  sectionLabel?: string;
  componentName?: string;
  sectionTargetId?: string;
  textSlots?: SlotRecord[];
  buttonSlots?: SlotRecord[];
  imageSlots?: SlotRecord[];
};

function normalizeSlotRecords(value: unknown): SlotRecord[] | undefined {
  return Array.isArray(value) ? (value as SlotRecord[]) : undefined;
}

function ImportedSourceSectionFrame({
  id,
  sectionLabel,
  componentName,
  sectionTargetId,
  textSlots,
  buttonSlots,
  imageSlots,
}: ImportedSourceSectionProps) {
  return (
    <ImportedRuntimeSection
      id={id}
      sectionLabel={sectionLabel}
      componentName={componentName}
      sectionTargetId={sectionTargetId}
      textOverrides={normalizeSlotRecords(textSlots)}
      buttonOverrides={normalizeSlotRecords(buttonSlots)}
      imageOverrides={normalizeSlotRecords(imageSlots)}
    />
  );
}

export function ImportedHeaderSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...(augmentImportedSourceSectionProps(props) as ImportedSourceSectionProps)} />;
}

export function ImportedHeroSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedProofBarSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedFeatureSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedOfferSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedTestimonialsSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedComparisonSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedFaqSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...props} />;
}

export function ImportedFooterSection(props: ImportedSourceSectionProps) {
  return <ImportedSourceSectionFrame {...(augmentImportedSourceSectionProps(props) as ImportedSourceSectionProps)} />;
}

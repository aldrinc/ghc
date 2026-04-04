import type { ReactNode } from "react";

import { ImportedPage, ImportedSection } from "@/components/imported-site/ImportedTemplateBlocks";
import {
  ImportedFooterSection,
  ImportedHeaderSection,
} from "@/components/imported-site/ImportedSourceSectionBlocks";

import type { ImportedOneProductShellData } from "../importedOneProductShellData";

type ImportedOneProductShellProps = {
  shell: ImportedOneProductShellData;
  children: ReactNode;
};

export function ImportedOneProductShell({ shell, children }: ImportedOneProductShellProps) {
  const headerWrapperProps = shell.header.wrapperProps;
  const headerSectionProps = shell.header.sectionProps;
  const footerWrapperProps = shell.footer.wrapperProps;
  const footerSectionProps = shell.footer.sectionProps;

  return (
    <ImportedPage
      pageName={shell.pageName}
      theme={shell.theme}
      themeJson={shell.themeJson}
      renderMode={shell.renderMode}
      sharedRuntimeSource={shell.sharedRuntimeSource}
      sharedHeadAssets={shell.sharedHeadAssets}
      content={() => (
        <div className="flex min-h-screen flex-col">
          <ImportedSection
            displayName={typeof headerWrapperProps.displayName === "string" ? headerWrapperProps.displayName : undefined}
            sourceSectionId={
              typeof headerWrapperProps.sourceSectionId === "string" ? headerWrapperProps.sourceSectionId : undefined
            }
            sectionKey={typeof headerWrapperProps.sectionKey === "string" ? headerWrapperProps.sectionKey : undefined}
            sectionType={typeof headerWrapperProps.sectionType === "string" ? headerWrapperProps.sectionType : undefined}
            semanticTagsText={
              typeof headerWrapperProps.semanticTagsText === "string"
                ? headerWrapperProps.semanticTagsText
                : undefined
            }
            surface={typeof headerWrapperProps.surface === "string" ? headerWrapperProps.surface : undefined}
            renderMode={typeof headerWrapperProps.renderMode === "string" ? headerWrapperProps.renderMode : undefined}
            content={() => <ImportedHeaderSection {...headerSectionProps} />}
          />
          <div className="flex-1">{children}</div>
          <ImportedSection
            displayName={typeof footerWrapperProps.displayName === "string" ? footerWrapperProps.displayName : undefined}
            sourceSectionId={
              typeof footerWrapperProps.sourceSectionId === "string" ? footerWrapperProps.sourceSectionId : undefined
            }
            sectionKey={typeof footerWrapperProps.sectionKey === "string" ? footerWrapperProps.sectionKey : undefined}
            sectionType={typeof footerWrapperProps.sectionType === "string" ? footerWrapperProps.sectionType : undefined}
            semanticTagsText={
              typeof footerWrapperProps.semanticTagsText === "string"
                ? footerWrapperProps.semanticTagsText
                : undefined
            }
            surface={typeof footerWrapperProps.surface === "string" ? footerWrapperProps.surface : undefined}
            renderMode={typeof footerWrapperProps.renderMode === "string" ? footerWrapperProps.renderMode : undefined}
            content={() => <ImportedFooterSection {...footerSectionProps} />}
          />
        </div>
      )}
    />
  );
}

import { HtmlDeployPage } from "@/funnels/StandaloneImportedHtmlPage";
import type { PublicCommerceVariant } from "@/types/commerce";
import type { ImportedHtmlInstrumentationManifest, PublicFunnelPage, PublicFunnelStage } from "@/types/funnels";

type PublicImportedHtmlRendererProps = {
  page: PublicFunnelPage;
  productSlug: string;
  funnelSlug: string;
  visitorId: string;
  sessionId: string;
  htmlDocument: string;
  instrumentationManifest: ImportedHtmlInstrumentationManifest;
  variants: PublicCommerceVariant[];
  pagePathById: Record<string, string>;
  pageStageById: Record<string, PublicFunnelStage>;
};

export default function PublicImportedHtmlRenderer(props: PublicImportedHtmlRendererProps) {
  return <HtmlDeployPage {...props} />;
}

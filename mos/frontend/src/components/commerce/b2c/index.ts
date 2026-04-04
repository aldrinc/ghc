// Runtime and Theme
export { B2CRuntimeProvider, useB2CRuntime, useMaybeB2CRuntime } from "./B2CRuntimeProvider";
export { useB2CTheme, useB2CCTATheme, useB2CHeaderTheme } from "./useB2CTheme";
export type { B2CTheme, B2CThemeTokens } from "./useB2CTheme";

// Pages
export { MedusaB2CHomePage } from "./pages/MedusaB2CHomePage";
export { MedusaB2CStorePage } from "./pages/MedusaB2CStorePage";
export { MedusaB2CProductPage } from "./pages/MedusaB2CProductPage";
export { B2CStarterShell } from "./pages/B2CStarterShell";
export {
  MedusaB2CCollectionPage,
  MedusaB2CCategoryPage,
  MedusaB2CCartPage,
  MedusaB2CCheckoutPage,
  MedusaB2CPolicyPage,
  MedusaB2CAccountDashboardPage,
  MedusaB2CAccountProfilePage,
  MedusaB2CAccountAddressesPage,
  MedusaB2CAccountOrdersPage,
  MedusaB2CAccountOrderDetailPage,
  MedusaB2COrderConfirmedPage,
  MedusaB2COrderTransferPage,
  MedusaB2COrderTransferAcceptPage,
  MedusaB2COrderTransferDeclinePage,
} from "./pages/MedusaB2CAdditionalPages";

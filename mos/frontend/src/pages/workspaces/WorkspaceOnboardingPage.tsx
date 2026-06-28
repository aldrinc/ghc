import { useClerk } from "@clerk/clerk-react";
import { ArrowLeft, LogOut, MoreVertical, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { OnboardingWizard } from "@/components/clients/OnboardingWizard";
import { buttonClasses } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";

export function WorkspaceOnboardingPage() {
  const navigate = useNavigate();
  const { signOut } = useClerk();
  const { selectWorkspace, clients, isLoading } = useWorkspace();
  const { selectProduct } = useProductContext();
  const isFirstWorkspaceOnboarding = !isLoading && clients.length === 0;

  const handleComplete = ({
    clientId,
    clientName,
    productId,
    productName,
  }: {
    clientId: string;
    clientName?: string;
    productId: string;
    productName?: string;
  }) => {
    selectWorkspace(clientId, { name: clientName });
    selectProduct(
      productId,
      {
        title: productName,
        client_id: clientId,
      },
      { clientId }
    );
    navigate("/workspaces/foundation-ready");
  };

  return (
    <div className="first-run-surface min-h-screen bg-background text-foreground">
      <OnboardingWizard
        variant="page"
        triggerLabel="Start onboarding"
        onCompleted={handleComplete}
        showSetupLogout={isFirstWorkspaceOnboarding}
        pageHeaderAction={
          <button
            onClick={() => navigate("/workspaces")}
            className="hidden items-center gap-2 text-sm font-medium text-content-muted transition hover:text-content sm:inline-flex"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to workspaces</span>
          </button>
        }
        pageHeaderEndAction={
          isFirstWorkspaceOnboarding ? (
            <Menu>
              <MenuTrigger
                aria-label="Onboarding options"
                className={buttonClasses({
                  variant: "ghost",
                  size: "sm",
                  className:
                    "inline-flex h-9 w-9 items-center justify-center p-0 text-content-muted hover:text-content hover:scale-100 hover:shadow-none active:scale-100 active:shadow-none sm:hidden",
                })}
              >
                <MoreVertical className="h-4 w-4" />
              </MenuTrigger>
              <MenuContent className="sm:hidden">
                <MenuItem onClick={() => signOut({ redirectUrl: "/sign-in" })}>
                  <LogOut className="h-4 w-4" />
                  Log out
                </MenuItem>
              </MenuContent>
            </Menu>
          ) : (
            <button
              type="button"
              aria-label="Close onboarding"
              onClick={() => navigate("/workspaces")}
              className={buttonClasses({
                variant: "ghost",
                size: "sm",
                className:
                  "inline-flex h-9 w-9 items-center justify-center p-0 text-content-muted hover:text-content hover:scale-100 hover:shadow-none active:scale-100 active:shadow-none sm:hidden",
              })}
            >
              <X className="h-4 w-4" />
            </button>
          )
        }
      />
    </div>
  );
}

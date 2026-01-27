import { useMemo, type ComponentType, type SVGProps } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useClerk, useUser } from "@clerk/clerk-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "@/components/animate-ui/components/radix/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/animate-ui/components/radix/dropdown-menu";
import {
  FileText,
  Globe2,
  Funnel,
  NotepadText,
  FlaskConical,
  Palette,
  Sparkles,
  Folder,
  Plus,
  BadgeCheck,
  Settings2,
  CreditCard,
  Bell,
  ChevronsUpDown,
  LogOut,
  LayoutDashboard,
  ListChecks,
  Target,
  MessageSquare,
} from "lucide-react";
import { appRoutes } from "./routes";
import { useIsMobile } from "@/hooks/use-mobile";
import { useWorkspace } from "@/contexts/WorkspaceContext";

type NavItem = {
  title: string;
  path: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

function getWorkspaceInitial(name?: string | null) {
  const trimmed = name?.trim();
  if (!trimmed) return "W";
  const match = trimmed.match(/[A-Za-z0-9]/);
  return (match?.[0] ?? trimmed[0]).toUpperCase();
}

const WORKSPACE_NAV: NavSection = {
  label: "Workspace",
  items: [
    { title: "Overview", path: "/workspaces/overview", icon: LayoutDashboard },
    { title: "Workflows", path: "/workflows", icon: ListChecks },
  ],
};

const RESEARCH_NAV: NavSection = {
  label: "Research",
  items: [
    { title: "Documents", path: "/research/documents", icon: FileText },
    { title: "Competitors", path: "/research/competitors", icon: Globe2 },
    { title: "Funnels", path: "/research/funnels", icon: Funnel },
    { title: "Explore Ads", path: "/explore/ads", icon: Sparkles },
    { title: "Explore Brands", path: "/explore/brands", icon: Folder },
  ],
};

const EXECUTION_NAV: NavSection = {
  label: "Execution",
  items: [
    { title: "Campaigns", path: "/campaigns", icon: Target },
    { title: "Strategy Sheet", path: "/strategy-sheet", icon: NotepadText },
    { title: "Experiments", path: "/experiments", icon: FlaskConical },
  ],
};

const ASSETS_NAV: NavSection = {
  label: "Assets",
  items: [{ title: "Creative Library", path: "/creative-library", icon: Palette }],
};

const AI_NAV: NavSection = {
  label: "AI",
  items: [{ title: "Claude Chat", path: "/claude-chat", icon: MessageSquare }],
};

function NavigationMenu({ label, items }: NavSection) {
  const location = useLocation();
  const navigate = useNavigate();
  const { setOpenMobile } = useSidebar();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => {
          const isActive =
            location.pathname === item.path ||
            location.pathname.startsWith(`${item.path}/`);

          return (
            <SidebarMenuItem key={item.path}>
              <SidebarMenuButton
                isActive={isActive}
                tooltip={item.title}
                className="min-w-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2 transition-transform hover:translate-x-[1px]"
                onClick={() => {
                  navigate(item.path);
                  setOpenMobile(false);
                }}
              >
                <item.icon className="size-4" />
                <span className="group-data-[collapsible=icon]:hidden">{item.title}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const { user } = useUser();
  const { signOut, openUserProfile, openUserSettings } = useClerk();
  const { workspace, selectWorkspace, clients, isLoading: isLoadingWorkspaces } = useWorkspace();

  const activeRoute = useMemo(
    () => appRoutes.find((route) => location.pathname.startsWith(route.path)),
    [location.pathname],
  );
  const routeLabel = activeRoute?.label ?? "Overview";
  const email =
    user?.primaryEmailAddress?.emailAddress ?? user?.emailAddresses?.[0]?.emailAddress;
  const name = user?.fullName || user?.username || email || "Operator";
  const initials = useMemo(
    () =>
      name
        .split(" ")
        .filter(Boolean)
        .map((part) => part[0])
        .join("")
        .slice(0, 2)
        .toUpperCase(),
    [name],
  );

  const handleSwitchWorkspace = () => {
    navigate("/workspaces");
  };

  const workspaceInitial = useMemo(
    () => getWorkspaceInitial(workspace?.name),
    [workspace?.name],
  );

  const handleSelectWorkspace = (clientId: string) => {
    selectWorkspace(clientId);
    navigate("/workspaces/overview");
  };

  const handleCreateWorkspace = () => {
    navigate("/workspaces/new");
  };

  return (
    <SidebarProvider className="bg-background text-foreground">
      <Sidebar collapsible="icon" className="border-r border-sidebar-border">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    tooltip="Workspace"
                    className="min-w-0 data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-foreground group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2"
                  >
                    <div className="flex aspect-square size-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground text-sm font-semibold uppercase group-data-[collapsible=icon]:size-8">
                      {workspaceInitial}
                    </div>
                    <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                      <span className="truncate font-semibold">
                        {workspace?.name || "Select a workspace"}
                      </span>
                      <span className="truncate text-xs text-sidebar-foreground opacity-70">
                        Workspace
                      </span>
                    </div>
                    <ChevronsUpDown className="ml-auto size-4 group-data-[collapsible=icon]:hidden" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                  align="start"
                  side={isMobile ? "bottom" : "right"}
                  sideOffset={6}
                >
                  <DropdownMenuLabel className="text-xs text-muted-foreground">
                    Workspaces
                  </DropdownMenuLabel>
                  <DropdownMenuGroup className="max-h-72 overflow-y-auto">
                    {isLoadingWorkspaces ? (
                      <div className="px-3 py-2 text-xs text-muted-foreground">Loading workspaces…</div>
                    ) : clients.length ? (
                      clients.map((client) => (
                        <DropdownMenuItem
                          key={client.id}
                          className="gap-3"
                          onClick={() => handleSelectWorkspace(client.id)}
                        >
                          <div className="flex h-9 w-9 items-center justify-center rounded-md border border-sidebar-border bg-white text-sidebar-foreground text-sm font-semibold uppercase">
                            {getWorkspaceInitial(client.name)}
                          </div>
                          <div className="flex flex-col">
                            <span className="font-semibold leading-5">{client.name}</span>
                            {client.industry ? (
                              <span className="text-xs text-muted-foreground">{client.industry}</span>
                            ) : null}
                          </div>
                        </DropdownMenuItem>
                      ))
                    ) : (
                      <div className="px-3 py-2 text-xs text-muted-foreground">
                        No workspaces yet. Start onboarding to create one.
                      </div>
                    )}
                  </DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="gap-3" onClick={handleCreateWorkspace}>
                    <Plus className="size-4" />
                    <div className="flex flex-col">
                      <span className="font-medium">Add workspace</span>
                      <span className="text-xs text-muted-foreground">Start onboarding flow</span>
                    </div>
                  </DropdownMenuItem>
                  <DropdownMenuItem className="gap-3" onClick={handleSwitchWorkspace}>
                    <Folder className="size-4" />
                    <div className="flex flex-col">
                      <span className="font-medium">Manage workspaces</span>
                      <span className="text-xs text-muted-foreground">Open workspace list</span>
                    </div>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent>
          <NavigationMenu {...WORKSPACE_NAV} />
          <NavigationMenu {...RESEARCH_NAV} />
          <NavigationMenu {...EXECUTION_NAV} />
          <NavigationMenu {...AI_NAV} />

          <SidebarSeparator className="mx-2" />
          <NavigationMenu {...ASSETS_NAV} />
        </SidebarContent>

        <SidebarFooter>
          <SidebarSeparator className="mx-2" />
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    tooltip="Account"
                    className="min-w-0 data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-foreground group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2"
                  >
                    <Avatar className="h-9 w-9 rounded-lg">
                      <AvatarImage src={user?.imageUrl} alt={name} />
                      <AvatarFallback className="rounded-lg">{initials}</AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                      <span className="truncate font-semibold">{name}</span>
                      {email ? <span className="truncate text-xs">{email}</span> : null}
                    </div>
                    <ChevronsUpDown className="ml-auto size-4 group-data-[collapsible=icon]:hidden" />
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                  align="end"
                  side={isMobile ? "bottom" : "right"}
                  sideOffset={6}
                >
                  <DropdownMenuLabel className="p-0 font-normal">
                    <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                      <Avatar className="h-9 w-9 rounded-lg">
                        <AvatarImage src={user?.imageUrl} alt={name} />
                        <AvatarFallback className="rounded-lg">{initials}</AvatarFallback>
                      </Avatar>
                      <div className="grid flex-1 text-left text-sm leading-tight">
                        <span className="truncate font-semibold">{name}</span>
                        {email ? <span className="truncate text-xs">{email}</span> : null}
                      </div>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuGroup>
                    <DropdownMenuItem
                      className="gap-3"
                      onClick={() => openUserProfile?.()}
                    >
                      <BadgeCheck className="size-4" />
                      <span>Profile</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="gap-3"
                      onClick={() => openUserSettings?.()}
                    >
                      <Settings2 className="size-4" />
                      <span>Account settings</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem className="gap-3">
                      <CreditCard className="size-4" />
                      <span>Billing</span>
                      <DropdownMenuShortcut>⌘B</DropdownMenuShortcut>
                    </DropdownMenuItem>
                    <DropdownMenuItem className="gap-3">
                      <Bell className="size-4" />
                      <span>Notifications</span>
                      <DropdownMenuShortcut>⌘N</DropdownMenuShortcut>
                    </DropdownMenuItem>
                  </DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => signOut({ redirectUrl: "/sign-in" })}>
                    <LogOut />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>

      <SidebarInset className="bg-white dark:bg-slate-950">
        <header className="flex h-16 shrink-0 items-center border-b border-border bg-white px-4 pr-4 text-sm md:px-6 dark:bg-slate-950">
          <div className="flex items-center gap-3">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="h-5" />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem className="hidden md:block">
                  <BreadcrumbLink asChild>
                    <Link to="/workspaces">Workspaces</Link>
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator className="hidden md:block" />
                <BreadcrumbItem>
                  <BreadcrumbPage>{routeLabel}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
        </header>
        <div className="flex flex-1 flex-col overflow-y-auto bg-white px-4 py-4 md:px-6 md:py-6 dark:bg-slate-950">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

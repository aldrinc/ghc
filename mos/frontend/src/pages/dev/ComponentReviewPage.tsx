import {
  Activity,
  ArrowRight,
  BarChart3,
  Briefcase,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  DollarSign,
  Eye,
  GraduationCap,
  Laptop,
  Layers3,
  Link2,
  Loader2,
  Mail,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Rocket,
  Search,
  Send,
  Settings2,
  ShoppingBag,
  Smartphone,
  Store,
  Target,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorState } from "@/components/layout/ErrorState";
import { FilterBar } from "@/components/layout/FilterBar";
import { ChoiceList } from "@/components/onboarding";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { DialogClose, DialogContent, DialogDescription, DialogRoot, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function ReviewSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="ds-section-card space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-content">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-content-muted">{description}</p>
      </div>
      {children}
    </section>
  );
}

export function ComponentReviewPage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-0">
      <PageHeader
        title="Component Review"
        description="Local MOS primitive harness for density, radius, focus, disabled, overflow, and floating states."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => toast.success("Workspace created")}
          >
            Show toast
          </Button>
        }
      />

      <ReviewSection title="Buttons" description="Reference: pill shape, 46px default, 36/54/64px sizes, halo hover and focus states.">
        <div className="flex flex-wrap items-center gap-3">
          <Button><Plus /> Get started</Button>
          <Button variant="accent"><CheckCircle2 /> Get started</Button>
          <Button variant="secondary">Book a demo</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive"><Trash2 /> Delete campaign</Button>
          <Button variant="link" className="underline decoration-1 underline-offset-4">Read the docs</Button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm">Small</Button>
          <Button size="default">Default</Button>
          <Button size="lg">Large</Button>
          <Button size="xl">Extra large</Button>
          <Button size="icon" variant="secondary" aria-label="Settings">
            <Settings2 />
          </Button>
        </div>
        <div className="mos-state-grid">
          <div className="mos-state-card">
            <span className="mos-state-label">Default</span>
            <Button>Launch campaign</Button>
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Hover</span>
            <Button className="scale-[1.015] shadow-[0_0_0_4px_rgba(11,13,18,0.12)]">Launch campaign</Button>
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Focused</span>
            <Button className="shadow-[0_0_0_4px_rgba(11,13,18,0.20)]">Launch campaign</Button>
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Loading</span>
            <Button aria-busy="true">
              <Loader2 className="animate-spin" />
              Launching...
            </Button>
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">With arrow</span>
            <Button>
              Continue
              <ArrowRight />
            </Button>
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Icon only</span>
            <Button size="icon" variant="secondary" aria-label="Search">
              <Search />
            </Button>
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Disabled</span>
            <Button disabled>Disabled</Button>
          </div>
        </div>
      </ReviewSection>

      <ReviewSection title="Badges, Pills And Status" description="Reference: 22px badges, subtle borders, dots with soft rings, and small pills for selected values.">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Neutral</Badge>
          <Badge tone="accent"><span className="mos-dot mos-dot--blue" /> Accent</Badge>
          <Badge tone="info">Info</Badge>
          <Badge tone="success">Success</Badge>
          <Badge tone="warning">Warning</Badge>
          <Badge tone="danger">Danger</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status="running" />
          <StatusBadge status="completed" />
          <StatusBadge status="failed" />
          <StatusBadge status="cancelled" />
          <StatusBadge status="pending" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="mos-chip"><span className="mos-dot mos-dot--success" /> Live</span>
          <span className="mos-chip">Brand voice</span>
          <span className="mos-chip">Organic social</span>
          <span className="mos-chip"><span className="mos-dot mos-dot--warning" /> Needs input</span>
        </div>
      </ReviewSection>

      <ReviewSection title="Forms" description="Reference: 54px controls, 12px corners, 1.5px borders, black focus ring, explicit error and disabled states.">
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Workspace name" helper="Short labels should stay close to their controls." required>
            <Input placeholder="Enter workspace name" />
          </FormField>
          <FormField label="Stage" error="This field shows the error style.">
            <Select
              className="!border-danger"
              options={[
                { label: "Draft", value: "draft" },
                { label: "Ready", value: "ready" },
                { label: "Blocked", value: "blocked" },
              ]}
              defaultValue="draft"
            />
          </FormField>
          <FormField label="Search field">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-content-muted" />
              <Input className="pl-9" placeholder="Search components" />
            </div>
          </FormField>
          <FormField label="Disabled input">
            <Input placeholder="Unavailable" disabled />
          </FormField>
          <FormField label="Brief" className="md:col-span-2">
            <Textarea placeholder="Write a short internal note." />
          </FormField>
        </div>
        <div className="mos-state-grid">
          <div className="mos-state-card">
            <span className="mos-state-label">Default</span>
            <Input placeholder="acme.com" />
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Focused</span>
            <Input className="border-input-border-focus shadow-[0_0_0_4px_rgba(11,13,18,0.07)]" value="acme.com" readOnly />
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Error</span>
            <Input className="!border-danger shadow-[0_0_0_4px_rgba(239,68,68,0.14)]" value="missing-at-symbol" readOnly />
          </div>
          <div className="mos-state-card">
            <span className="mos-state-label">Input group</span>
            <div className="mos-input-group">
              <span className="mos-input-addon">https://</span>
              <input className="mos-input" value="acme.com" readOnly />
            </div>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
          <div className="mos-combobox-demo">
            <div className="mos-combobox-trigger">
              <span className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
                <span className="mos-chip">Email</span>
                <span className="mos-chip">Paid social</span>
              </span>
              <ChevronDown className="size-4 text-content-muted" />
            </div>
            <div className="mos-combobox-panel">
              <div className="mos-combobox-option is-focused">
                <Check className="size-4" />
                <span>Email</span>
                <span className="text-xs text-content-muted">Selected</span>
              </div>
              <div className="mos-combobox-option">
                <span />
                <span>Paid social</span>
                <span className="text-xs text-content-muted">Meta</span>
              </div>
              <div className="mos-combobox-option">
                <span />
                <span>Organic social</span>
                <span className="text-xs text-content-muted">Queued</span>
              </div>
            </div>
          </div>
          <div>
            <span className="mos-state-label">OTP</span>
            <div className="mos-otp">
              <input className="mos-otp-cell" value="2" readOnly aria-label="Code digit 1" />
              <input className="mos-otp-cell is-focused" value="8" readOnly aria-label="Code digit 2" />
              <input className="mos-otp-cell" value="4" readOnly aria-label="Code digit 3" />
              <input className="mos-otp-cell" value="" readOnly aria-label="Code digit 4" />
            </div>
          </div>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <FormField label="Website with icon">
            <div className="relative">
              <Link2 className="pointer-events-none absolute left-[18px] top-1/2 size-4 -translate-y-1/2 text-content-muted" />
              <Input className="pl-12" placeholder="acme.com" />
            </div>
          </FormField>
          <FormField label="Search docs" className="min-h-[172px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-[18px] top-1/2 size-4 -translate-y-1/2 text-content-muted" />
              <Input className="pl-12 pr-16" type="search" placeholder="Search the docs..." />
              <span className="mos-kbd absolute right-3 top-1/2 -translate-y-1/2">⌘K</span>
              <div className="mos-autocomplete-panel is-open">
                <button className="mos-autocomplete-row is-focused" type="button">
                  <span>Connecting LinkedIn</span>
                  <span>Setup</span>
                </button>
                <button className="mos-autocomplete-row" type="button">
                  <span>Brand voice training</span>
                  <span>Brand</span>
                </button>
              </div>
            </div>
          </FormField>
          <FormField label="Password strength">
            <div>
              <div className="relative">
                <Input className="pr-14" type="password" value="strong-password" readOnly />
                <button className="mos-input-icon-button absolute right-3 top-1/2 -translate-y-1/2" type="button" aria-label="Show password">
                  <Eye className="size-4" />
                </button>
              </div>
              <div className="mos-strength-meter">
                <span className="mos-strength-track"><span className="mos-strength-fill" style={{ width: "72%" }} /></span>
                <span className="mos-strength-label">Strong</span>
              </div>
            </div>
          </FormField>
          <FormField label="Phone">
            <div className="relative">
              <Smartphone className="pointer-events-none absolute left-[18px] top-1/2 size-4 -translate-y-1/2 text-content-muted" />
              <Input className="pl-12" inputMode="tel" placeholder="(555) 204-9811" />
            </div>
          </FormField>
          <FormField label="Currency">
            <div className="mos-input-group">
              <span className="mos-input-addon"><DollarSign className="size-4" /></span>
              <input className="mos-input" inputMode="decimal" value="89.00" readOnly />
              <span className="mos-input-addon border-l-[1.5px] border-r-0">USD</span>
            </div>
          </FormField>
          <FormField label="Copyable value">
            <div className="mos-input-group">
              <span className="mos-input-addon"><Mail className="size-4" /></span>
              <input className="mos-input" value="ada@acme.com" readOnly />
              <button className="mos-input-addon mos-input-addon--button border-l-[1.5px] border-r-0" type="button">
                <Copy className="size-4" />
                Copy
              </button>
            </div>
          </FormField>
        </div>
      </ReviewSection>

      <ReviewSection title="Choice Cards" description="Full source choice system: single-select flows with Continue CTA, multi-select cards, compact choices, and grid/card choices.">
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <div className="ds-card ds-card--lg space-y-5">
            <div>
              <h3 className="font-display text-xl font-semibold tracking-tight text-content">What is the main bottleneck?</h3>
              <p className="mt-1 text-sm leading-6 text-content-muted">Single-select stack with full-width cards and a footer action.</p>
            </div>
            <ChoiceList
              aria-label="Marketing bottleneck"
              items={[
                {
                  id: "mess",
                  title: "Our marketing is kind of a mess",
                  description: "Inconsistent, scattered, or embarrassing to review.",
                  icon: <MessageSquare className="size-5" />,
                },
                {
                  id: "ship",
                  title: "We ship faster than we market",
                  description: "Product is great, but no one's hearing about it.",
                  icon: <Activity className="size-5" />,
                  selected: true,
                },
                {
                  id: "same",
                  title: "Same content, every single day",
                  description: "Customers keep asking the same questions.",
                  icon: <BarChart3 className="size-5" />,
                },
                {
                  id: "all",
                  title: "All of the above",
                  description: "Use this when the system needs a full reset.",
                  icon: <Target className="size-5" />,
                },
              ]}
            />
            <div className="flex justify-end">
              <Button>
                Continue
                <ArrowRight />
              </Button>
            </div>
          </div>

          <div className="space-y-5">
            <div className="ds-card ds-card--lg space-y-4">
              <div>
                <h3 className="font-display text-xl font-semibold tracking-tight text-content">Where should MOS publish?</h3>
                <p className="mt-1 text-sm leading-6 text-content-muted">Multi-select uses square rings and multiple selected cards.</p>
              </div>
              <ChoiceList
                aria-label="Publishing channels"
                selectionMode="multiple"
                items={[
                  {
                    id: "linkedin",
                    title: "LinkedIn",
                    description: "B2B reach · connected account.",
                    icon: <Send className="size-5" />,
                    selected: true,
                  },
                  {
                    id: "email",
                    title: "Email",
                    description: "Subscribers in your list.",
                    icon: <Mail className="size-5" />,
                    selected: true,
                  },
                  {
                    id: "blog",
                    title: "Blog",
                    description: "Long-form posts on your domain.",
                    icon: <Rocket className="size-5" />,
                  },
                ]}
              />
            </div>

            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-1">
              <div className="ds-card ds-card--md space-y-3">
                <h3 className="text-sm font-semibold text-content">Compact choices</h3>
                <ChoiceList
                  aria-label="Team size"
                  variant="compact"
                  items={[
                    { id: "solo", title: "Just me" },
                    { id: "small", title: "2-10", selected: true },
                    { id: "team", title: "11-50" },
                    { id: "scale", title: "50+" },
                  ]}
                />
              </div>

              <div className="ds-card ds-card--md space-y-3">
                <h3 className="text-sm font-semibold text-content">Grid card choices</h3>
                <ChoiceList
                  aria-label="Business model"
                  variant="card"
                  items={[
                    {
                      id: "ecommerce",
                      title: "E-commerce",
                      description: "Product-first online store.",
                      icon: <ShoppingBag className="size-5" />,
                      selected: true,
                    },
                    {
                      id: "course",
                      title: "Course",
                      description: "Training or packaged knowledge.",
                      icon: <GraduationCap className="size-5" />,
                    },
                    {
                      id: "software",
                      title: "Software",
                      description: "App, tool, or SaaS.",
                      icon: <Laptop className="size-5" />,
                    },
                    {
                      id: "service",
                      title: "Service",
                      description: "Done-for-you work.",
                      icon: <Briefcase className="size-5" />,
                    },
                    {
                      id: "marketplace",
                      title: "Marketplace",
                      description: "Two-sided platform.",
                      icon: <Store className="size-5" />,
                    },
                    {
                      id: "other",
                      title: "Other",
                      description: "Does not fit common buckets.",
                      icon: <Layers3 className="size-5" />,
                    },
                  ]}
                />
              </div>
            </div>
          </div>
        </div>
      </ReviewSection>

      <ReviewSection title="Filters And Tabs" description="Repeated controls should not shift layout when selected or hovered.">
        <FilterBar>
          <Button size="sm" variant="secondary">All</Button>
          <Button size="sm" variant="ghost">Ready</Button>
          <Button size="sm" variant="ghost">Blocked</Button>
          <Input className="max-w-64" placeholder="Filter rows" />
        </FilterBar>
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">
            <Callout title="Selected tab" variant="info">
              The panel uses shared callout, spacing, and focus styles.
            </Callout>
          </TabsContent>
          <TabsContent value="activity">
            <Callout title="Activity" variant="neutral">Activity content renders here.</Callout>
          </TabsContent>
          <TabsContent value="settings">
            <Callout title="Settings" variant="warning">Settings content renders here.</Callout>
          </TabsContent>
        </Tabs>
      </ReviewSection>

      <ReviewSection title="Table" description="Table density should support scanning without giant row padding or clipped metadata.">
        <Table variant="surface" size={1}>
          <TableHeader>
            <TableRow hover={false}>
              <TableHeadCell>Item</TableHeadCell>
              <TableHeadCell>Status</TableHeadCell>
              <TableHeadCell>Owner</TableHeadCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {["Workspace source", "Strategy brief", "Creative queue"].map((item, index) => (
              <TableRow key={item}>
                <TableCell className="font-medium text-content">{item}</TableCell>
                <TableCell><StatusBadge status={index === 1 ? "running" : "completed"} /></TableCell>
                <TableCell>{index === 2 ? "System" : "Operator"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ReviewSection>

      <ReviewSection title="Floating Surfaces" description="Menus, popovers, tooltips, dialogs, and alert dialogs should share panel radius and shadow.">
        <div className="flex flex-wrap items-center gap-2">
          <Menu>
            <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>
              <MoreHorizontal /> Menu
            </MenuTrigger>
            <MenuContent>
              <MenuItem>Open detail</MenuItem>
              <MenuItem>Duplicate</MenuItem>
              <MenuSeparator />
              <MenuItem>Archive</MenuItem>
            </MenuContent>
          </Menu>

          <Popover>
            <PopoverTrigger className={buttonClasses({ variant: "outline", size: "sm" })}>
              Popover
            </PopoverTrigger>
            <PopoverContent className="w-72">
              <div className="font-semibold text-content">Popover surface</div>
              <p className="mt-1 text-sm leading-5 text-content-muted">Compact content should stay legible inside floating panels.</p>
            </PopoverContent>
          </Popover>

          <Tooltip>
            <TooltipTrigger className={buttonClasses({ variant: "ghost", size: "sm" })}>
              Tooltip
            </TooltipTrigger>
            <TooltipContent>Tooltip copy</TooltipContent>
          </Tooltip>

          <DialogRoot>
            <DialogTrigger className={buttonClasses({ size: "sm" })}>Dialog</DialogTrigger>
            <DialogContent>
              <DialogTitle>Dialog title</DialogTitle>
              <DialogDescription>
                Dialog body uses shared floating panel styles with readable default header rhythm.
              </DialogDescription>
              <div className="mt-5 flex justify-end gap-2">
                <DialogClose className={buttonClasses({ variant: "secondary", size: "sm" })}>Close</DialogClose>
              </div>
            </DialogContent>
          </DialogRoot>

          <AlertDialog>
            <AlertDialogTrigger className={buttonClasses({ variant: "destructive", size: "sm" })}>
              Alert dialog
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogTitle>Confirm destructive action</AlertDialogTitle>
              <AlertDialogDescription>
                Alert content should be dense and readable, including longer confirmation copy that wraps cleanly.
              </AlertDialogDescription>
              <div className="mt-5 flex justify-end gap-2">
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction>Confirm</AlertDialogAction>
              </div>
            </AlertDialogContent>
          </AlertDialog>
        </div>
        <div className="grid gap-3 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,0.7fr)]">
          <div className="rounded-lg border-[1.5px] border-border bg-surface p-2 text-sm text-content shadow-xl">
            <div className="rounded-[8px] px-3.5 py-[11px]">Open detail</div>
            <div className="rounded-[8px] px-3.5 py-[11px]">Duplicate</div>
            <div className="my-1 h-px bg-border" />
            <div className="rounded-[8px] px-3.5 py-[11px]">Archive</div>
          </div>
          <div className="rounded-lg border-[1.5px] border-border bg-surface p-5 text-sm text-content shadow-xl">
            <div className="font-semibold text-content">Popover surface</div>
            <p className="mt-1 leading-5 text-content-muted">
              Compact content should stay legible inside floating panels.
            </p>
          </div>
          <div className="flex items-start">
            <div className="rounded-[8px] bg-content px-3 py-2 text-xs font-semibold text-surface shadow-lg">
              Tooltip copy
            </div>
          </div>
        </div>
      </ReviewSection>

      <ReviewSection title="Feedback States" description="Empty, error, progress, skeleton, and callout states need consistent surfaces.">
        <div className="grid gap-4 lg:grid-cols-2">
          <EmptyState
            title="No matching rows"
            description="The empty state should stay compact enough for repeated product screens."
            actions={<Button size="sm" variant="secondary">Reset filters</Button>}
          />
          <ErrorState title="Load failed" message="Error states use danger color without expanding into oversized panels." onRetry={() => undefined} />
          <div className="ds-card ds-card--md space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-semibold text-content">Progress</span>
              <span className="text-content-muted">In progress</span>
            </div>
            <Progress value={48} />
          </div>
          <div className="ds-card ds-card--md space-y-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Callout title="Neutral callout" variant="neutral">Neutral copy should not dominate the screen.</Callout>
          <Callout title="Success callout" variant="success">Success copy should be clear but compact.</Callout>
          <Callout title="Warning callout" variant="warning">Warning copy should carry visual weight without shouting.</Callout>
          <Callout title="Danger callout" variant="danger">Danger copy should be obvious and still scannable.</Callout>
        </div>
      </ReviewSection>
    </div>
  );
}

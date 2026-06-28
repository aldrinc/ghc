import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Edit3,
  Loader2,
  LogOut,
} from 'lucide-react';
import { useClerk } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';

import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button, buttonClasses } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldRoot,
  FormRoot,
} from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  ChoiceList,
  FirstRunShell,
  OnboardingIcon,
  OnboardingProgressRail,
  ReviewChangesPanel,
  SetupChecklist,
  type OnboardingIconName,
} from '@/components/onboarding';
import {
  useClientFoundationReadiness,
  useCreateClient,
  useExtractMarketingAgentContext,
  useStartMarketingAgentSetup,
  type MarketingAgentExtractionResponse,
  type MarketingAgentSetupPayload,
} from '@/api/clients';
import { toast } from '@/components/ui/toast';
import { useProductContext } from '@/contexts/ProductContext';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import type { Client } from '@/types/common';

type BusinessType = 'new' | 'existing';
type OfferingKind = NonNullable<MarketingAgentSetupPayload['offering_kind']>;

type WizardStep =
  | 'workspace'
  | 'business-type'
  | 'existing-url'
  | 'existing-competitors'
  | 'existing-review'
  | 'new-business-model'
  | 'new-offering-kind'
  | 'new-offering-name'
  | 'new-offering-description'
  | 'new-pricing'
  | 'new-competitors'
  | 'new-review';

type SetupDraft = {
  workspaceName: string;
  businessType: BusinessType | '';
  businessUrl: string;
  businessName: string;
  businessModel: string;
  customBusinessModel: string;
  offeringKind: OfferingKind | '';
  customOfferingKind: string;
  offeringType: string;
  offeringName: string;
  offeringDescription: string;
  productCategory: string;
  price: string;
  startingRate: string;
  pricingModel: string;
  customPricingModel: string;
  pricingIntent: 'known' | 'later' | '';
  competitorUrls: string;
};

type ReviewEditMode = 'workspace' | 'offer' | 'pricing' | 'competitors' | 'all';

type OnboardingWizardProps = {
  clientId?: string;
  clientName?: string;
  triggerLabel?: string;
  pageHeaderAction?: ReactNode;
  pageHeaderEndAction?: ReactNode;
  showSetupLogout?: boolean;
  onCompleted?: (payload: {
    clientId: string;
    clientName?: string;
    productId: string;
    productName?: string;
  }) => void;
  variant?: 'modal' | 'page';
};

type CompletedSetup = {
  clientId: string;
  clientName?: string;
  productId: string;
  productName?: string;
  workflowRunId: string;
  temporalWorkflowId?: string;
};

type StepLayoutKind = 'simple' | 'choice' | 'review' | 'edit';

const stepLayoutClassName: Record<StepLayoutKind, string> = {
  simple: 'mos-onboarding-form--simple',
  choice: 'mos-onboarding-form--choice',
  review: 'mos-onboarding-form--review',
  edit: 'mos-onboarding-form--edit',
};

const businessModelOptions = [
  { label: 'Select business model', value: '' },
  { label: 'E-commerce product', value: 'ecommerce' },
  { label: 'Digital product or course', value: 'digital_product' },
  { label: 'SaaS or software', value: 'saas_subscription' },
  { label: 'Service business', value: 'service_business' },
  { label: 'Lead generation', value: 'lead_generation' },
  { label: 'Affiliate', value: 'affiliate' },
  { label: 'Marketplace or platform', value: 'marketplace' },
  { label: 'Other', value: 'other' },
];

const businessModelChoiceOptions = [
  {
    id: 'ecommerce',
    title: 'E-commerce product',
    description: 'A product-first business selling through an online store.',
    icon: <OnboardingIcon name="model-ecommerce" />,
  },
  {
    id: 'digital_product',
    title: 'Digital product or course',
    description:
      'A course, template, download, training, or packaged knowledge.',
    icon: <OnboardingIcon name="model-digital-product" />,
  },
  {
    id: 'service_business',
    title: 'Service business',
    description:
      'Done-for-you work, consulting, implementation, or local services.',
    icon: <OnboardingIcon name="model-service" />,
  },
  {
    id: 'saas_subscription',
    title: 'SaaS or software',
    description: 'An app, tool, or platform customers use to get a job done.',
    icon: <OnboardingIcon name="model-saas" />,
  },
  {
    id: 'lead_generation',
    title: 'Lead generation',
    description:
      'A business built around qualified inquiries, booked calls, or buyer introductions.',
    icon: <OnboardingIcon name="model-lead-generation" />,
  },
  {
    id: 'affiliate',
    title: 'Affiliate',
    description: "Promote another company's offer and earn commission.",
    icon: <OnboardingIcon name="model-affiliate" />,
  },
  {
    id: 'marketplace',
    title: 'Marketplace or platform',
    description: 'A two-sided network, directory, or transaction platform.',
    icon: <OnboardingIcon name="model-marketplace" />,
  },
  {
    id: 'other',
    title: 'Other',
    description: 'Use this when the model does not fit the common buckets.',
    icon: <OnboardingIcon name="model-other" />,
  },
];

const offeringKindOptions: Array<{
  id: OfferingKind;
  title: string;
  description: string;
}> = [
  {
    id: 'product',
    title: 'Product',
    description: 'A physical, digital, or packaged thing people buy.',
  },
  {
    id: 'service',
    title: 'Service',
    description:
      'Done-for-you, advisory, implementation, coaching, or local services.',
  },
  {
    id: 'software',
    title: 'Software or SaaS',
    description: 'An app, tool, platform, or subscription product.',
  },
  {
    id: 'course',
    title: 'Course or digital product',
    description: 'Training, cohort, template, download, or education offer.',
  },
  {
    id: 'lead_generation',
    title: 'Lead-gen offer',
    description:
      'A free or paid offer that creates qualified leads or booked calls.',
  },
  {
    id: 'marketplace',
    title: 'Marketplace or platform',
    description: 'A two-sided network, directory, or transaction platform.',
  },
  {
    id: 'other',
    title: 'Other',
    description: 'Use this when the offer does not fit the common buckets.',
  },
];

const offeringIconByKind: Record<OfferingKind, OnboardingIconName> = {
  product: 'offer-product',
  service: 'offer-service',
  software: 'offer-software',
  course: 'offer-course',
  lead_generation: 'offer-lead-generation',
  marketplace: 'offer-marketplace',
  other: 'offer-other',
};

const directOfferingByBusinessModel: Record<
  string,
  { kind: OfferingKind; type: string }
> = {
  ecommerce: { kind: 'product', type: 'product' },
  digital_product: { kind: 'course', type: 'digital_product' },
  service_business: { kind: 'service', type: 'service' },
  saas_subscription: { kind: 'software', type: 'software' },
  lead_generation: { kind: 'lead_generation', type: 'lead_generation' },
  marketplace: { kind: 'marketplace', type: 'marketplace' },
};

const initialDraft = (clientName?: string): SetupDraft => ({
  workspaceName: clientName || '',
  businessType: '',
  businessUrl: '',
  businessName: '',
  businessModel: '',
  customBusinessModel: '',
  offeringKind: '',
  customOfferingKind: '',
  offeringType: '',
  offeringName: '',
  offeringDescription: '',
  productCategory: '',
  price: '',
  startingRate: '',
  pricingModel: '',
  customPricingModel: '',
  pricingIntent: '',
  competitorUrls: '',
});

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function parseUrls(value: string): string[] {
  return value
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (item.includes('://') ? item : `https://${item}`));
}

function validateUrls(label: string, value: string): string[] {
  const urls = parseUrls(value);
  const invalid = urls.filter((url) => {
    try {
      const parsed = new URL(url);
      return parsed.protocol !== 'http:' && parsed.protocol !== 'https:';
    } catch {
      return true;
    }
  });
  if (invalid.length) {
    throw new Error(`${label} must be valid http/https URLs.`);
  }
  return urls;
}

function hasValidUrls(value: string, required = false): boolean {
  if (!value.trim()) return !required;
  try {
    const urls = validateUrls('URLs', value);
    return required ? urls.length > 0 : true;
  } catch {
    return false;
  }
}

function normalizeUrlForCacheKey(url: string): string {
  const parsed = new URL(url);
  parsed.hash = '';
  const path = parsed.pathname.replace(/\/+$/g, '');
  return `${parsed.protocol}//${parsed.host.toLowerCase()}${path || '/'}${parsed.search}`;
}

function extractionRequestCacheKey(
  businessUrl: string,
  competitorUrls: string[],
): string {
  return JSON.stringify({
    business_url: normalizeUrlForCacheKey(businessUrl),
    competitor_urls: Array.from(
      new Set(competitorUrls.map(normalizeUrlForCacheKey)),
    ).sort(),
  });
}

function offeringLabel(value: string) {
  return (
    offeringKindOptions.find((option) => option.id === value)?.title ||
    value ||
    'Not set'
  );
}

function displayOfferingKind(value: string, customValue = '') {
  if (value === 'other') return customValue.trim() || 'Other';
  return offeringLabel(value);
}

function businessModelLabel(value: string) {
  return (
    businessModelOptions.find((option) => option.value === value)?.label ||
    value ||
    'Not set'
  );
}

function displayBusinessModel(value: string, customValue = '') {
  if (value === 'other') return customValue.trim() || 'Other';
  return businessModelLabel(value);
}

function pricingModelLabel(
  kind: OfferingKind | '',
  value: string,
  customValue = '',
) {
  if (value === 'other') return customValue.trim() || 'Other';
  const options = kind
    ? pricingModelOptionsByKind[kind]
    : pricingModelOptionsByKind.other;
  return options.find((option) => option.value === value)?.label || value || '';
}

function stageLabel(value: BusinessType | '') {
  if (value === 'existing') return 'Already live business';
  if (value === 'new') return 'New business';
  return 'Not set';
}

function displayValue(value: string, fallback = 'Not set') {
  return value.trim() || fallback;
}

function normalizeBusinessModel(value: unknown): string {
  const text = cleanText(value)
    .toLowerCase()
    .replace(/[-\s]+/g, '_');
  if (!text) return '';
  if (text.includes('saas') || text.includes('subscription'))
    return 'saas_subscription';
  if (
    text.includes('service') ||
    text.includes('agency') ||
    text.includes('consult')
  )
    return 'service_business';
  if (
    text.includes('commerce') ||
    text.includes('retail') ||
    text.includes('shop')
  )
    return 'ecommerce';
  if (text.includes('course') || text.includes('digital'))
    return 'digital_product';
  if (text.includes('coach')) return 'service_business';
  if (text.includes('lead')) return 'lead_generation';
  if (text.includes('affiliate') || text.includes('commission'))
    return 'affiliate';
  if (text.includes('marketplace')) return 'marketplace';
  if (businessModelOptions.some((option) => option.value === text)) return text;
  return 'other';
}

function normalizeOfferingKind(value: unknown): OfferingKind | '' {
  const text = cleanText(value)
    .toLowerCase()
    .replace(/[-\s]+/g, '_');
  if (!text) return '';
  if (
    text.includes('service') ||
    text.includes('agency') ||
    text.includes('consult')
  )
    return 'service';
  if (
    text.includes('software') ||
    text.includes('saas') ||
    text.includes('app')
  )
    return 'software';
  if (text.includes('course') || text.includes('training')) return 'course';
  if (text.includes('lead')) return 'lead_generation';
  if (text.includes('marketplace')) return 'marketplace';
  if (
    text.includes('product') ||
    text.includes('ecommerce') ||
    text.includes('physical')
  )
    return 'product';
  if (offeringKindOptions.some((option) => option.id === text))
    return text as OfferingKind;
  return 'other';
}

function extractionValue(
  extraction: MarketingAgentExtractionResponse | null,
  key: string,
): string {
  if (!extraction?.fields?.[key]) return '';
  const value = extraction.fields[key].value;
  return typeof value === 'string' || typeof value === 'number'
    ? String(value).trim()
    : '';
}

const pricingModelOptionsByKind: Record<
  OfferingKind,
  Array<{ label: string; value: string }>
> = {
  product: [
    { label: 'One-time purchase', value: 'one_time' },
    { label: 'Monthly', value: 'monthly' },
    { label: 'Subscription', value: 'subscription' },
    { label: 'Custom', value: 'custom' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
  service: [
    { label: 'Hourly', value: 'hourly' },
    { label: 'Monthly', value: 'monthly' },
    { label: 'Project', value: 'project' },
    { label: 'Retainer', value: 'retainer' },
    { label: 'Performance', value: 'performance' },
    { label: 'Consultation', value: 'consultation' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
  software: [
    { label: 'Monthly', value: 'monthly' },
    { label: 'Subscription', value: 'subscription' },
    { label: 'Usage-based', value: 'usage_based' },
    { label: 'Seat-based', value: 'seat_based' },
    { label: 'Freemium', value: 'freemium' },
    { label: 'Custom', value: 'custom' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
  course: [
    { label: 'One-time purchase', value: 'one_time' },
    { label: 'Monthly', value: 'monthly' },
    { label: 'Subscription', value: 'subscription' },
    { label: 'Custom', value: 'custom' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
  lead_generation: [
    { label: 'Free', value: 'free' },
    { label: 'Paid follow-up', value: 'paid_followup' },
    { label: 'Consultation', value: 'consultation' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
  marketplace: [
    { label: 'Monthly', value: 'monthly' },
    { label: 'Commission', value: 'commission' },
    { label: 'Subscription', value: 'subscription' },
    { label: 'Listing fee', value: 'listing_fee' },
    { label: 'Transaction fee', value: 'transaction_fee' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
  other: [
    { label: 'One-time purchase', value: 'one_time' },
    { label: 'Monthly', value: 'monthly' },
    { label: 'Subscription', value: 'subscription' },
    { label: 'Custom', value: 'custom' },
    { label: 'Other', value: 'other' },
    { label: 'Not sure', value: 'not_sure' },
  ],
};

function offeringCopy(kind: OfferingKind | '') {
  const fallback = {
    nameTitle: 'What should your agent work on first?',
    nameLabel: 'Offer name',
    namePlaceholder: 'Example: Starter offer',
    outcomeTitle: 'What does the buyer or user get?',
    outcomeLabel: 'Buyer outcome',
    outcomePlaceholder: 'Describe what someone gets and why it matters.',
    pricingTitle: 'How do customers pay, if they do?',
    pricingLabel: 'Payment details',
    pricingPlaceholder: 'Example: quote-based, subscription, one-time fee',
    modelLabel: 'Payment model',
  };

  if (kind === 'product') {
    return {
      nameTitle: 'What is the product called?',
      nameLabel: 'Product name',
      namePlaceholder: 'Example: Starter Kit',
      outcomeTitle: 'What does the product help buyers do?',
      outcomeLabel: 'Buyer outcome',
      outcomePlaceholder:
        'Describe what buyers get or accomplish with the product.',
      pricingTitle: 'What is the product price?',
      pricingLabel: 'Product price',
      pricingPlaceholder: 'Example: $49',
      modelLabel: 'Pricing model',
    };
  }
  if (kind === 'service') {
    return {
      nameTitle: 'What service do you provide?',
      nameLabel: 'Service name',
      namePlaceholder: 'Example: Growth Sprint',
      outcomeTitle: 'What outcome does the service create for clients?',
      outcomeLabel: 'Client outcome',
      outcomePlaceholder: 'Describe the result clients hire you to create.',
      pricingTitle: 'How do you charge for your service?',
      pricingLabel: 'Rate or starting point',
      pricingPlaceholder: 'Example: $2,500/month, hourly, quote-based',
      modelLabel: 'Charge model',
    };
  }
  if (kind === 'software') {
    return {
      nameTitle: 'What is the software called?',
      nameLabel: 'Software name',
      namePlaceholder: 'Example: Revenue Dashboard',
      outcomeTitle: 'What job does the software help customers do?',
      outcomeLabel: 'Customer job',
      outcomePlaceholder:
        'Describe the job customers use the software to complete.',
      pricingTitle: 'How is it priced?',
      pricingLabel: 'Starting price',
      pricingPlaceholder: 'Example: $99/month, usage-based, custom',
      modelLabel: 'Pricing model',
    };
  }
  if (kind === 'course') {
    return {
      nameTitle: 'What is the course or digital product called?',
      nameLabel: 'Course or digital product name',
      namePlaceholder: 'Example: Acquisition OS',
      outcomeTitle: 'What does the customer learn or achieve?',
      outcomeLabel: 'Customer outcome',
      outcomePlaceholder: 'Describe the transformation or skill customers get.',
      pricingTitle: 'What is the enrollment or purchase price?',
      pricingLabel: 'Enrollment or purchase price',
      pricingPlaceholder: 'Example: $299, $1,500 cohort, free',
      modelLabel: 'Pricing model',
    };
  }
  if (kind === 'lead_generation') {
    return {
      nameTitle: 'What offer should your agent start with?',
      nameLabel: 'Lead-gen offer',
      namePlaceholder: 'Example: Free audit, consultation, guide',
      outcomeTitle: 'What does someone get after opting in?',
      outcomeLabel: 'Opt-in outcome',
      outcomePlaceholder:
        'Describe what the lead receives and what happens next.',
      pricingTitle: 'Is there a paid offer after this?',
      pricingLabel: 'Paid follow-up',
      pricingPlaceholder:
        'Example: free consult, $500 audit, quote-based service',
      modelLabel: 'Follow-up model',
    };
  }
  if (kind === 'marketplace') {
    return {
      nameTitle:
        'What side of the marketplace should your agent focus on first?',
      nameLabel: 'Marketplace focus',
      namePlaceholder: 'Example: Homeowners looking for contractors',
      outcomeTitle: 'What problem does that side need solved?',
      outcomeLabel: 'User problem',
      outcomePlaceholder:
        'Describe the demand-side or supply-side problem to solve first.',
      pricingTitle: 'How does the platform make money?',
      pricingLabel: 'Monetization details',
      pricingPlaceholder: 'Example: commission, listing fee, subscription',
      modelLabel: 'Revenue model',
    };
  }
  return fallback;
}

function defaultPricingModel(kind: OfferingKind | '') {
  if (kind === 'product' || kind === 'course') return 'one_time';
  if (kind === 'software') return 'subscription';
  if (kind === 'marketplace') return 'commission';
  return 'not_sure';
}

function stepTitle(step: WizardStep, draft: SetupDraft) {
  const copy = offeringCopy(draft.offeringKind);
  if (step === 'workspace') return 'What should we call this workspace?';
  if (step === 'business-type')
    return 'Is this a new or already live business?';
  if (step === 'existing-url') return 'What is the business website?';
  if (step === 'existing-competitors')
    return 'Any competitors your agent should know about?';
  if (step === 'existing-review' || step === 'new-review')
    return 'Review workspace';
  if (step === 'new-business-model')
    return 'How will this business make money?';
  if (step === 'new-offering-kind')
    return draft.businessModel === 'affiliate'
      ? 'What kind of offer are you promoting?'
      : 'What do you sell or plan to sell?';
  if (step === 'new-offering-name') return copy.nameTitle;
  if (step === 'new-offering-description') return copy.outcomeTitle;
  if (step === 'new-pricing') return copy.pricingTitle;
  if (step === 'new-competitors')
    return 'Any competitors your agent should know about?';
  return 'Review your workspace';
}

function stepDescription(step: WizardStep) {
  if (step === 'workspace')
    return 'Use the business name or a working name. You can change it later.';
  if (step === 'business-type')
    return "We'll start from scratch or research your existing business to get you setup.";
  if (step === 'existing-url')
    return 'We will use the site as source material and ask you to confirm what we find.';
  if (step === 'existing-review' || step === 'new-review')
    return 'Check the changes before creating the workspace.';
  if (step === 'new-offering-kind') return 'Choose the closest offer type.';
  if (step === 'new-offering-name')
    return 'Use the customer-facing name if you have one.';
  if (step === 'new-offering-description')
    return 'One to three sentences is enough for setup.';
  if (step === 'new-pricing')
    return 'Optional — you can set exact pricing later.';
  if (step === 'existing-competitors' || step === 'new-competitors')
    return 'Optional';
  return undefined;
}

function stepProgressValue(step: WizardStep) {
  const values: Record<WizardStep, number> = {
    workspace: 12,
    'business-type': 24,
    'existing-url': 48,
    'existing-competitors': 72,
    'existing-review': 100,
    'new-business-model': 36,
    'new-offering-kind': 48,
    'new-offering-name': 60,
    'new-offering-description': 72,
    'new-pricing': 84,
    'new-competitors': 92,
    'new-review': 100,
  };

  return values[step];
}

function ReviewFactRow({
  label,
  value,
  muted,
  clamp,
}: {
  label: string;
  value: ReactNode;
  muted?: boolean;
  clamp?: boolean;
}) {
  return (
    <div className="grid gap-1 border-t border-border/70 px-4 py-3 first:border-t-0 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-5">
      <dt className="text-xs font-medium uppercase tracking-[0.08em] text-content-muted">
        {label}
      </dt>
      <dd
        className={
          muted
            ? 'min-w-0 text-sm text-content-muted'
            : 'min-w-0 text-sm font-medium leading-6 text-content'
        }
      >
        <span
          className={
            clamp ? 'line-clamp-3 whitespace-pre-wrap' : 'whitespace-pre-wrap'
          }
        >
          {value}
        </span>
      </dd>
    </div>
  );
}

function ReviewSection({
  title,
  onEdit,
  children,
}: {
  title: string;
  onEdit: () => void;
  children: ReactNode;
}) {
  return (
    <section
      className="overflow-hidden rounded-md border border-border bg-surface"
      aria-label={title}
    >
      <div className="flex items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
        <h2 className="text-sm font-semibold text-content">{title}</h2>
        <Button type="button" size="xs" variant="ghost" onClick={onEdit}>
          <Edit3 className="h-3.5 w-3.5" />
          Edit
        </Button>
      </div>
      <dl>{children}</dl>
    </section>
  );
}

export function OnboardingWizard({
  clientId,
  clientName,
  triggerLabel = 'Start onboarding',
  pageHeaderAction,
  pageHeaderEndAction,
  showSetupLogout = true,
  onCompleted,
  variant = 'modal',
}: OnboardingWizardProps) {
  const navigate = useNavigate();
  const { signOut } = useClerk();
  const { selectWorkspace } = useWorkspace();
  const { selectProduct } = useProductContext();
  const isPage = variant === 'page';
  const [open, setOpen] = useState(isPage);
  const [step, setStep] = useState<WizardStep>('workspace');
  const [draft, setDraft] = useState<SetupDraft>(() =>
    initialDraft(clientName),
  );
  const [activeClientId, setActiveClientId] = useState<string | null>(
    clientId ?? null,
  );
  const [extraction, setExtraction] =
    useState<MarketingAgentExtractionResponse | null>(null);
  const [extractionCacheKey, setExtractionCacheKey] = useState<string | null>(
    null,
  );
  const [completedSetup, setCompletedSetup] = useState<CompletedSetup | null>(
    null,
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [reviewEditMode, setReviewEditMode] = useState<ReviewEditMode | null>(
    null,
  );
  const [isMobileViewport, setIsMobileViewport] = useState(() => {
    if (
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function'
    )
      return false;
    return window.matchMedia('(max-width: 767px)').matches;
  });
  const createClient = useCreateClient({ showSuccessToast: false });
  const extractMarketingAgent = useExtractMarketingAgentContext();
  const startSetup = useStartMarketingAgentSetup();
  const setupAutoOpenRef = useRef(false);
  const { data: foundationReadiness } = useClientFoundationReadiness(
    completedSetup?.clientId,
    completedSetup?.productId,
    {
      enabled: Boolean(completedSetup),
      refetchIntervalMs: 15000,
    },
  );

  useEffect(() => {
    if (!open && !isPage) {
      setStep('workspace');
      setDraft(initialDraft(clientName));
      setActiveClientId(clientId ?? null);
      setExtraction(null);
      setExtractionCacheKey(null);
      setCompletedSetup(null);
      setReviewEditMode(null);
    }
  }, [clientId, clientName, isPage, open]);

  useEffect(() => {
    if (step !== 'existing-review' && step !== 'new-review') {
      setReviewEditMode(null);
    }
  }, [step]);

  useEffect(() => {
    if (
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function'
    )
      return;
    const mediaQuery = window.matchMedia('(max-width: 767px)');
    const handleChange = () => setIsMobileViewport(mediaQuery.matches);
    handleChange();
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  const steps = useMemo<WizardStep[]>(() => {
    if (draft.businessType === 'existing') {
      return [
        'workspace',
        'business-type',
        'existing-url',
        'existing-competitors',
        'existing-review',
      ];
    }
    if (draft.businessType === 'new') {
      const needsOfferingKindStep = draft.businessModel === 'affiliate';
      return [
        'workspace',
        'business-type',
        'new-business-model',
        ...(needsOfferingKindStep
          ? (['new-offering-kind'] as WizardStep[])
          : []),
        'new-offering-name',
        'new-offering-description',
        'new-pricing',
        'new-competitors',
        'new-review',
      ];
    }
    return ['workspace', 'business-type'];
  }, [draft.businessType]);

  const stepIndex = Math.max(0, steps.indexOf(step));
  const progressValue = stepProgressValue(step);
  const isSubmitting =
    createClient.isPending ||
    extractMarketingAgent.isPending ||
    startSetup.isPending;
  const isCheckingSite =
    step === 'existing-competitors' &&
    (createClient.isPending || extractMarketingAgent.isPending);
  const isSelectionOnlyStep =
    step === 'business-type' ||
    (step === 'new-business-model' && draft.businessModel !== 'other') ||
    (step === 'new-offering-kind' && draft.offeringKind !== 'other') ||
    (step === 'new-pricing' && draft.pricingIntent !== 'known');
  const stepLayoutKind: StepLayoutKind = reviewEditMode
    ? 'edit'
    : step === 'existing-review' || step === 'new-review'
      ? 'review'
      : isSelectionOnlyStep
        ? 'choice'
        : 'simple';
  const pricingText =
    draft.offeringKind === 'service' ? draft.startingRate : draft.price;
  const pricingModelText = pricingModelLabel(
    draft.offeringKind,
    draft.pricingModel,
    draft.customPricingModel,
  );
  const resolvedPricingModel =
    draft.pricingModel === 'other'
      ? draft.customPricingModel.trim()
      : draft.pricingModel.trim();
  const resolvedBusinessModel =
    draft.businessModel === 'other'
      ? draft.customBusinessModel.trim()
      : draft.businessModel.trim();
  const hasPricingDetails = Boolean(pricingText.trim() || resolvedPricingModel);
  const canCreate = Boolean(
    draft.workspaceName.trim() &&
    draft.businessType &&
    resolvedBusinessModel &&
    draft.offeringKind &&
    draft.offeringType.trim() &&
    draft.offeringName.trim() &&
    draft.offeringDescription.trim(),
  );
  const stepIsValid = (() => {
    if (step === 'workspace') return Boolean(draft.workspaceName.trim());
    if (step === 'business-type') return Boolean(draft.businessType);
    if (step === 'existing-url') return hasValidUrls(draft.businessUrl, true);
    if (step === 'existing-competitors')
      return (
        hasValidUrls(draft.businessUrl, true) &&
        hasValidUrls(draft.competitorUrls)
      );
    if (step === 'new-business-model')
      return draft.businessModel === 'other'
        ? Boolean(draft.customBusinessModel.trim())
        : Boolean(draft.businessModel.trim());
    if (step === 'new-offering-kind')
      return draft.offeringKind === 'other'
        ? Boolean(draft.customOfferingKind.trim())
        : Boolean(draft.offeringKind);
    if (step === 'new-offering-name') return Boolean(draft.offeringName.trim());
    if (step === 'new-offering-description')
      return Boolean(draft.offeringDescription.trim());
    if (step === 'new-pricing') {
      if (!draft.pricingIntent) return false;
      if (draft.pricingIntent === 'later') return true;
      if (draft.pricingModel === 'other')
        return Boolean(draft.customPricingModel.trim());
      return Boolean(draft.pricingModel.trim() || pricingText.trim());
    }
    if (step === 'new-competitors') return hasValidUrls(draft.competitorUrls);
    if (step === 'existing-review' || step === 'new-review') {
      return (
        canCreate &&
        hasValidUrls(draft.competitorUrls) &&
        (draft.businessType !== 'existing' ||
          hasValidUrls(draft.businessUrl, true))
      );
    }
    return false;
  })();
  const reviewEditIsValid = (mode: ReviewEditMode) => {
    const workspaceValid = Boolean(
      draft.workspaceName.trim() && resolvedBusinessModel,
    );
    const offerValid = Boolean(
      draft.offeringKind &&
      draft.offeringName.trim() &&
      draft.offeringType.trim() &&
      draft.offeringDescription.trim(),
    );
    const competitorsValid = hasValidUrls(draft.competitorUrls);
    if (mode === 'workspace') return workspaceValid;
    if (mode === 'offer') return offerValid;
    if (mode === 'competitors') return competitorsValid;
    if (mode === 'pricing') return true;
    return workspaceValid && offerValid && competitorsValid;
  };

  const reviewItems = [
    {
      id: 'workspace',
      label: 'Workspace profile',
      status:
        draft.workspaceName.trim() && draft.businessType
          ? ('added' as const)
          : ('missing' as const),
      detail: `${draft.workspaceName || 'No workspace'} - ${draft.businessType || 'No stage'}`,
    },
    {
      id: 'offer',
      label: 'First offer',
      status: draft.offeringName.trim()
        ? ('added' as const)
        : ('missing' as const),
      detail: `${displayOfferingKind(draft.offeringKind, draft.customOfferingKind)} - ${draft.offeringName || 'No name'}`,
    },
    {
      id: 'pricing',
      label: 'Pricing',
      status: hasPricingDetails ? ('updated' as const) : ('missing' as const),
      detail: hasPricingDetails
        ? [pricingModelText, pricingText.trim()].filter(Boolean).join(' - ')
        : 'Set later',
    },
  ];

  const reviewAttentionItems = [
    !resolvedBusinessModel
      ? {
          id: 'business-model',
          label: 'Business model',
          detail: 'Required before creating the workspace.',
          tone: 'danger' as const,
          action: 'Edit workspace',
          editMode: 'workspace' as const,
        }
      : null,
    !draft.offeringKind
      ? {
          id: 'offering-kind',
          label: 'Offering kind',
          detail: 'Required before creating the workspace.',
          tone: 'danger' as const,
          action: 'Edit offer',
          editMode: 'offer' as const,
        }
      : null,
    !draft.offeringName.trim() ||
    !draft.offeringType.trim() ||
    !draft.offeringDescription.trim()
      ? {
          id: 'offer-details',
          label: 'Offer details',
          detail:
            'Name, type, and outcome need enough context before setup can start.',
          tone: 'danger' as const,
          action: 'Edit offer',
          editMode: 'offer' as const,
        }
      : null,
    !hasPricingDetails
      ? {
          id: 'pricing',
          label: 'Pricing',
          detail:
            'No charge model or rate was found. You can add it now or set it later.',
          tone: 'warning' as const,
          action: 'Add pricing',
          editMode: 'pricing' as const,
        }
      : null,
  ].filter(Boolean) as Array<{
    id: string;
    label: string;
    detail: string;
    tone: 'danger' | 'warning';
    action: string;
    editMode: ReviewEditMode;
  }>;

  const ensureClient = async (): Promise<string> => {
    if (activeClientId) return activeClientId;
    const created = (await createClient.mutateAsync({
      name: draft.workspaceName.trim(),
      strategyV2Enabled: true,
    })) as Client;
    if (!created?.id) throw new Error('Client creation failed');
    setActiveClientId(created.id);
    return created.id;
  };

  const completeOnboarding = useCallback(
    (payload: CompletedSetup) => {
      if (onCompleted) {
        onCompleted(payload);
        return;
      }
      selectWorkspace(payload.clientId, { name: payload.clientName });
      selectProduct(
        payload.productId,
        { title: payload.productName, client_id: payload.clientId },
        { clientId: payload.clientId },
      );
      navigate('/workspaces/foundation-ready');
    },
    [navigate, onCompleted, selectProduct, selectWorkspace],
  );

  useEffect(() => {
    if (!completedSetup) return;
    if (
      foundationReadiness?.status === 'foundation_ready' &&
      !setupAutoOpenRef.current
    ) {
      setupAutoOpenRef.current = true;
      completeOnboarding(completedSetup);
    }
  }, [completeOnboarding, completedSetup, foundationReadiness?.status]);

  const goBack = () => {
    const index = steps.indexOf(step);
    if (index > 0) setStep(steps[index - 1]);
  };

  const applyExtraction = (
    result: MarketingAgentExtractionResponse,
    cacheKey: string,
  ) => {
    setExtraction(result);
    setExtractionCacheKey(cacheKey);
    setDraft((current) => {
      const nextKind = normalizeOfferingKind(
        extractionValue(result, 'offering_kind'),
      );
      const nextBusinessModel = normalizeBusinessModel(
        extractionValue(result, 'business_model'),
      );
      const rawPrice = extractionValue(result, 'price');
      return {
        ...current,
        businessName:
          extractionValue(result, 'business_name') || current.workspaceName,
        businessModel: nextBusinessModel,
        customBusinessModel:
          nextBusinessModel === 'other'
            ? extractionValue(result, 'business_model')
            : '',
        offeringKind: nextKind,
        customOfferingKind:
          nextKind === 'other' ? extractionValue(result, 'offering_kind') : '',
        offeringType:
          extractionValue(result, 'offering_type') ||
          extractionValue(result, 'category'),
        offeringName: extractionValue(result, 'offering_name'),
        offeringDescription: extractionValue(result, 'offering_description'),
        productCategory: extractionValue(result, 'category'),
        pricingModel: extractionValue(result, 'pricing_model'),
        customPricingModel: '',
        price: nextKind === 'service' ? '' : rawPrice,
        startingRate: nextKind === 'service' ? rawPrice : '',
        pricingIntent: rawPrice ? 'known' : 'later',
      };
    });
  };

  const goNext = async () => {
    setFieldErrors({});
    try {
      if (step === 'workspace') {
        if (!draft.workspaceName.trim()) {
          setFieldErrors({ workspaceName: 'Workspace name is required.' });
          return;
        }
        setStep('business-type');
        return;
      }
      if (step === 'business-type') {
        if (!draft.businessType) {
          toast.error('Choose new or existing business.');
          return;
        }
        setStep(
          draft.businessType === 'existing'
            ? 'existing-url'
            : 'new-business-model',
        );
        return;
      }
      if (step === 'existing-url') {
        validateUrls('Business website', draft.businessUrl);
        setStep('existing-competitors');
        return;
      }
      if (step === 'existing-competitors') {
        const urls = validateUrls('Competitor websites', draft.competitorUrls);
        const [businessUrl] = validateUrls(
          'Business website',
          draft.businessUrl,
        );
        const cacheKey = extractionRequestCacheKey(businessUrl, urls);
        if (extraction && extractionCacheKey === cacheKey) {
          setStep('existing-review');
          return;
        }
        const ensuredClientId = await ensureClient();
        const result = await extractMarketingAgent.mutateAsync({
          clientId: ensuredClientId,
          payload: {
            business_url: businessUrl,
            competitor_urls: urls,
          },
        });
        applyExtraction(result, cacheKey);
        setStep('existing-review');
        return;
      }
      if (step === 'new-business-model') {
        if (!draft.businessModel.trim()) {
          toast.error('Choose a business model.');
          return;
        }
        if (draft.businessModel === 'other') {
          if (!draft.customBusinessModel.trim()) {
            setFieldErrors({
              customBusinessModel: 'Describe how this business makes money.',
            });
            return;
          }
          setDraft((current) => ({
            ...current,
            offeringKind: 'other',
            customOfferingKind: current.customBusinessModel,
            offeringType: current.customBusinessModel,
          }));
          setStep('new-offering-name');
          return;
        }
        if (draft.businessModel === 'affiliate') {
          setStep('new-offering-kind');
          return;
        }
        const directOffering =
          directOfferingByBusinessModel[draft.businessModel];
        if (directOffering) {
          setDraft((current) => ({
            ...current,
            offeringKind: directOffering.kind,
            offeringType: directOffering.type,
            customOfferingKind: '',
          }));
          setStep('new-offering-name');
          return;
        }
        setStep('new-offering-kind');
        return;
      }
      if (step === 'new-offering-kind') {
        if (!draft.offeringKind) {
          toast.error('Choose what you sell.');
          return;
        }
        if (
          draft.offeringKind === 'other' &&
          !draft.customOfferingKind.trim()
        ) {
          setFieldErrors({ customOfferingKind: 'Describe the offer type.' });
          return;
        }
        setDraft((current) => ({
          ...current,
          offeringType:
            current.offeringKind === 'other'
              ? current.customOfferingKind
              : current.offeringType || current.offeringKind,
        }));
        setStep('new-offering-name');
        return;
      }
      if (step === 'new-offering-name') {
        if (!draft.offeringName.trim()) {
          setFieldErrors({ offeringName: 'Offer name is required.' });
          return;
        }
        setStep('new-offering-description');
        return;
      }
      if (step === 'new-offering-description') {
        if (!draft.offeringDescription.trim()) {
          setFieldErrors({
            offeringDescription: 'Describe what the buyer gets.',
          });
          return;
        }
        setStep('new-pricing');
        return;
      }
      if (step === 'new-pricing') {
        if (!draft.pricingIntent) {
          toast.error('Choose whether pricing is known yet.');
          return;
        }
        setStep('new-competitors');
        return;
      }
      if (step === 'new-competitors') {
        validateUrls('Competitor websites', draft.competitorUrls);
        setStep('new-review');
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Unable to continue.',
      );
    }
  };

  const handleSubmit = async () => {
    try {
      if (!canCreate) {
        toast.error(
          'Complete the required setup fields before creating the workspace.',
        );
        return;
      }
      const ensuredClientId = await ensureClient();
      const urls = validateUrls('Competitor websites', draft.competitorUrls);
      const pricingKnownForPayload =
        draft.businessType === 'existing'
          ? Boolean(pricingText.trim() || resolvedPricingModel)
          : draft.pricingIntent === 'known';
      const payload: MarketingAgentSetupPayload = {
        business_type: draft.businessType || 'new',
        input_mode:
          draft.businessType === 'existing' ? 'source_extract' : 'manual_seed',
        business_url:
          draft.businessType === 'existing'
            ? validateUrls('Business website', draft.businessUrl)[0]
            : undefined,
        business_name: draft.businessName.trim() || draft.workspaceName.trim(),
        business_model: resolvedBusinessModel,
        offering_kind: draft.offeringKind || undefined,
        offering_type:
          draft.offeringType.trim() || draft.offeringKind || undefined,
        offering_name: draft.offeringName.trim(),
        offering_description: draft.offeringDescription.trim(),
        product_category: draft.productCategory.trim() || undefined,
        price: !pricingKnownForPayload
          ? undefined
          : draft.offeringKind === 'service'
            ? undefined
            : draft.price.trim() || undefined,
        starting_rate: !pricingKnownForPayload
          ? undefined
          : draft.offeringKind === 'service'
            ? draft.startingRate.trim() || undefined
            : undefined,
        pricing_model: pricingKnownForPayload
          ? resolvedPricingModel || undefined
          : undefined,
        competitor_urls: urls,
        context_dev_summary: extraction
          ? {
              provider: extraction.provider,
              domain: extraction.domain,
              fields: extraction.fields,
              requests: extraction.requests,
              raw_artifact_id: extraction.raw_artifact_id,
            }
          : undefined,
        extraction_review: extraction
          ? {
              confirmed_fields: extraction.fields,
              raw_artifact_id: extraction.raw_artifact_id,
            }
          : undefined,
        metadata: {
          source: 'marketing_agent_onboarding_wizard',
          pricing_status: pricingKnownForPayload
            ? 'provided_or_partial'
            : 'later',
        },
      };
      const response = await startSetup.mutateAsync({
        clientId: ensuredClientId,
        payload,
      });
      if (!response.product_id) {
        toast.error('Workspace setup started but no product ID was returned.');
        return;
      }
      const completed = {
        clientId: ensuredClientId,
        clientName: draft.workspaceName.trim(),
        productId: response.product_id,
        productName: response.product_name || draft.offeringName.trim(),
        workflowRunId: response.workflow_run_id,
        temporalWorkflowId: response.temporal_workflow_id,
      };
      selectWorkspace(completed.clientId, { name: completed.clientName });
      selectProduct(
        completed.productId,
        { title: completed.productName, client_id: completed.clientId },
        { clientId: completed.clientId },
      );
      setCompletedSetup(completed);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Workspace setup failed.',
      );
    }
  };

  const renderWorkspaceEditFields = () => (
    <div className="grid gap-4 md:grid-cols-2">
      <FieldRoot name="business_name" className="md:col-span-2">
        <FieldLabel>Business name</FieldLabel>
        <Input
          aria-label="Business name"
          value={draft.businessName}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              businessName: event.target.value,
            }))
          }
          placeholder={draft.workspaceName || 'Business name'}
          disabled={isSubmitting}
        />
      </FieldRoot>
      <FieldRoot name="business_model" className="md:col-span-2">
        <FieldLabel>Business model</FieldLabel>
        <Select
          aria-label="Business model"
          value={draft.businessModel}
          onValueChange={(value) =>
            setDraft((current) => ({
              ...current,
              businessModel: value,
              customBusinessModel:
                value === 'other' ? current.customBusinessModel : '',
            }))
          }
          options={businessModelOptions}
          disabled={isSubmitting}
        />
      </FieldRoot>
      {draft.businessModel === 'other' ? (
        <FieldRoot name="custom_business_model" className="md:col-span-2">
          <FieldLabel>Describe how this business makes money</FieldLabel>
          <Input
            aria-label="Custom business model"
            value={draft.customBusinessModel}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                customBusinessModel: event.target.value,
              }))
            }
            placeholder="Example: paid community for independent consultants"
            disabled={isSubmitting}
          />
        </FieldRoot>
      ) : null}
    </div>
  );

  const renderOfferEditFields = () => {
    const copy = offeringCopy(draft.offeringKind);
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <FieldRoot name="offering_kind">
          <FieldLabel>Offering kind</FieldLabel>
          <Select
            aria-label="Offering kind"
            value={draft.offeringKind}
            onValueChange={(value) =>
              setDraft((current) => ({
                ...current,
                offeringKind: value as OfferingKind | '',
                customOfferingKind:
                  value === 'other' ? current.customOfferingKind : '',
                offeringType:
                  value === 'other'
                    ? current.customOfferingKind
                    : current.offeringType || value,
              }))
            }
            options={[
              { label: 'Select offering kind', value: '' },
              ...offeringKindOptions.map((option) => ({
                label: option.title,
                value: option.id,
              })),
            ]}
            disabled={isSubmitting}
          />
        </FieldRoot>
        {draft.offeringKind === 'other' ? (
          <FieldRoot name="custom_offering_kind">
            <FieldLabel>Describe the offer type</FieldLabel>
            <Input
              aria-label="Custom offering kind"
              value={draft.customOfferingKind}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  customOfferingKind: event.target.value,
                  offeringType: event.target.value,
                }))
              }
              placeholder="Example: paid community"
              disabled={isSubmitting}
            />
          </FieldRoot>
        ) : null}
        <FieldRoot name="offering_name">
          <FieldLabel>{copy.nameLabel}</FieldLabel>
          <Input
            aria-label="Offer name"
            value={draft.offeringName}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                offeringName: event.target.value,
              }))
            }
            disabled={isSubmitting}
          />
        </FieldRoot>
        <FieldRoot name="offering_type">
          <FieldLabel>Offering type</FieldLabel>
          <Input
            aria-label="Offer type"
            value={draft.offeringType}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                offeringType: event.target.value,
              }))
            }
            disabled={isSubmitting}
          />
        </FieldRoot>
        <FieldRoot name="product_category">
          <FieldLabel>Category</FieldLabel>
          <Input
            aria-label="Category"
            value={draft.productCategory}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                productCategory: event.target.value,
              }))
            }
            disabled={isSubmitting}
          />
        </FieldRoot>
        <FieldRoot name="offering_description" className="md:col-span-2">
          <FieldLabel>{copy.outcomeLabel}</FieldLabel>
          <Textarea
            aria-label="Offer description"
            rows={4}
            value={draft.offeringDescription}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                offeringDescription: event.target.value,
              }))
            }
            disabled={isSubmitting}
          />
        </FieldRoot>
      </div>
    );
  };

  const renderPricingEditFields = () => {
    const copy = offeringCopy(draft.offeringKind);
    const pricingModelOptions = draft.offeringKind
      ? pricingModelOptionsByKind[draft.offeringKind]
      : pricingModelOptionsByKind.other;
    const pricingOptions =
      pricingModelOptions.some(
        (option) => option.value === draft.pricingModel,
      ) || !draft.pricingModel
        ? pricingModelOptions
        : [
            {
              label: pricingModelLabel(draft.offeringKind, draft.pricingModel),
              value: draft.pricingModel,
            },
            ...pricingModelOptions,
          ];
    return (
      <div className="grid gap-4">
        <FieldRoot name="pricing_model">
          <FieldLabel>{copy.modelLabel}</FieldLabel>
          <Select
            aria-label="Pricing model"
            value={draft.pricingModel}
            onValueChange={(value) =>
              setDraft((current) => ({
                ...current,
                pricingModel: value,
                customPricingModel:
                  value === 'other' ? current.customPricingModel : '',
                pricingIntent: 'known',
              }))
            }
            options={[{ label: 'Select model', value: '' }, ...pricingOptions]}
            disabled={isSubmitting}
          />
        </FieldRoot>
        {draft.pricingModel === 'other' ? (
          <FieldRoot name="custom_pricing_model">
            <FieldLabel>Custom charge model</FieldLabel>
            <Input
              aria-label="Custom pricing model"
              value={draft.customPricingModel}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  customPricingModel: event.target.value,
                  pricingIntent: 'known',
                }))
              }
              placeholder="Example: monthly minimum, per deliverable, hybrid"
              disabled={isSubmitting}
            />
          </FieldRoot>
        ) : null}
        <FieldRoot name="price">
          <FieldLabel>{copy.pricingLabel}</FieldLabel>
          <Input
            aria-label="Price"
            value={
              draft.offeringKind === 'service'
                ? draft.startingRate
                : draft.price
            }
            onChange={(event) =>
              setDraft((current) =>
                current.offeringKind === 'service'
                  ? {
                      ...current,
                      startingRate: event.target.value,
                      pricingIntent: 'known',
                    }
                  : {
                      ...current,
                      price: event.target.value,
                      pricingIntent: 'known',
                    },
              )
            }
            placeholder="Optional"
            disabled={isSubmitting}
          />
        </FieldRoot>
      </div>
    );
  };

  const renderCompetitorEditFields = () => (
    <FieldRoot name="competitor_urls">
      <FieldLabel>Competitor websites</FieldLabel>
      <FieldDescription>One per line</FieldDescription>
      <Textarea
        aria-label="Competitor websites"
        rows={4}
        value={draft.competitorUrls}
        onChange={(event) =>
          setDraft((current) => ({
            ...current,
            competitorUrls: event.target.value,
          }))
        }
        placeholder="https://competitor.com"
        disabled={isSubmitting}
      />
    </FieldRoot>
  );

  const renderReviewFields = (mode: ReviewEditMode = 'all') => (
    <div className="space-y-5">
      {mode === 'workspace' || mode === 'all'
        ? renderWorkspaceEditFields()
        : null}
      {mode === 'offer' || mode === 'all' ? renderOfferEditFields() : null}
      {mode === 'pricing' || mode === 'all' ? renderPricingEditFields() : null}
      {mode === 'competitors' || mode === 'all'
        ? renderCompetitorEditFields()
        : null}
    </div>
  );

  const renderReviewDisplay = () => {
    const copy = offeringCopy(draft.offeringKind);
    const competitorUrls = parseUrls(draft.competitorUrls);
    const businessName =
      draft.businessName.trim() || draft.workspaceName.trim();

    return (
      <div className="space-y-5">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{reviewItems.length} changes ready</Badge>
            {reviewAttentionItems.length ? (
              <Badge
                tone={
                  reviewAttentionItems.some((item) => item.tone === 'danger')
                    ? 'danger'
                    : 'warning'
                }
              >
                {reviewAttentionItems.length} item
                {reviewAttentionItems.length === 1 ? '' : 's'} to review
              </Badge>
            ) : (
              <Badge tone="success">Ready to create</Badge>
            )}
          </div>
          {isPage && isMobileViewport ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="w-full justify-center sm:hidden"
              onClick={() => setReviewEditMode('all')}
              disabled={isSubmitting}
            >
              <Edit3 className="h-4 w-4" />
              Edit all details
            </Button>
          ) : null}
        </div>
        {reviewAttentionItems.length ? (
          <section className="space-y-3" aria-label="Review attention">
            <h2 className="text-sm font-semibold text-content">
              {reviewAttentionItems.some((item) => item.tone === 'danger')
                ? 'Needs attention'
                : 'Optional gap'}
            </h2>
            <div className="divide-y divide-border rounded-md border border-border bg-surface">
              {reviewAttentionItems.map((item) => (
                <div key={item.id} className="flex items-start gap-3 px-4 py-3">
                  <AlertTriangle
                    className={
                      item.tone === 'danger'
                        ? 'mt-0.5 h-4 w-4 shrink-0 text-danger'
                        : 'mt-0.5 h-4 w-4 shrink-0 text-warning'
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-content">
                        {item.label}
                      </span>
                      <Badge tone={item.tone}>
                        {item.tone === 'danger' ? 'Required' : 'Optional'}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm leading-5 text-content-muted">
                      {item.detail}
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="xs"
                    variant="secondary"
                    onClick={() => setReviewEditMode(item.editMode)}
                  >
                    {item.action}
                  </Button>
                </div>
              ))}
            </div>
          </section>
        ) : null}
        <ReviewChangesPanel title="Workspace changes" items={reviewItems} />
        <ReviewSection
          title="Workspace"
          onEdit={() => setReviewEditMode('workspace')}
        >
          <ReviewFactRow
            label="Business name"
            value={displayValue(businessName)}
            muted={!businessName}
          />
          <ReviewFactRow
            label="Stage"
            value={stageLabel(draft.businessType)}
            muted={!draft.businessType}
          />
          <ReviewFactRow
            label="Business model"
            value={displayBusinessModel(
              draft.businessModel,
              draft.customBusinessModel,
            )}
            muted={!resolvedBusinessModel}
          />
          {draft.businessType === 'existing' ? (
            <ReviewFactRow
              label="Website"
              value={displayValue(draft.businessUrl)}
              muted={!draft.businessUrl.trim()}
            />
          ) : null}
        </ReviewSection>
        <ReviewSection title="Offer" onEdit={() => setReviewEditMode('offer')}>
          <ReviewFactRow
            label="Offering kind"
            value={displayOfferingKind(
              draft.offeringKind,
              draft.customOfferingKind,
            )}
            muted={!draft.offeringKind}
          />
          <ReviewFactRow
            label={copy.nameLabel}
            value={displayValue(draft.offeringName)}
            muted={!draft.offeringName.trim()}
          />
          <ReviewFactRow
            label="Offering type"
            value={displayValue(draft.offeringType)}
            muted={!draft.offeringType.trim()}
          />
          <ReviewFactRow
            label="Category"
            value={displayValue(draft.productCategory, 'Not provided')}
            muted={!draft.productCategory.trim()}
          />
          <ReviewFactRow
            label={copy.outcomeLabel}
            value={displayValue(draft.offeringDescription)}
            muted={!draft.offeringDescription.trim()}
            clamp
          />
        </ReviewSection>
        <ReviewSection
          title="Pricing"
          onEdit={() => setReviewEditMode('pricing')}
        >
          <ReviewFactRow
            label={copy.modelLabel}
            value={displayValue(
              pricingModelText || draft.pricingModel,
              'Set later',
            )}
            muted={!draft.pricingModel.trim()}
          />
          <ReviewFactRow
            label={copy.pricingLabel}
            value={displayValue(pricingText, 'Set later')}
            muted={!pricingText.trim()}
          />
        </ReviewSection>
        <ReviewSection
          title="Competitors"
          onEdit={() => setReviewEditMode('competitors')}
        >
          <ReviewFactRow
            label="Websites"
            value={
              competitorUrls.length ? (
                <span className="flex flex-col gap-1">
                  {competitorUrls.map((url) => (
                    <span key={url}>{url}</span>
                  ))}
                </span>
              ) : (
                'Not provided'
              )
            }
            muted={!competitorUrls.length}
          />
        </ReviewSection>
      </div>
    );
  };

  const renderReviewEditView = (mode: ReviewEditMode) => {
    const titleByMode: Record<ReviewEditMode, string> = {
      workspace: 'Edit workspace',
      offer: 'Edit offer',
      pricing: 'Edit pricing',
      competitors: 'Edit competitors',
      all: 'Edit all details',
    };

    return (
      <div className="space-y-5">
        <div className="rounded-md border border-border bg-surface px-4 py-3">
          <h2 className="text-sm font-semibold text-content">
            {titleByMode[mode]}
          </h2>
          <p className="mt-1 text-sm text-content-muted">
            Update the fields, then return to review before creating the
            workspace.
          </p>
        </div>
        {renderReviewFields(mode)}
      </div>
    );
  };

  const stepBody = (() => {
    if (step === 'workspace') {
      return (
        <FieldRoot name="workspace_name">
          <FieldLabel>Workspace name</FieldLabel>
          <Input
            aria-label="Workspace name"
            value={draft.workspaceName}
            onChange={(event) => {
              setDraft((current) => ({
                ...current,
                workspaceName: event.target.value,
              }));
              if (fieldErrors.workspaceName)
                setFieldErrors((prev) => ({ ...prev, workspaceName: '' }));
            }}
            disabled={Boolean(clientId) || isSubmitting}
          />
          {fieldErrors.workspaceName ? (
            <p className="mt-1 text-xs text-danger">
              {fieldErrors.workspaceName}
            </p>
          ) : (
            <FieldError />
          )}
        </FieldRoot>
      );
    }
    if (step === 'business-type') {
      return (
        <ChoiceList
          aria-label="Business stage"
          iconStyle="color"
          items={[
            {
              id: 'new',
              title: 'New business',
              description:
                'Start from scratch with what you sell or plan to sell.',
              selected: draft.businessType === 'new',
              icon: <OnboardingIcon name="business-new" />,
            },
            {
              id: 'existing',
              title: 'Already live business',
              description:
                'Use your website so your agent can learn the business.',
              selected: draft.businessType === 'existing',
              icon: <OnboardingIcon name="business-existing" />,
            },
          ]}
          onSelect={(id) => {
            const businessType = id === 'existing' ? 'existing' : 'new';
            setDraft((current) => ({ ...current, businessType }));
            setExtraction(null);
            setExtractionCacheKey(null);
            setStep(
              businessType === 'existing'
                ? 'existing-url'
                : 'new-business-model',
            );
          }}
        />
      );
    }
    if (step === 'existing-url') {
      return (
        <FieldRoot name="business_url">
          <FieldLabel>Business website URL</FieldLabel>
          <Input
            aria-label="Business website URL"
            value={draft.businessUrl}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                businessUrl: event.target.value,
              }))
            }
            placeholder="https://example.com"
            disabled={isSubmitting}
          />
          <FieldError />
        </FieldRoot>
      );
    }
    if (step === 'existing-competitors' || step === 'new-competitors') {
      return (
        <FieldRoot name="competitor_urls">
          <FieldLabel>Competitor websites</FieldLabel>
          <FieldDescription>One per line</FieldDescription>
          <Textarea
            aria-label="Competitor websites"
            rows={5}
            value={draft.competitorUrls}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                competitorUrls: event.target.value,
              }))
            }
            placeholder="https://competitor.com"
            disabled={isSubmitting}
          />
        </FieldRoot>
      );
    }
    if (step === 'new-business-model') {
      return (
        <div className="space-y-4">
          <ChoiceList
            aria-label="Business model"
            layout="grid"
            iconStyle="color"
            itemClassName="min-h-[104px]"
            items={businessModelChoiceOptions.map((option) => ({
              ...option,
              selected: draft.businessModel === option.id,
            }))}
            onSelect={(id) => {
              const directOffering = directOfferingByBusinessModel[id];
              setDraft((current) => ({
                ...current,
                businessModel: id,
                customBusinessModel:
                  id === 'other' ? current.customBusinessModel : '',
                offeringKind:
                  id === 'other' ? 'other' : directOffering?.kind || '',
                customOfferingKind: '',
                offeringType: id === 'other' ? '' : directOffering?.type || '',
                price: '',
                startingRate: '',
                pricingModel: '',
                customPricingModel: '',
                pricingIntent: '',
              }));
              setFieldErrors((current) => ({
                ...current,
                customBusinessModel: '',
              }));
              if (id === 'other') return;
              setStep(
                id === 'affiliate' ? 'new-offering-kind' : 'new-offering-name',
              );
            }}
          />
          {draft.businessModel === 'other' ? (
            <FieldRoot name="custom_business_model">
              <FieldLabel>Describe how this business makes money</FieldLabel>
              <FieldDescription>One sentence is enough.</FieldDescription>
              <Input
                aria-label="Custom business model"
                value={draft.customBusinessModel}
                onChange={(event) => {
                  setDraft((current) => ({
                    ...current,
                    customBusinessModel: event.target.value,
                    customOfferingKind: event.target.value,
                    offeringType: event.target.value,
                  }));
                  if (fieldErrors.customBusinessModel) {
                    setFieldErrors((current) => ({
                      ...current,
                      customBusinessModel: '',
                    }));
                  }
                }}
                placeholder="Example: paid community for independent consultants"
                disabled={isSubmitting}
              />
              {fieldErrors.customBusinessModel ? (
                <p className="mt-1 text-xs text-danger">
                  {fieldErrors.customBusinessModel}
                </p>
              ) : null}
            </FieldRoot>
          ) : null}
        </div>
      );
    }
    if (step === 'new-offering-kind') {
      return (
        <div className="space-y-4">
          <ChoiceList
            aria-label="What do you sell"
            layout="grid"
            iconStyle="color"
            itemClassName="min-h-[104px]"
            items={offeringKindOptions.map((option) => ({
              id: option.id,
              title: option.title,
              description: option.description,
              selected: draft.offeringKind === option.id,
              icon: <OnboardingIcon name={offeringIconByKind[option.id]} />,
            }))}
            onSelect={(id) => {
              setDraft((current) => ({
                ...current,
                offeringKind: id as OfferingKind,
                customOfferingKind:
                  id === 'other' ? current.customOfferingKind : '',
                offeringType: id === 'other' ? '' : id,
                price: '',
                startingRate: '',
                pricingModel: '',
                customPricingModel: '',
                pricingIntent: '',
              }));
              setFieldErrors((current) => ({
                ...current,
                customOfferingKind: '',
              }));
              if (id === 'other') return;
              setStep('new-offering-name');
            }}
          />
          {draft.offeringKind === 'other' ? (
            <FieldRoot name="custom_offering_kind">
              <FieldLabel>Describe the promoted offer type</FieldLabel>
              <FieldDescription>One sentence is enough.</FieldDescription>
              <Input
                aria-label="Custom offering kind"
                value={draft.customOfferingKind}
                onChange={(event) => {
                  setDraft((current) => ({
                    ...current,
                    customOfferingKind: event.target.value,
                    offeringType: event.target.value,
                  }));
                  if (fieldErrors.customOfferingKind) {
                    setFieldErrors((current) => ({
                      ...current,
                      customOfferingKind: '',
                    }));
                  }
                }}
                placeholder="Example: paid newsletter sponsorship"
                disabled={isSubmitting}
              />
              {fieldErrors.customOfferingKind ? (
                <p className="mt-1 text-xs text-danger">
                  {fieldErrors.customOfferingKind}
                </p>
              ) : null}
            </FieldRoot>
          ) : null}
        </div>
      );
    }
    if (step === 'new-offering-name') {
      const copy = offeringCopy(draft.offeringKind);
      return (
        <FieldRoot name="offering_name">
          <FieldLabel>{copy.nameLabel}</FieldLabel>
          <Input
            aria-label="Offer name"
            value={draft.offeringName}
            onChange={(event) => {
              setDraft((current) => ({
                ...current,
                offeringName: event.target.value,
              }));
              if (fieldErrors.offeringName)
                setFieldErrors((prev) => ({ ...prev, offeringName: '' }));
            }}
            placeholder={copy.namePlaceholder}
            disabled={isSubmitting}
          />
          {fieldErrors.offeringName ? (
            <p className="mt-1 text-xs text-danger">
              {fieldErrors.offeringName}
            </p>
          ) : null}
        </FieldRoot>
      );
    }
    if (step === 'new-offering-description') {
      const copy = offeringCopy(draft.offeringKind);
      return (
        <FieldRoot name="offering_description">
          <FieldLabel>{copy.outcomeLabel}</FieldLabel>
          <Textarea
            aria-label="Offer description"
            rows={5}
            value={draft.offeringDescription}
            onChange={(event) => {
              setDraft((current) => ({
                ...current,
                offeringDescription: event.target.value,
              }));
              if (fieldErrors.offeringDescription)
                setFieldErrors((prev) => ({
                  ...prev,
                  offeringDescription: '',
                }));
            }}
            placeholder={copy.outcomePlaceholder}
            disabled={isSubmitting}
          />
          {fieldErrors.offeringDescription ? (
            <p className="mt-1 text-xs text-danger">
              {fieldErrors.offeringDescription}
            </p>
          ) : null}
        </FieldRoot>
      );
    }
    if (step === 'new-pricing') {
      const copy = offeringCopy(draft.offeringKind);
      const pricingModelOptions = draft.offeringKind
        ? pricingModelOptionsByKind[draft.offeringKind]
        : pricingModelOptionsByKind.other;
      return (
        <div className="space-y-4">
          <ChoiceList
            aria-label="Pricing status"
            layout="grid"
            iconStyle="color"
            items={[
              {
                id: 'known',
                title: 'I know enough to add it now',
                description:
                  'Add a price, rate, or pricing model for your agent.',
                selected: draft.pricingIntent === 'known',
                icon: <OnboardingIcon name="pricing-known" />,
              },
              {
                id: 'later',
                title: 'Set pricing later',
                description: 'Skip price and rate setup for now.',
                selected: draft.pricingIntent === 'later',
                icon: <OnboardingIcon name="pricing-later" />,
              },
            ]}
            onSelect={(id) => {
              setDraft((current) => ({
                ...current,
                pricingIntent: id === 'known' ? 'known' : 'later',
                pricingModel:
                  id === 'known'
                    ? current.pricingModel ||
                      defaultPricingModel(current.offeringKind)
                    : '',
                customPricingModel:
                  id === 'known' ? current.customPricingModel : '',
                price: id === 'known' ? current.price : '',
                startingRate: id === 'known' ? current.startingRate : '',
              }));
              if (id === 'later') setStep('new-competitors');
            }}
          />
          {draft.pricingIntent === 'known' ? (
            <div className="grid gap-4">
              <FieldRoot name="pricing_model">
                <FieldLabel>{copy.modelLabel}</FieldLabel>
                <Select
                  aria-label="Pricing model"
                  value={draft.pricingModel}
                  onValueChange={(value) =>
                    setDraft((current) => ({
                      ...current,
                      pricingModel: value,
                      customPricingModel:
                        value === 'other' ? current.customPricingModel : '',
                    }))
                  }
                  options={[
                    { label: 'Select model', value: '' },
                    ...pricingModelOptions,
                  ]}
                  disabled={isSubmitting}
                />
              </FieldRoot>
              {draft.pricingModel === 'other' ? (
                <FieldRoot name="custom_pricing_model">
                  <FieldLabel>Custom charge model</FieldLabel>
                  <Input
                    aria-label="Custom pricing model"
                    value={draft.customPricingModel}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        customPricingModel: event.target.value,
                      }))
                    }
                    placeholder="Example: monthly minimum, per deliverable, hybrid"
                    disabled={isSubmitting}
                  />
                </FieldRoot>
              ) : null}
              <FieldRoot name="price">
                <FieldLabel>{copy.pricingLabel}</FieldLabel>
                <Input
                  aria-label="Price"
                  value={
                    draft.offeringKind === 'service'
                      ? draft.startingRate
                      : draft.price
                  }
                  onChange={(event) =>
                    setDraft((current) =>
                      current.offeringKind === 'service'
                        ? { ...current, startingRate: event.target.value }
                        : { ...current, price: event.target.value },
                    )
                  }
                  placeholder={copy.pricingPlaceholder}
                  disabled={isSubmitting}
                />
              </FieldRoot>
            </div>
          ) : null}
        </div>
      );
    }
    if (step === 'existing-review' || step === 'new-review') {
      return reviewEditMode
        ? renderReviewEditView(reviewEditMode)
        : renderReviewDisplay();
    }
    return null;
  })();

  const hasPrimaryAction =
    step === 'existing-review' || step === 'new-review'
      ? true
      : !isSelectionOnlyStep;
  const form = (
    <FormRoot
      className={`mos-onboarding-form ${stepLayoutClassName[stepLayoutKind]}${hasPrimaryAction ? '' : ' mos-onboarding-form--no-primary-action'}`}
      onSubmit={(event) => event.preventDefault()}
    >
      <div
        key={`${step}-${reviewEditMode || 'review'}`}
        className="step-enter mos-onboarding-step-frame"
      >
        {stepBody}
      </div>

      <div className="mos-onboarding-actions space-y-3">
        {step === 'existing-review' || step === 'new-review' ? (
          reviewEditMode ? (
            <Button
              type="button"
              className="w-full"
              onClick={() => setReviewEditMode(null)}
              disabled={isSubmitting || !reviewEditIsValid(reviewEditMode)}
            >
              <CheckCircle2 className="h-4 w-4" />
              Done
            </Button>
          ) : (
            <Button
              type="button"
              className="w-full"
              onClick={handleSubmit}
              disabled={isSubmitting || !stepIsValid}
            >
              <CheckCircle2 className="h-4 w-4" />
              Create workspace
            </Button>
          )
        ) : isSelectionOnlyStep ? null : (
          <Button
            type="button"
            className="w-full"
            onClick={goNext}
            disabled={isSubmitting || !stepIsValid}
            aria-busy={isCheckingSite ? 'true' : undefined}
          >
            {isCheckingSite ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Checking site...
              </>
            ) : (
              <>
                Continue
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>
        )}
      </div>
    </FormRoot>
  );

  if (completedSetup) {
    const isFailed = foundationReadiness?.status === 'foundation_failed';
    const setupBadgeTone = isFailed ? 'danger' : 'accent';
    const setupBadgeLabel = isFailed ? 'Setup blocked' : 'Setup running';
    const readinessReason = foundationReadiness?.reason || null;
    const missingStepKeys = foundationReadiness?.missing_step_keys || [];
    const shouldShowSetupLogout = !isPage || showSetupLogout;

    const successShell = (
      <FirstRunShell
        centered
        className="mos-onboarding-success-shell py-6 sm:py-8"
        taskClassName="mos-onboarding-success space-y-5"
        title="Setting up your workspace"
        description="mOS is building foundational docs, market context, and workspace memory. You'll stay here until setup is fully ready."
        actions={
          <div className="flex w-full items-center justify-between gap-3">
            <Badge tone={setupBadgeTone}>{setupBadgeLabel}</Badge>
            {shouldShowSetupLogout ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => signOut({ redirectUrl: '/sign-in' })}
              >
                <LogOut className="h-4 w-4" />
                Log out
              </Button>
            ) : null}
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-3 rounded-lg border border-border bg-surface p-3 shadow-xs sm:grid-cols-2 lg:grid-cols-4">
            <div className="min-w-0">
              <div className="text-xs font-medium text-content-muted">
                Workspace
              </div>
              <div className="mt-1 truncate text-sm font-semibold text-content">
                {completedSetup.clientName || 'Workspace created'}
              </div>
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-content-muted">
                Offering
              </div>
              <div className="mt-1 truncate text-sm font-semibold text-content">
                {completedSetup.productName || 'Offering shell created'}
              </div>
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-content-muted">
                Estimated time
              </div>
              <div className="mt-1 truncate text-sm font-semibold text-content">
                20-30 minutes
              </div>
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-content-muted">
                Notification
              </div>
              <div className="mt-1 truncate text-sm font-semibold text-content">
                Email when ready
              </div>
            </div>
          </div>
          {isFailed ? (
            <div className="rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm leading-6 text-danger">
              Foundational setup did not complete cleanly. Reason:{' '}
              {readinessReason || 'unknown_error'}.
              {missingStepKeys.length
                ? ` Missing docs: ${missingStepKeys.join(', ')}.`
                : ''}
            </div>
          ) : null}
          <SetupChecklist
            title="Setup progress"
            items={[
              {
                id: 'workspace-created',
                label: 'Workspace created',
                status: 'done',
                icon: <OnboardingIcon name="setup-workspace" />,
              },
              {
                id: 'offering-created',
                label: 'Offering shell created',
                status: 'done',
                icon: <OnboardingIcon name="setup-offer" />,
              },
              {
                id: 'market',
                label: 'mOS agent researching the market',
                status: isFailed ? 'pending' : 'running',
                icon: <OnboardingIcon name="setup-market" />,
              },
              {
                id: 'docs',
                label: 'mOS agent building foundational docs',
                status: isFailed ? 'pending' : 'running',
                icon: <OnboardingIcon name="setup-docs" />,
              },
              {
                id: 'memory',
                label: 'mOS agent packaging workspace memory',
                status: 'pending',
                icon: <OnboardingIcon name="setup-memory" />,
              },
            ]}
          />
        </div>
      </FirstRunShell>
    );

    if (isPage) {
      return (
        <div className="mos-onboarding-page-shell">
          <div className="mos-onboarding-topbar mos-onboarding-topbar--success">
            <div className="mos-onboarding-topbar-start">
              {pageHeaderAction}
            </div>
            <div
              aria-hidden="true"
              className="mos-onboarding-topbar-progress"
            />
            <div className="mos-onboarding-topbar-end">
              {pageHeaderEndAction}
            </div>
          </div>
          {successShell}
        </div>
      );
    }

    return (
      <DialogRoot open={open} onOpenChange={setOpen}>
        <DialogTrigger className={buttonClasses({ size: 'sm' })}>
          {triggerLabel}
        </DialogTrigger>
        <DialogContent className="max-h-[92svh] w-[min(1120px,calc(100vw-2rem))] overflow-y-auto">
          <div className="sr-only">
            <DialogTitle>Setting up your workspace</DialogTitle>
            <DialogDescription>
              mOS is building foundational docs, market context, and workspace
              memory. This usually takes 20-30 minutes.
            </DialogDescription>
          </div>
          <DialogClose className="absolute right-4 top-4 rounded-md px-2 py-1 text-sm text-content-muted hover:text-content">
            Close
          </DialogClose>
          {successShell}
        </DialogContent>
      </DialogRoot>
    );
  }

  const progressRail = (
    <OnboardingProgressRail
      value={progressValue}
      label="Setup progress"
      showCount={false}
      showLabel={false}
    />
  );
  const taskClassName = 'mos-onboarding-task space-y-7';
  const isReviewStep = step === 'existing-review' || step === 'new-review';
  const firstStepBadge =
    stepIndex === 0 && !reviewEditMode ? (
      <Badge tone="neutral" className="mos-onboarding-duration-badge">
        2-minute setup
      </Badge>
    ) : null;
  const backAction =
    (stepIndex > 0 || reviewEditMode) && (!isPage || !isMobileViewport) ? (
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className={`mos-onboarding-back px-4 text-content-muted hover:text-content hover:scale-100 hover:shadow-none active:scale-100 active:shadow-none sm:-ml-3 sm:px-3${isPage ? ' hidden sm:inline-flex' : ''}`}
        onClick={(event) => {
          event.currentTarget.blur();
          if (reviewEditMode) {
            setReviewEditMode(null);
            return;
          }
          goBack();
        }}
        disabled={isSubmitting}
      >
        <ArrowLeft className="h-4 w-4" />
        {reviewEditMode ? 'Back to review' : 'Previous'}
      </Button>
    ) : null;
  const mobileHeaderBackAction =
    isPage && isMobileViewport && (stepIndex > 0 || reviewEditMode) ? (
      <button
        type="button"
        className="mos-onboarding-mobile-header-back inline-flex h-9 items-center gap-1.5 px-1 text-sm font-medium text-content-muted transition hover:text-content sm:hidden"
        onClick={(event) => {
          event.currentTarget.blur();
          if (reviewEditMode) {
            setReviewEditMode(null);
            return;
          }
          goBack();
        }}
        disabled={isSubmitting}
      >
        <ArrowLeft className="h-4 w-4" />
        Previous
      </button>
    ) : null;
  const editAllAction =
    isReviewStep && !reviewEditMode && (!isPage || !isMobileViewport) ? (
      <Button
        type="button"
        size="sm"
        variant="secondary"
        className={
          isPage
            ? 'mos-onboarding-edit-all hidden sm:inline-flex'
            : 'mos-onboarding-edit-all'
        }
        onClick={() => setReviewEditMode('all')}
        disabled={isSubmitting}
      >
        <Edit3 className="h-4 w-4" />
        Edit all details
      </Button>
    ) : null;
  const headerActions =
    firstStepBadge || backAction || editAllAction ? (
      <div className="mos-onboarding-header-actions-row">
        <div className="min-w-0">{firstStepBadge || backAction}</div>
        {editAllAction}
      </div>
    ) : null;

  const shell = (
    <FirstRunShell
      centered
      className={
        isPage
          ? 'mos-onboarding-shell mos-onboarding-shell--page !items-center !justify-start !pt-4 sm:!pt-5'
          : 'mos-onboarding-shell'
      }
      taskClassName={taskClassName}
      title={stepTitle(step, draft)}
      description={stepDescription(step)}
      actions={headerActions}
      progressRail={isPage ? undefined : progressRail}
    >
      {form}
    </FirstRunShell>
  );

  if (isPage) {
    return (
      <div className="mos-onboarding-page-shell">
        <div className="mos-onboarding-topbar">
          <div className="mos-onboarding-topbar-start">
            {mobileHeaderBackAction}
            {pageHeaderAction}
          </div>
          <div className="mos-onboarding-topbar-progress">{progressRail}</div>
          <div className="mos-onboarding-topbar-end">{pageHeaderEndAction}</div>
        </div>
        {shell}
      </div>
    );
  }

  return (
    <DialogRoot open={open} onOpenChange={setOpen}>
      <DialogTrigger className={buttonClasses({ size: 'sm' })}>
        {triggerLabel}
      </DialogTrigger>
      <DialogContent className="max-h-[92svh] w-[min(1120px,calc(100vw-2rem))] overflow-y-auto">
        <div className="sr-only">
          <DialogTitle>Set up your marketing agent</DialogTitle>
          <DialogDescription>
            Add source details and create the workspace.
          </DialogDescription>
        </div>
        <DialogClose className="absolute right-4 top-4 rounded-md px-2 py-1 text-sm text-content-muted hover:text-content">
          Close
        </DialogClose>
        {shell}
      </DialogContent>
    </DialogRoot>
  );
}

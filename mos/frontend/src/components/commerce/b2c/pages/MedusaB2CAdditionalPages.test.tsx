import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { runtimeState } = vi.hoisted(() => ({
  runtimeState: { value: null as Record<string, unknown> | null },
}));
const { themeState } = vi.hoisted(() => ({
  themeState: {
    value: {
      tokens: {},
      isThemed: false,
      ctaStyle: undefined as Record<string, string> | undefined,
    },
  },
}));

vi.mock('@/funnels/puckConfig', () => ({
  useFunnelRuntime: () => ({
    productSlug: 'b8f94ba2',
    funnelSlug: 'honest-herbalist',
  }),
}));

vi.mock('../B2CRuntimeProvider', () => ({
  useB2CRuntime: () => runtimeState.value,
}));

vi.mock('../useB2CTheme', () => ({
  resolveB2CActionRadius: (tokens: { radiusMedium?: string; radiusLarge?: string }) =>
    tokens.radiusMedium || tokens.radiusLarge || '8px',
  resolveB2CBodyFont: (tokens: { fontBody?: string }) =>
    tokens.fontBody ||
    'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  resolveB2CHeadingFont: (tokens: {
    fontHeading?: string;
    fontBody?: string;
  }) =>
    tokens.fontHeading ||
    tokens.fontBody ||
    'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  resolveB2CPillRadius: (tokens: {
    radiusFull?: string;
    radiusMedium?: string;
    radiusLarge?: string;
  }) => tokens.radiusFull || tokens.radiusMedium || tokens.radiusLarge || '8px',
  resolveB2CSurfaceRadius: (tokens: { radiusLarge?: string; radiusMedium?: string }) =>
    tokens.radiusLarge || tokens.radiusMedium || '12px',
  useB2CTheme: () => ({
    tokens: themeState.value.tokens,
    isThemed: themeState.value.isThemed,
  }),
  useB2CCTATheme: () => ({
    style: themeState.value.ctaStyle,
    hoverStyle: undefined,
    isThemed: themeState.value.isThemed,
  }),
}));

import {
  MedusaB2CAccountOrderDetailPage,
  MedusaB2CCheckoutPage,
} from './MedusaB2CAdditionalPages';

function buildRuntime(overrides: Record<string, unknown> = {}) {
  return {
    siteName: 'Honest Herbalist',
    categories: [],
    collections: [],
    cart: { items: [] },
    customer: null,
    customerLoading: false,
    customerError: null,
    isAuthenticated: false,
    login: vi.fn(),
    register: vi.fn(),
    refreshCustomer: vi.fn(),
    updateCustomer: vi.fn(),
    addCustomerAddress: vi.fn(),
    updateCustomerAddress: vi.fn(),
    deleteCustomerAddress: vi.fn(),
    listOrders: vi.fn(),
    getOrder: vi.fn(),
    requestOrderTransfer: vi.fn(),
    cartLoading: false,
    regions: [],
    getShippingOptions: vi.fn().mockResolvedValue([]),
    getPaymentProviders: vi.fn().mockResolvedValue([]),
    performCheckoutAction: vi.fn(),
    completeCheckout: vi.fn(),
    applyPromotionCode: vi.fn(),
    removePromotionCode: vi.fn(),
    updateCartBillingAddress: vi.fn(),
    navigateToOrderConfirmed: vi.fn(),
    logout: vi.fn(),
    navigateToHome: vi.fn(),
    navigateToStore: vi.fn(),
    navigateToCollection: vi.fn(),
    navigateToCategory: vi.fn(),
    navigateToCart: vi.fn(),
    navigateToAccount: vi.fn(),
    navigateToAccountProfile: vi.fn(),
    navigateToAccountAddresses: vi.fn(),
    navigateToAccountOrders: vi.fn(),
    navigateToOrder: vi.fn(),
    ...overrides,
  };
}

describe('MedusaB2CAdditionalPages account gating', () => {
  afterEach(() => {
    cleanup();
    runtimeState.value = null;
    themeState.value = {
      tokens: {},
      isThemed: false,
      ctaStyle: undefined,
    };
    vi.clearAllMocks();
  });

  it('shows an explicit account error when the customer API fails', () => {
    runtimeState.value = buildRuntime({
      customerError: 'Failed to load customer account.',
    });

    render(
      <MemoryRouter
        initialEntries={[
          '/workspaces/sites/b8f94ba2-761a-491c-b7b4-05247032b8e6/preview/us/account/orders/details/order_123',
        ]}
      >
        <MedusaB2CAccountOrderDetailPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: 'Account unavailable' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Failed to load customer account.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Sign in' }),
    ).not.toBeInTheDocument();
  });

  it('keeps the auth shell for true unauthenticated access', () => {
    runtimeState.value = buildRuntime();

    render(
      <MemoryRouter
        initialEntries={[
          '/workspaces/sites/b8f94ba2-761a-491c-b7b4-05247032b8e6/preview/us/account/orders/details/order_123',
        ]}
      >
        <MedusaB2CAccountOrderDetailPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: 'Account' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Account unavailable' }),
    ).not.toBeInTheDocument();
  });

  it('applies the site theme to the auth shell when no customer session exists', () => {
    runtimeState.value = buildRuntime();
    themeState.value = {
      isThemed: true,
      tokens: {
        colorText: 'rgb(17, 24, 39)',
        colorTextMuted: 'rgb(75, 85, 99)',
        colorPrimary: 'rgb(21, 94, 117)',
        colorPrimaryText: 'rgb(255, 255, 255)',
        colorBorder: 'rgb(165, 243, 252)',
        fontHeading: 'Fraunces',
        radiusMedium: '16px',
        radiusLarge: '24px',
      },
      ctaStyle: {
        backgroundColor: 'rgb(21, 94, 117)',
        color: 'rgb(255, 255, 255)',
        borderColor: 'rgb(21, 94, 117)',
      },
    };

    render(
      <MemoryRouter
        initialEntries={[
          '/workspaces/sites/b8f94ba2-761a-491c-b7b4-05247032b8e6/preview/us/account/orders/details/order_123',
        ]}
      >
        <MedusaB2CAccountOrderDetailPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Welcome back' })).toHaveStyle({
      fontFamily: 'Fraunces',
      color: 'rgb(17, 24, 39)',
    });
    expect(screen.getByRole('button', { name: 'Sign in' })).toHaveStyle({
      backgroundColor: 'rgb(21, 94, 117)',
      color: 'rgb(255, 255, 255)',
    });
  });

  it('uses explicit standalone typography for checkout headings instead of the app display font', async () => {
    runtimeState.value = buildRuntime({
      cart: {
        id: 'cart_123',
        region_id: 'reg_123',
        currency_code: 'usd',
        subtotal: 1299,
        shipping_total: 0,
        tax_total: 0,
        discount_total: 0,
        email: 'hello@example.com',
        shipping_methods: [],
        items: [
          {
            id: 'item_123',
            title: 'Tincture',
            quantity: 1,
            unit_price: 1299,
            total: 1299,
            thumbnail: null,
            variant: { title: 'Default' },
          },
        ],
      },
    });

    await act(async () => {
      render(<MedusaB2CCheckoutPage />);
    });

    expect(screen.getByRole('heading', { name: 'Contact' })).toHaveStyle({
      fontFamily:
        'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    });
  });

  it('keeps the checkout rails constrained instead of stretching the form and summary across the full pane', async () => {
    runtimeState.value = buildRuntime({
      cart: {
        id: 'cart_123',
        region_id: 'reg_123',
        currency_code: 'usd',
        subtotal: 1299,
        shipping_total: 0,
        tax_total: 0,
        discount_total: 0,
        email: 'hello@example.com',
        shipping_methods: [],
        items: [
          {
            id: 'item_123',
            title: 'Tincture',
            quantity: 1,
            unit_price: 1299,
            total: 1299,
            thumbnail: null,
            variant: { title: 'Default' },
          },
        ],
      },
    });

    let container!: HTMLElement;
    await act(async () => {
      const rendered = render(<MedusaB2CCheckoutPage />);
      container = rendered.container;
    });

    const page = screen.getByTestId('b2c-checkout-page');
    const header = container.querySelector(
      '[data-testid="b2c-checkout-page"] header',
    );
    const headerFrame = screen.getByTestId('b2c-checkout-header-frame');
    const main = container.querySelector(
      '[data-testid="b2c-checkout-page"] main',
    );
    const headerShell = screen.getByTestId('b2c-checkout-header-shell');
    const mainShell = screen.getByTestId('b2c-checkout-main-shell');
    const formRail = screen.getByTestId('b2c-checkout-form-rail');
    const summaryRail = screen.getByTestId('b2c-checkout-summary');

    expect(page).toBeInTheDocument();
    expect(header).toHaveClass('w-full');
    expect(headerFrame).toHaveClass(
      'lg:grid-cols-[minmax(0,1fr)_minmax(0,56rem)_minmax(0,1fr)]',
    );
    expect(main).toHaveClass(
      'lg:grid-cols-[minmax(0,1fr)_minmax(0,56rem)_minmax(0,1fr)]',
    );
    expect(headerShell).toHaveClass(
      'lg:grid-cols-[minmax(0,54%)_minmax(0,46%)]',
    );
    expect(mainShell).toHaveClass('lg:grid-cols-[minmax(0,54%)_minmax(0,46%)]');
    expect(formRail).toHaveClass('lg:max-w-[27.5rem]');
    expect(formRail).toHaveClass('lg:mr-8');
    expect(summaryRail).toHaveClass('lg:max-w-[22rem]');
  });
});

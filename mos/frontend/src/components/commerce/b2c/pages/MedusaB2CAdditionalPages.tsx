import { useEffect, useMemo, useState, useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { buildPublicFunnelPath, parseSitePath } from "@/funnels/runtimeRouting";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import type {
  MedusaCartAddress,
  MedusaCustomerAddress,
  MedusaOrder,
  MedusaPaymentCollection,
  MedusaPaymentProvider,
  MedusaShippingOption,
} from "@/types/commerce";

function PageShell({ title, description, children }: { title: string; description?: string; children?: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white">
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
        <header className="space-y-2 border-b border-zinc-200 pb-4">
          <h1 className="text-3xl font-medium text-zinc-950">{title}</h1>
          {description ? <p className="max-w-2xl text-sm text-zinc-600">{description}</p> : null}
        </header>
        {children}
      </main>
    </div>
  );
}

function formatPrice(amount?: number, currencyCode: string = "usd") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode.toUpperCase(),
  }).format((amount || 0) / 100);
}

function formatDate(dateString?: string): string {
  if (!dateString) return "—";
  return new Date(dateString).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function useResolvedSitePath() {
  const location = useLocation();
  const runtime = useFunnelRuntime();
  return useMemo(() => {
    const hostedPrefix = `/f/${runtime?.productSlug || ""}/${runtime?.funnelSlug || ""}/`;
    const bundlePrefix = `/${runtime?.productSlug || ""}/${runtime?.funnelSlug || ""}/`;
    const stripped = location.pathname.startsWith(hostedPrefix)
      ? location.pathname.slice(hostedPrefix.length)
      : location.pathname.startsWith(bundlePrefix)
        ? location.pathname.slice(bundlePrefix.length)
        : "";
    return parseSitePath(stripped);
  }, [location.pathname, runtime?.funnelSlug, runtime?.productSlug]);
}

// =============================================================================
// Login/Register Shell
// =============================================================================

type AuthView = "login" | "register";

function LoginForm({ onSwitch }: { onSwitch: () => void }) {
  const { login, refreshCustomer, navigateToAccount } = useB2CRuntime();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      await refreshCustomer();
      navigateToAccount();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }, [email, password, login, refreshCustomer, navigateToAccount]);

  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-2 text-center">
        <h2 className="text-2xl font-semibold text-zinc-950">Welcome back</h2>
        <p className="text-sm text-zinc-600">Sign in to access your account and orders.</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-zinc-700">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
      <p className="text-center text-sm text-zinc-600">
        Not a member?{" "}
        <button onClick={onSwitch} className="font-medium text-zinc-950 underline">
          Join us
        </button>
      </p>
    </div>
  );
}

function RegisterForm({ onSwitch }: { onSwitch: () => void }) {
  const { register, login, refreshCustomer, navigateToAccount } = useB2CRuntime();
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(form.email, form.password, form.firstName, form.lastName, form.phone);
      // Auto-login after registration
      await login(form.email, form.password);
      await refreshCustomer();
      navigateToAccount();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }, [form, register, login, refreshCustomer, navigateToAccount]);

  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-2 text-center">
        <h2 className="text-2xl font-semibold text-zinc-950">Create an account</h2>
        <p className="text-sm text-zinc-600">Join us for an enhanced shopping experience.</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700">First name</label>
            <input
              type="text"
              value={form.firstName}
              onChange={(e) => setForm(f => ({ ...f, firstName: e.target.value }))}
              required
              className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700">Last name</label>
            <input
              type="text"
              value={form.lastName}
              onChange={(e) => setForm(f => ({ ...f, lastName: e.target.value }))}
              required
              className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Email</label>
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Phone</label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => setForm(f => ({ ...f, phone: e.target.value }))}
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Password</label>
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
        >
          {loading ? "Creating account..." : "Create account"}
        </button>
      </form>
      <p className="text-center text-sm text-zinc-600">
        Already a member?{" "}
        <button onClick={onSwitch} className="font-medium text-zinc-950 underline">
          Sign in
        </button>
      </p>
    </div>
  );
}

function AuthShell() {
  const [view, setView] = useState<AuthView>("login");
  return (
    <PageShell title="Account" description="Sign in or create an account to access your orders and profile.">
      <div className="flex justify-center py-8">
        {view === "login" ? (
          <LoginForm onSwitch={() => setView("register")} />
        ) : (
          <RegisterForm onSwitch={() => setView("login")} />
        )}
      </div>
    </PageShell>
  );
}

// =============================================================================
// Account Navigation
// =============================================================================

function AccountNav({ active }: { active: "dashboard" | "profile" | "addresses" | "orders" }) {
  const {
    navigateToAccount,
    navigateToAccountProfile,
    navigateToAccountAddresses,
    navigateToAccountOrders,
    customer,
    logout,
    navigateToHome,
  } = useB2CRuntime();
  const navItems = [
    { id: "dashboard", label: "Overview", onClick: navigateToAccount },
    { id: "profile", label: "Profile", onClick: navigateToAccountProfile },
    { id: "addresses", label: "Addresses", onClick: navigateToAccountAddresses },
    { id: "orders", label: "Orders", onClick: navigateToAccountOrders },
  ] as const;

  const handleLogout = useCallback(async () => {
    await logout();
    navigateToHome();
  }, [logout, navigateToHome]);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-zinc-200 p-4">
        <p className="font-medium text-zinc-950">{[customer?.first_name, customer?.last_name].filter(Boolean).join(" ") || "Account"}</p>
        <p className="text-sm text-zinc-500">{customer?.email}</p>
      </div>
      <nav className="space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={item.onClick}
            className={`block w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${
              active === item.id ? "bg-zinc-100 text-zinc-950" : "text-zinc-600 hover:bg-zinc-50"
            }`}
          >
            {item.label}
          </button>
        ))}
        <button
          onClick={handleLogout}
          className="block w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50"
        >
          Log out
        </button>
      </nav>
    </div>
  );
}

// =============================================================================
// Account Dashboard
// =============================================================================

export function MedusaB2CAccountDashboardPage() {
  const { customer, isAuthenticated, navigateToHome } = useB2CRuntime();
  
  if (!isAuthenticated) return <AuthShell />;
  
  return (
    <PageShell title="Account" description="Manage your account and view your orders.">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="dashboard" />
        <div className="space-y-6">
          <div className="rounded-xl border border-zinc-200 p-6">
            <h2 className="text-lg font-medium text-zinc-950">Welcome back</h2>
            <p className="mt-2 text-sm text-zinc-600">
              You&apos;re signed in as {customer?.email}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-zinc-200 p-6">
              <h3 className="font-medium text-zinc-950">Profile</h3>
              <p className="mt-1 text-sm text-zinc-600">Manage your personal information.</p>
            </div>
            <div className="rounded-xl border border-zinc-200 p-6">
              <h3 className="font-medium text-zinc-950">Orders</h3>
              <p className="mt-1 text-sm text-zinc-600">View and track your orders.</p>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Profile Page
// =============================================================================

export function MedusaB2CAccountProfilePage() {
  const { customer, isAuthenticated, updateCustomer, customerLoading } = useB2CRuntime();
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (customer) {
      setForm({
        firstName: customer.first_name || "",
        lastName: customer.last_name || "",
        email: customer.email || "",
        phone: customer.phone || "",
      });
    }
  }, [customer]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    try {
      await updateCustomer({
        first_name: form.firstName,
        last_name: form.lastName,
        email: form.email,
        phone: form.phone,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update profile");
    }
  }, [form, updateCustomer]);

  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell title="Profile" description="Manage your personal information.">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="profile" />
        <div>
          <form onSubmit={handleSubmit} className="max-w-md space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700">First name</label>
                <input
                  type="text"
                  value={form.firstName}
                  onChange={(e) => setForm(f => ({ ...f, firstName: e.target.value }))}
                  className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700">Last name</label>
                <input
                  type="text"
                  value={form.lastName}
                  onChange={(e) => setForm(f => ({ ...f, lastName: e.target.value }))}
                  className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-700">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-700">Phone</label>
              <input
                type="tel"
                value={form.phone}
                onChange={(e) => setForm(f => ({ ...f, phone: e.target.value }))}
                className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
              />
            </div>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {success ? <p className="text-sm text-green-600">Profile updated successfully.</p> : null}
            <button
              type="submit"
              disabled={customerLoading}
              className="rounded-lg bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
            >
              {customerLoading ? "Saving..." : "Save changes"}
            </button>
          </form>
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Addresses Page
// =============================================================================

function AddressForm({
  address,
  onSave,
  onCancel,
  loading,
}: {
  address?: MedusaCustomerAddress;
  onSave: (data: {
    first_name?: string;
    last_name?: string;
    company?: string;
    address_1?: string;
    address_2?: string;
    city?: string;
    province?: string;
    postal_code?: string;
    country_code?: string;
    phone?: string;
  }) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [form, setForm] = useState({
    first_name: address?.first_name || "",
    last_name: address?.last_name || "",
    company: address?.company || "",
    address_1: address?.address_1 || "",
    address_2: address?.address_2 || "",
    city: address?.city || "",
    province: address?.province || "",
    postal_code: address?.postal_code || "",
    country_code: address?.country_code || "us",
    phone: address?.phone || "",
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-zinc-200 p-6">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-zinc-700">First name</label>
          <input
            type="text"
            value={form.first_name}
            onChange={(e) => setForm(f => ({ ...f, first_name: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Last name</label>
          <input
            type="text"
            value={form.last_name}
            onChange={(e) => setForm(f => ({ ...f, last_name: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-zinc-700">Company (optional)</label>
        <input
          type="text"
          value={form.company}
          onChange={(e) => setForm(f => ({ ...f, company: e.target.value }))}
          className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-zinc-700">Address line 1</label>
        <input
          type="text"
          value={form.address_1}
          onChange={(e) => setForm(f => ({ ...f, address_1: e.target.value }))}
          required
          className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-zinc-700">Address line 2 (optional)</label>
        <input
          type="text"
          value={form.address_2}
          onChange={(e) => setForm(f => ({ ...f, address_2: e.target.value }))}
          className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
        />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-zinc-700">City</label>
          <input
            type="text"
            value={form.city}
            onChange={(e) => setForm(f => ({ ...f, city: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Province/State</label>
          <input
            type="text"
            value={form.province}
            onChange={(e) => setForm(f => ({ ...f, province: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Postal code</label>
          <input
            type="text"
            value={form.postal_code}
            onChange={(e) => setForm(f => ({ ...f, postal_code: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-zinc-700">Country code</label>
          <select
            value={form.country_code}
            onChange={(e) => setForm(f => ({ ...f, country_code: e.target.value }))}
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          >
            <option value="us">United States</option>
            <option value="ca">Canada</option>
            <option value="gb">United Kingdom</option>
            <option value="de">Germany</option>
            <option value="fr">France</option>
            <option value="au">Australia</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Phone</label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => setForm(f => ({ ...f, phone: e.target.value }))}
            className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none"
          />
        </div>
      </div>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
        >
          {loading ? "Saving..." : address ? "Update address" : "Add address"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function MedusaB2CAccountAddressesPage() {
  const { customer, isAuthenticated, addCustomerAddress, updateCustomerAddress, deleteCustomerAddress, customerLoading } = useB2CRuntime();
  const [editingAddress, setEditingAddress] = useState<MedusaCustomerAddress | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = useCallback(async (data: Parameters<typeof addCustomerAddress>[0]) => {
    setError(null);
    try {
      await addCustomerAddress(data);
      setIsAdding(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add address");
    }
  }, [addCustomerAddress]);

  const handleUpdate = useCallback(async (data: Parameters<typeof updateCustomerAddress>[1]) => {
    if (!editingAddress) return;
    setError(null);
    try {
      await updateCustomerAddress(editingAddress.id, data);
      setEditingAddress(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update address");
    }
  }, [editingAddress, updateCustomerAddress]);

  const handleDelete = useCallback(async (addressId: string) => {
    if (!confirm("Are you sure you want to delete this address?")) return;
    setError(null);
    try {
      await deleteCustomerAddress(addressId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete address");
    }
  }, [deleteCustomerAddress]);

  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell title="Addresses" description="Manage your shipping and billing addresses.">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="addresses" />
        <div className="space-y-6">
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          
          {isAdding ? (
            <AddressForm onSave={handleAdd} onCancel={() => setIsAdding(false)} loading={customerLoading} />
          ) : (
            <button
              onClick={() => setIsAdding(true)}
              className="w-full rounded-xl border-2 border-dashed border-zinc-300 p-6 text-center text-sm font-medium text-zinc-600 hover:border-zinc-900 hover:text-zinc-900"
            >
              + Add new address
            </button>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {customer?.addresses?.map((address) => (
              <div key={address.id} className="rounded-xl border border-zinc-200 p-4">
                {editingAddress?.id === address.id ? (
                  <AddressForm
                    address={address}
                    onSave={handleUpdate}
                    onCancel={() => setEditingAddress(null)}
                    loading={customerLoading}
                  />
                ) : (
                  <>
                    <p className="font-medium text-zinc-950">
                      {[address.first_name, address.last_name].filter(Boolean).join(" ") || "Unnamed address"}
                    </p>
                    {address.company ? <p className="text-sm text-zinc-600">{address.company}</p> : null}
                    <p className="text-sm text-zinc-600">{address.address_1}</p>
                    {address.address_2 ? <p className="text-sm text-zinc-600">{address.address_2}</p> : null}
                    <p className="text-sm text-zinc-600">
                      {[address.city, address.province, address.postal_code].filter(Boolean).join(", ")}
                    </p>
                    <p className="text-sm text-zinc-600">{address.country_code?.toUpperCase()}</p>
                    {address.phone ? <p className="text-sm text-zinc-600">{address.phone}</p> : null}
                    <div className="mt-4 flex gap-3">
                      <button
                        onClick={() => setEditingAddress(address)}
                        className="text-sm font-medium text-zinc-950 underline"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(address.id)}
                        className="text-sm font-medium text-red-600 underline"
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>

          {!customer?.addresses?.length && !isAdding ? (
            <p className="text-center text-sm text-zinc-500">No addresses saved yet.</p>
          ) : null}
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Orders Page
// =============================================================================

function OrderCard({ order }: { order: MedusaOrder }) {
  const { navigateToOrder } = useB2CRuntime();
  
  return (
    <div className="rounded-xl border border-zinc-200 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-zinc-950">Order #{order.display_id || order.id.slice(-8)}</p>
          <p className="text-sm text-zinc-500">{formatDate(order.created_at)}</p>
        </div>
        <div className="text-right">
          <p className="font-medium text-zinc-950">{formatPrice(order.total, order.currency_code)}</p>
          <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${
            order.status === "completed" ? "bg-green-100 text-green-800" : "bg-zinc-100 text-zinc-800"
          }`}>
            {order.status || "Pending"}
          </span>
        </div>
      </div>
      {order.items && order.items.length > 0 && (
        <div className="mt-4 border-t border-zinc-100 pt-4">
          <p className="text-sm text-zinc-600">{order.items.length} item(s)</p>
        </div>
      )}
      <button
        onClick={() => navigateToOrder(order.id)}
        className="mt-4 text-sm font-medium text-zinc-950 underline"
      >
        View details
      </button>
    </div>
  );
}

export function MedusaB2CAccountOrdersPage() {
  const { isAuthenticated, listOrders } = useB2CRuntime();
  const [orders, setOrders] = useState<MedusaOrder[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    const loadOrders = async () => {
      try {
        setLoading(true);
        const result = await listOrders(10, 0);
        setOrders(result.orders);
        setCount(result.count);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load orders");
      } finally {
        setLoading(false);
      }
    };
    loadOrders();
  }, [isAuthenticated, listOrders]);

  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell title="Orders" description="View and track your orders.">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="orders" />
        <div className="space-y-4">
          {loading ? (
            <p className="text-sm text-zinc-500">Loading orders...</p>
          ) : error ? (
            <p className="text-sm text-red-600">{error}</p>
          ) : orders.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-zinc-950 font-medium">No orders yet</p>
              <p className="text-sm text-zinc-600 mt-1">You haven&apos;t placed any orders yet.</p>
            </div>
          ) : (
            <>
              <p className="text-sm text-zinc-600">Showing {orders.length} of {count} orders</p>
              <div className="space-y-4">
                {orders.map((order) => (
                  <OrderCard key={order.id} order={order} />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Order Detail Page
// =============================================================================

export function MedusaB2CAccountOrderDetailPage() {
  const { getOrder, isAuthenticated, requestOrderTransfer } = useB2CRuntime();
  const location = useLocation();
  const orderId = location.pathname.split("/").pop() || "";
  const [order, setOrder] = useState<MedusaOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [transferMessage, setTransferMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!orderId || !isAuthenticated) return;
    const loadOrder = async () => {
      try {
        setLoading(true);
        const orderData = await getOrder(orderId);
        setOrder(orderData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load order");
      } finally {
        setLoading(false);
      }
    };
    loadOrder();
  }, [getOrder, isAuthenticated, orderId]);

  const handleTransferRequest = useCallback(async () => {
    setTransferMessage(null);
    try {
      const transferredOrder = await requestOrderTransfer(orderId);
      setTransferMessage(
        `Transfer request sent for order ${transferredOrder.id}${transferredOrder.email ? ` to ${transferredOrder.email}` : ""}.`,
      );
    } catch (err) {
      setTransferMessage(err instanceof Error ? err.message : "Failed to request order transfer.");
    }
  }, [orderId, requestOrderTransfer]);

  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell 
      title={`Order #${order?.display_id || orderId.slice(-8)}`} 
      description="View your order details."
    >
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="orders" />
        <div>
          {loading ? (
            <p className="text-sm text-zinc-500">Loading order...</p>
          ) : error ? (
            <p className="text-sm text-red-600">{error}</p>
          ) : !order ? (
            <p className="text-sm text-zinc-500">Order not found.</p>
          ) : (
            <div className="space-y-6">
              <div className="rounded-xl border border-zinc-200 p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-zinc-500">Order date</p>
                    <p className="font-medium text-zinc-950">{formatDate(order.created_at)}</p>
                  </div>
                  <span className={`inline-flex rounded-full px-3 py-1 text-sm font-medium ${
                    order.status === "completed" ? "bg-green-100 text-green-800" : "bg-zinc-100 text-zinc-800"
                  }`}>
                    {order.status || "Pending"}
                  </span>
                </div>
              </div>

              {order.items && order.items.length > 0 && (
                <div className="rounded-xl border border-zinc-200 p-6">
                  <h3 className="font-medium text-zinc-950 mb-4">Items</h3>
                  <div className="space-y-4">
                    {order.items.map((item) => (
                      <div key={item.id} className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          {item.thumbnail && (
                            <img src={item.thumbnail} alt={item.title} className="h-16 w-16 rounded-lg object-cover" />
                          )}
                          <div>
                            <p className="font-medium text-zinc-950">{item.title}</p>
                            {item.variant_title && (
                              <p className="text-sm text-zinc-600">{item.variant_title}</p>
                            )}
                            <p className="text-sm text-zinc-500">Qty: {item.quantity}</p>
                          </div>
                        </div>
                        <p className="font-medium text-zinc-950">{formatPrice(item.total, order.currency_code)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-zinc-200 p-6">
                <h3 className="font-medium text-zinc-950 mb-4">Order summary</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-zinc-600">Subtotal</span>
                    <span className="text-zinc-950">{formatPrice(order.subtotal, order.currency_code)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-600">Shipping</span>
                    <span className="text-zinc-950">{formatPrice(order.shipping_total, order.currency_code)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-600">Tax</span>
                    <span className="text-zinc-950">{formatPrice(order.tax_total, order.currency_code)}</span>
                  </div>
                  <div className="flex justify-between border-t border-zinc-200 pt-2">
                    <span className="font-medium text-zinc-950">Total</span>
                    <span className="font-medium text-zinc-950">{formatPrice(order.total, order.currency_code)}</span>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-zinc-200 p-6">
                <h3 className="font-medium text-zinc-950 mb-4">Order transfers</h3>
                <p className="text-sm text-zinc-600">Request a transfer email if this order should move to another owner.</p>
                {transferMessage ? <p className="mt-3 text-sm text-zinc-700">{transferMessage}</p> : null}
                <button
                  onClick={() => void handleTransferRequest()}
                  className="mt-4 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-50"
                >
                  Request transfer
                </button>
              </div>

              {order.shipping_address && (
                <div className="rounded-xl border border-zinc-200 p-6">
                  <h3 className="font-medium text-zinc-950 mb-4">Shipping address</h3>
                  <div className="text-sm text-zinc-600">
                    <p>{[order.shipping_address.first_name, order.shipping_address.last_name].filter(Boolean).join(" ")}</p>
                    <p>{order.shipping_address.address_1}</p>
                    {order.shipping_address.address_2 && <p>{order.shipping_address.address_2}</p>}
                    <p>
                      {[order.shipping_address.city, order.shipping_address.province, order.shipping_address.postal_code]
                        .filter(Boolean)
                        .join(", ")}
                    </p>
                    <p>{order.shipping_address.country_code?.toUpperCase()}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Collection Page
// =============================================================================

export function MedusaB2CCollectionPage() {
  const { collections, products, productsLoading, refreshProducts, navigateToProduct } = useB2CRuntime();
  const sitePath = useResolvedSitePath();
  const collection = collections.find((item) => item.handle === sitePath.handle) || null;

  useEffect(() => {
    if (collection?.id) {
      void refreshProducts({ collectionId: [collection.id], limit: 24 });
    }
  }, [collection?.id, refreshProducts]);

  return (
    <PageShell title={collection?.title || "Collection"} description="Products from the selected Medusa collection.">
      {productsLoading ? <p className="text-sm text-zinc-500">Loading collection...</p> : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((product) => (
          <button key={product.id} onClick={() => navigateToProduct(product.handle)} className="rounded-xl border border-zinc-200 p-4 text-left hover:border-zinc-900">
            <p className="font-medium text-zinc-950">{product.title}</p>
            <p className="mt-1 text-sm text-zinc-500">{product.handle}</p>
          </button>
        ))}
      </div>
    </PageShell>
  );
}

// =============================================================================
// Category Page
// =============================================================================

export function MedusaB2CCategoryPage() {
  const { categories, products, productsLoading, refreshProducts, navigateToProduct } = useB2CRuntime();
  const sitePath = useResolvedSitePath();
  const categoryHandle = [sitePath.handle, ...sitePath.nestedPath].filter(Boolean).join("/");
  const category = categories.find((item) => item.handle === categoryHandle || item.handle === sitePath.handle) || null;

  useEffect(() => {
    if (category?.id) {
      void refreshProducts({ categoryId: [category.id], limit: 24 });
    }
  }, [category?.id, refreshProducts]);

  return (
    <PageShell title={category?.name || "Category"} description="Products from the selected Medusa category.">
      {productsLoading ? <p className="text-sm text-zinc-500">Loading category...</p> : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((product) => (
          <button key={product.id} onClick={() => navigateToProduct(product.handle)} className="rounded-xl border border-zinc-200 p-4 text-left hover:border-zinc-900">
            <p className="font-medium text-zinc-950">{product.title}</p>
            <p className="mt-1 text-sm text-zinc-500">{product.handle}</p>
          </button>
        ))}
      </div>
    </PageShell>
  );
}

// =============================================================================
// Cart Page
// =============================================================================

export function MedusaB2CCartPage() {
  const { cart, cartLoading, updateCartItem, removeCartItem, navigateToCheckout } = useB2CRuntime();
  return (
    <PageShell title="Cart" description="Your current Medusa cart contents.">
      {cartLoading ? <p className="text-sm text-zinc-500">Loading cart...</p> : null}
      {!cart?.items?.length ? <p className="text-sm text-zinc-500">Your cart is empty.</p> : null}
      <div className="space-y-4">
        {cart?.items?.map((item) => (
          <div key={item.id} className="flex items-center justify-between rounded-xl border border-zinc-200 p-4">
            <div>
              <p className="font-medium text-zinc-950">{item.title}</p>
              <p className="text-sm text-zinc-500">Qty {item.quantity}</p>
            </div>
            <div className="flex items-center gap-3">
              <button className="text-sm text-zinc-600" onClick={() => void updateCartItem(item.id, Math.max(1, item.quantity - 1))}>-</button>
              <button className="text-sm text-zinc-600" onClick={() => void updateCartItem(item.id, item.quantity + 1)}>+</button>
              <button className="text-sm text-red-600" onClick={() => void removeCartItem(item.id)}>Remove</button>
            </div>
          </div>
        ))}
      </div>
      {cart ? (
        <div className="flex items-center justify-between rounded-xl bg-zinc-50 p-4">
          <p className="font-medium text-zinc-950">Total</p>
          <div className="flex items-center gap-4">
            <p className="font-medium text-zinc-950">{formatPrice(cart.total, cart.currency_code)}</p>
            <button onClick={() => navigateToCheckout()} className="rounded-full bg-zinc-950 px-5 py-2 text-sm font-medium text-white">Checkout</button>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

// =============================================================================
// Checkout Page
// =============================================================================

type CheckoutAddressFormState = {
  first_name: string;
  last_name: string;
  company: string;
  address_1: string;
  address_2: string;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  phone: string;
};

type CheckoutFieldErrors = Partial<Record<string, string>>;

function createCheckoutAddressState(
  address?: Partial<MedusaCartAddress> | MedusaCustomerAddress | null,
  fallbackCountryCode?: string,
): CheckoutAddressFormState {
  return {
    first_name: address?.first_name || "",
    last_name: address?.last_name || "",
    company: "company" in (address || {}) && typeof address?.company === "string" ? address.company : "",
    address_1: address?.address_1 || "",
    address_2: address?.address_2 || "",
    city: address?.city || "",
    province: address?.province || "",
    postal_code: address?.postal_code || "",
    country_code: (address?.country_code || fallbackCountryCode || "").toLowerCase(),
    phone: address?.phone || "",
  };
}

function isAddressReadyForRating(address?: Partial<CheckoutAddressFormState> | Partial<MedusaCartAddress> | null): boolean {
  if (!address) return false;
  return Boolean(
    address.first_name?.trim() &&
      address.last_name?.trim() &&
      address.address_1?.trim() &&
      address.city?.trim() &&
      address.postal_code?.trim() &&
      address.country_code?.trim(),
  );
}

function emailLooksValid(email: string): boolean {
  return /^\S+@\S+\.\S+$/.test(email.trim());
}

function humanizeProviderLabel(providerId: string): string {
  return providerId
    .replace(/^pp_/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function getPaymentRedirectUrl(paymentCollection: MedusaPaymentCollection, providerId: string): string | null {
  const session = paymentCollection.payment_sessions?.find((entry) => entry.provider_id === providerId);
  return typeof session?.data?.redirect_url === "string" ? session.data.redirect_url : null;
}

function CheckoutShell({
  children,
  cartCount,
  cartTotal,
  onBackToCart,
  onToggleMobileSummary,
}: {
  children: React.ReactNode;
  cartCount: number;
  cartTotal: string;
  onBackToCart: () => void;
  onToggleMobileSummary: () => void;
}) {
  return (
    <div className="min-h-screen bg-stone-50 text-zinc-950" data-testid="b2c-checkout-page">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <button onClick={onBackToCart} className="text-sm font-medium text-zinc-600 transition hover:text-zinc-950">
            Back to cart
          </button>
          <div className="text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-zinc-500">Secure checkout</p>
            <h1 className="text-lg font-semibold text-zinc-950">Checkout</h1>
          </div>
          <div className="text-right text-sm text-zinc-500">
            <p>{cartCount} item{cartCount === 1 ? "" : "s"}</p>
            <p className="font-medium text-zinc-950">{cartTotal}</p>
          </div>
        </div>
      </header>
      <div className="border-b border-zinc-200 bg-white px-4 py-3 sm:hidden">
        <button
          type="button"
          onClick={onToggleMobileSummary}
          className="flex w-full items-center justify-between rounded-2xl border border-zinc-200 bg-stone-50 px-4 py-3 text-left text-sm font-medium text-zinc-950"
          data-testid="b2c-mobile-summary-toggle"
        >
          <span>Order summary</span>
          <span>{cartTotal}</span>
        </button>
      </div>
      {children}
    </div>
  );
}

function CheckoutSection({
  title,
  description,
  action,
  children,
  disabled = false,
  testId,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <section className="rounded-[28px] border border-zinc-200 bg-white" data-testid={testId}>
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-100 px-5 py-5 sm:px-6">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-zinc-950">{title}</h2>
          {description ? <p className="max-w-2xl text-sm text-zinc-500">{description}</p> : null}
        </div>
        {action}
      </div>
      <div className={disabled ? "pointer-events-none opacity-60" : undefined}>{children}</div>
    </section>
  );
}

function CheckoutFieldError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-xs font-medium text-red-600">{message}</p> : null;
}

function CheckoutAddressFields({
  prefix,
  address,
  errors,
  onChange,
  countries,
  countryLocked,
  countryHint,
}: {
  prefix: "shipping" | "billing";
  address: CheckoutAddressFormState;
  errors: CheckoutFieldErrors;
  onChange: (field: keyof CheckoutAddressFormState, value: string) => void;
  countries: Array<{ iso_2: string; display_name?: string }>;
  countryLocked: boolean;
  countryHint?: string | null;
}) {
  const inputClassName =
    "mt-2 w-full rounded-2xl border border-zinc-200 bg-stone-50 px-4 py-3 text-sm text-zinc-950 outline-none transition placeholder:text-zinc-400 focus:border-zinc-400 focus:bg-white";

  const selectValue = address.country_code || countries[0]?.iso_2 || "";

  return (
    <div className="space-y-4 px-5 py-5 sm:px-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium text-zinc-700">
          First name
          <input
            value={address.first_name}
            onChange={(event) => onChange("first_name", event.target.value)}
            autoComplete={`${prefix} given-name`}
            className={inputClassName}
          />
          <CheckoutFieldError message={errors[`${prefix}_first_name`]} />
        </label>
        <label className="block text-sm font-medium text-zinc-700">
          Last name
          <input
            value={address.last_name}
            onChange={(event) => onChange("last_name", event.target.value)}
            autoComplete={`${prefix} family-name`}
            className={inputClassName}
          />
          <CheckoutFieldError message={errors[`${prefix}_last_name`]} />
        </label>
      </div>
      <label className="block text-sm font-medium text-zinc-700">
        Company
        <input
          value={address.company}
          onChange={(event) => onChange("company", event.target.value)}
          autoComplete={`${prefix} organization`}
          className={inputClassName}
        />
      </label>
      <label className="block text-sm font-medium text-zinc-700">
        Address
        <input
          value={address.address_1}
          onChange={(event) => onChange("address_1", event.target.value)}
          autoComplete={`${prefix} address-line1`}
          className={inputClassName}
        />
        <CheckoutFieldError message={errors[`${prefix}_address_1`]} />
      </label>
      <label className="block text-sm font-medium text-zinc-700">
        Apartment, suite, etc. (optional)
        <input
          value={address.address_2}
          onChange={(event) => onChange("address_2", event.target.value)}
          autoComplete={`${prefix} address-line2`}
          className={inputClassName}
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-[1.1fr_0.9fr]">
        <label className="block text-sm font-medium text-zinc-700">
          City
          <input
            value={address.city}
            onChange={(event) => onChange("city", event.target.value)}
            autoComplete={`${prefix} address-level2`}
            className={inputClassName}
          />
          <CheckoutFieldError message={errors[`${prefix}_city`]} />
        </label>
        <label className="block text-sm font-medium text-zinc-700">
          State / Province
          <input
            value={address.province}
            onChange={(event) => onChange("province", event.target.value)}
            autoComplete={`${prefix} address-level1`}
            className={inputClassName}
          />
        </label>
      </div>
      <div className="grid gap-4 sm:grid-cols-[0.9fr_1.1fr]">
        <label className="block text-sm font-medium text-zinc-700">
          ZIP / Postal code
          <input
            value={address.postal_code}
            onChange={(event) => onChange("postal_code", event.target.value)}
            autoComplete={`${prefix} postal-code`}
            className={inputClassName}
          />
          <CheckoutFieldError message={errors[`${prefix}_postal_code`]} />
        </label>
        <label className="block text-sm font-medium text-zinc-700">
          Country / Region
          <select
            value={selectValue}
            onChange={(event) => onChange("country_code", event.target.value)}
            className={`${inputClassName} appearance-none`}
            disabled={countryLocked && countries.length <= 1}
          >
            {countries.length ? (
              countries.map((country) => (
                <option key={country.iso_2} value={country.iso_2}>
                  {country.display_name || country.iso_2.toUpperCase()}
                </option>
              ))
            ) : (
              <option value={selectValue}>{selectValue ? selectValue.toUpperCase() : "Unavailable"}</option>
            )}
          </select>
          <CheckoutFieldError message={errors[`${prefix}_country_code`]} />
          {countryHint ? <p className="mt-1 text-xs text-zinc-500">{countryHint}</p> : null}
        </label>
      </div>
      <label className="block text-sm font-medium text-zinc-700">
        Phone (optional)
        <input
          value={address.phone}
          onChange={(event) => onChange("phone", event.target.value)}
          autoComplete={`${prefix} tel`}
          className={inputClassName}
        />
      </label>
    </div>
  );
}

function CheckoutSummary({
  cart,
  currencyCode,
  shippingCompleted,
  mobile = false,
}: {
  cart: NonNullable<ReturnType<typeof useB2CRuntime>["cart"]>;
  currencyCode: string;
  shippingCompleted: boolean;
  mobile?: boolean;
}) {
  const displayShippingTotal = shippingCompleted ? cart.shipping_total || 0 : 0;
  const displayTotal = (cart.subtotal || 0) + displayShippingTotal + (cart.tax_total || 0) - (cart.discount_total || 0);

  return (
    <aside
      className={mobile ? "rounded-[28px] border border-zinc-200 bg-white" : "sticky top-6 rounded-[28px] border border-zinc-200 bg-white"}
      data-testid={mobile ? "b2c-checkout-summary-mobile" : "b2c-checkout-summary"}
    >
      <div className="border-b border-zinc-100 px-5 py-5 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-zinc-950">Order summary</h2>
          <p className="text-sm text-zinc-500">{cart.items?.length || 0} item{cart.items?.length === 1 ? "" : "s"}</p>
        </div>
      </div>
      <div className="space-y-4 px-5 py-5 sm:px-6">
        <div className="space-y-3">
          {cart.items?.map((item) => (
            <div key={item.id} className="flex items-start justify-between gap-3 rounded-2xl bg-stone-50 px-4 py-3">
              <div className="min-w-0 space-y-1">
                <p className="truncate text-sm font-medium text-zinc-950">{item.title}</p>
                <p className="text-xs text-zinc-500">Qty {item.quantity}{item.variant?.title ? ` · ${item.variant.title}` : ""}</p>
              </div>
              <p className="shrink-0 text-sm font-medium text-zinc-950">{formatPrice(item.total ?? item.unit_price * item.quantity, currencyCode)}</p>
            </div>
          ))}
        </div>
        <div className="space-y-3 border-t border-zinc-100 pt-4 text-sm text-zinc-600">
          <div className="flex items-center justify-between">
            <span>Subtotal</span>
            <span className="font-medium text-zinc-950">{formatPrice(cart.subtotal, currencyCode)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Shipping</span>
            <span className="font-medium text-zinc-950">
              {shippingCompleted && displayShippingTotal > 0
                ? formatPrice(displayShippingTotal, currencyCode)
                : "Calculated next"}
            </span>
          </div>
          {cart.tax_total ? (
            <div className="flex items-center justify-between">
              <span>Taxes</span>
              <span className="font-medium text-zinc-950">{formatPrice(cart.tax_total, currencyCode)}</span>
            </div>
          ) : null}
          {cart.discount_total ? (
            <div className="flex items-center justify-between">
              <span>Discounts</span>
              <span className="font-medium text-zinc-950">-{formatPrice(cart.discount_total, currencyCode)}</span>
            </div>
          ) : null}
        </div>
        <div className="flex items-center justify-between border-t border-zinc-100 pt-4">
          <div>
            <p className="text-sm font-medium text-zinc-950">Total</p>
            <p className="text-xs text-zinc-500">Including taxes where applicable</p>
          </div>
          <p className="text-lg font-semibold text-zinc-950">{formatPrice(displayTotal, currencyCode)}</p>
        </div>
      </div>
    </aside>
  );
}

function CheckoutFooterLinks() {
  const funnelRuntime = useFunnelRuntime();
  const { countryCode } = useB2CRuntime();

  const policyLinks = [
    { label: "Privacy policy", slug: "privacy-policy" },
    { label: "Terms of service", slug: "terms-of-service" },
    { label: "Shipping policy", slug: "shipping-policy" },
    { label: "Refund policy", slug: "refund-policy" },
  ].map((link) => ({
    label: link.label,
    href: funnelRuntime
      ? buildPublicFunnelPath({
          productSlug: funnelRuntime.productSlug,
          funnelSlug: funnelRuntime.funnelSlug,
          bundleMode: funnelRuntime.bundleMode || false,
          sitePath: `${countryCode || "us"}/policies/${link.slug}`,
        })
      : `/policies/${link.slug}`,
  }));

  return (
    <div className="rounded-[28px] border border-zinc-200 bg-white px-5 py-5 text-sm text-zinc-600 sm:px-6" data-testid="b2c-checkout-footer-links">
      <p className="font-medium text-zinc-950">Secure checkout</p>
      <p className="mt-2 leading-6">
        Your payment details stay with the selected payment provider. Unsupported wallet, promo, and autocomplete
        affordances are intentionally omitted from this checkout.
      </p>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs font-medium text-zinc-700">
        {policyLinks.map((link) => (
          <a key={link.href} href={link.href} className="underline decoration-zinc-300 underline-offset-4 transition hover:text-zinc-950">
            {link.label}
          </a>
        ))}
      </div>
    </div>
  );
}

export function MedusaB2CCheckoutPage() {
  const {
    cart,
    cartLoading,
    customer,
    isAuthenticated,
    regions,
    navigateToAccount,
    navigateToCart,
    navigateToOrderConfirmed,
    getShippingOptions,
    getPaymentProviders,
    performCheckoutAction,
    completeCheckout,
    updateCartBillingAddress,
  } = useB2CRuntime();
  const [email, setEmail] = useState("");
  const [shippingAddress, setShippingAddress] = useState<CheckoutAddressFormState>(() => createCheckoutAddressState());
  const [billingSameAsShipping, setBillingSameAsShipping] = useState(true);
  const [billingAddress, setBillingAddress] = useState<CheckoutAddressFormState>(() => createCheckoutAddressState());
  const [fieldErrors, setFieldErrors] = useState<CheckoutFieldErrors>({});
  const [sectionErrors, setSectionErrors] = useState<CheckoutFieldErrors>({});
  const [shippingOptions, setShippingOptions] = useState<MedusaShippingOption[]>([]);
  const [shippingOptionsLoading, setShippingOptionsLoading] = useState(false);
  const [shippingOptionsLoaded, setShippingOptionsLoaded] = useState(false);
  const [deliveryVersion, setDeliveryVersion] = useState(0);
  const [shippingVersion, setShippingVersion] = useState(0);
  const [selectedShippingOptionId, setSelectedShippingOptionId] = useState<string | null>(null);
  const [shippingAddressEdited, setShippingAddressEdited] = useState(false);
  const [paymentProviders, setPaymentProviders] = useState<MedusaPaymentProvider[]>([]);
  const [paymentProvidersLoading, setPaymentProvidersLoading] = useState(false);
  const [paymentProvidersLoaded, setPaymentProvidersLoaded] = useState(false);
  const [selectedPaymentProviderId, setSelectedPaymentProviderId] = useState<string | null>(null);
  const [billingAddressEdited, setBillingAddressEdited] = useState(false);
  const [paymentRedirectUrl, setPaymentRedirectUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false);
  const [hydratedCartId, setHydratedCartId] = useState<string | null>(null);

  const activeRegion = useMemo(() => regions.find((region) => region.id === cart?.region_id) || null, [regions, cart?.region_id]);
  const activeCountries = useMemo(() => activeRegion?.countries || [], [activeRegion]);
  const defaultCountryCode = useMemo(
    () => cart?.shipping_address?.country_code || customer?.addresses?.find((address) => address.is_default_shipping)?.country_code || activeCountries[0]?.iso_2 || "",
    [activeCountries, cart?.shipping_address?.country_code, customer?.addresses],
  );
  const currencyCode = cart?.currency_code || "usd";
  const activeCartCount = cart?.items?.length || 0;
  const contactCompleted = Boolean(cart?.email?.trim()) && cart?.email === email.trim();
  const deliveryCompleted = isAddressReadyForRating(cart?.shipping_address);
  const cartShippingMethodId = cart?.shipping_methods?.[0]?.shipping_option_id || null;
  const shippingCompleted = Boolean(cartShippingMethodId) && deliveryVersion > 0 && shippingVersion === deliveryVersion && !shippingAddressEdited;
  const visibleShippingOptionId = shippingAddressEdited ? null : shippingCompleted ? (selectedShippingOptionId || cartShippingMethodId) : selectedShippingOptionId;
  const visibleOrderTotal = formatPrice(
    (cart?.subtotal || 0) + (shippingCompleted ? cart?.shipping_total || 0 : 0) + (cart?.tax_total || 0) - (cart?.discount_total || 0),
    currencyCode,
  );
  const countryHint = activeCountries.length <= 1
    ? "This checkout is tied to the current storefront country. To ship elsewhere, start a new checkout from that country storefront."
    : "Only countries already supported by this checkout region are available here.";

  useEffect(() => {
    if (!cart) return;
    const defaultShippingAddress = customer?.addresses?.find((address) => address.is_default_shipping) || customer?.addresses?.[0] || null;
    const defaultBillingAddress = customer?.addresses?.find((address) => address.is_default_billing) || defaultShippingAddress;
    if (hydratedCartId !== cart.id) {
      const initialDeliveryVersion = isAddressReadyForRating(cart.shipping_address) ? 1 : 0;
      const initialShippingVersion = cart.shipping_methods?.[0]?.shipping_option_id && initialDeliveryVersion ? initialDeliveryVersion : 0;
      setEmail(cart.email || customer?.email || "");
      setShippingAddress(createCheckoutAddressState(cart.shipping_address || defaultShippingAddress, defaultCountryCode));
      setBillingAddress(createCheckoutAddressState(cart.billing_address || defaultBillingAddress || cart.shipping_address || defaultShippingAddress, defaultCountryCode));
      setSelectedShippingOptionId(cart.shipping_methods?.[0]?.shipping_option_id || null);
      setDeliveryVersion(initialDeliveryVersion);
      setShippingVersion(initialShippingVersion);
      setShippingAddressEdited(false);
      setBillingAddressEdited(false);
      setHydratedCartId(cart.id);
      setFieldErrors({});
      setSectionErrors({});
      setShippingOptionsLoaded(false);
      setPaymentProvidersLoaded(false);
      return;
    }

    if (customer?.email && !cart.email && !email.trim()) {
      setEmail(customer.email);
    }

    if (!cart.shipping_address && defaultShippingAddress && !shippingAddressEdited && !isAddressReadyForRating(shippingAddress)) {
      setShippingAddress(createCheckoutAddressState(defaultShippingAddress, defaultCountryCode));
    }

    if (!cart.billing_address && defaultBillingAddress && !billingAddressEdited && !isAddressReadyForRating(billingAddress)) {
      setBillingAddress(createCheckoutAddressState(defaultBillingAddress, defaultCountryCode));
    }
  }, [billingAddress, billingAddressEdited, cart, customer, defaultCountryCode, email, hydratedCartId, shippingAddress, shippingAddressEdited]);

  useEffect(() => {
    if (!cart?.shipping_methods?.[0]?.shipping_option_id) return;
    setSelectedShippingOptionId(cart.shipping_methods[0].shipping_option_id);
  }, [cart?.shipping_methods]);

  const updateSectionError = useCallback((section: string, message?: string | null) => {
    setSectionErrors((current) => {
      const next = { ...current };
      if (!message) {
        delete next[section];
      } else {
        next[section] = message;
      }
      return next;
    });
  }, []);

  const updateShippingField = useCallback((field: keyof CheckoutAddressFormState, value: string) => {
    setShippingAddressEdited(true);
    setShippingAddress((current) => ({ ...current, [field]: field === "country_code" ? value.toLowerCase() : value }));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[`shipping_${field}`];
      return next;
    });
  }, []);

  const updateBillingField = useCallback((field: keyof CheckoutAddressFormState, value: string) => {
    setBillingAddressEdited(true);
    setBillingAddress((current) => ({ ...current, [field]: field === "country_code" ? value.toLowerCase() : value }));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[`billing_${field}`];
      return next;
    });
  }, []);

  const validateAddress = useCallback((prefix: "shipping" | "billing", address: CheckoutAddressFormState) => {
    const nextErrors: CheckoutFieldErrors = {};
    if (!address.first_name.trim()) nextErrors[`${prefix}_first_name`] = "Enter a first name.";
    if (!address.last_name.trim()) nextErrors[`${prefix}_last_name`] = "Enter a last name.";
    if (!address.address_1.trim()) nextErrors[`${prefix}_address_1`] = "Enter a street address.";
    if (!address.city.trim()) nextErrors[`${prefix}_city`] = "Enter a city.";
    if (!address.postal_code.trim()) nextErrors[`${prefix}_postal_code`] = "Enter a ZIP or postal code.";
    if (!address.country_code.trim()) {
      nextErrors[`${prefix}_country_code`] = "Select a country / region.";
    } else if (activeCountries.length && !activeCountries.some((country) => country.iso_2 === address.country_code.toLowerCase())) {
      nextErrors[`${prefix}_country_code`] = "This checkout cannot switch to a different region. Start a new checkout for that country.";
    }
    return nextErrors;
  }, [activeCountries]);

  const loadShippingOptions = useCallback(async () => {
    setShippingOptionsLoading(true);
    setShippingOptionsLoaded(false);
    updateSectionError("shipping", null);
    try {
      const options = await getShippingOptions();
      setShippingOptions(options);
      if (!options.length) {
        updateSectionError("shipping", "No shipping options are available for this address yet.");
      }
      return options;
    } catch (err) {
      updateSectionError("shipping", err instanceof Error ? err.message : "Unable to load shipping options.");
      return [];
    } finally {
      setShippingOptionsLoaded(true);
      setShippingOptionsLoading(false);
    }
  }, [getShippingOptions, updateSectionError]);

  const loadPaymentProviders = useCallback(async () => {
    setPaymentProvidersLoading(true);
    setPaymentProvidersLoaded(false);
    updateSectionError("payment", null);
    try {
      const providers = await getPaymentProviders();
      setPaymentProviders(providers);
      if (!providers.length) {
        updateSectionError("payment", "No payment methods are available for this checkout yet.");
      }
      return providers;
    } catch (err) {
      updateSectionError("payment", err instanceof Error ? err.message : "Unable to load payment methods.");
      return [];
    } finally {
      setPaymentProvidersLoaded(true);
      setPaymentProvidersLoading(false);
    }
  }, [getPaymentProviders, updateSectionError]);

  useEffect(() => {
    if (!cart || !deliveryCompleted || shippingOptions.length || shippingOptionsLoading || shippingOptionsLoaded) return;
    void loadShippingOptions();
  }, [cart, deliveryCompleted, loadShippingOptions, shippingOptions.length, shippingOptionsLoaded, shippingOptionsLoading]);

  useEffect(() => {
    if (!cart || !shippingCompleted || paymentProviders.length || paymentProvidersLoading || paymentProvidersLoaded) return;
    void loadPaymentProviders();
  }, [cart, loadPaymentProviders, paymentProviders.length, paymentProvidersLoaded, paymentProvidersLoading, shippingCompleted]);

  const saveContact = useCallback(async () => {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setFieldErrors((current) => ({ ...current, contact_email: "Enter an email address." }));
      return false;
    }
    if (!emailLooksValid(trimmedEmail)) {
      setFieldErrors((current) => ({ ...current, contact_email: "Enter a valid email address." }));
      return false;
    }
    try {
      await performCheckoutAction("update_email", { step: "update_email", email: trimmedEmail });
      updateSectionError("contact", null);
      return true;
    } catch (err) {
      updateSectionError("contact", err instanceof Error ? err.message : "Unable to save your email.");
      return false;
    }
  }, [email, performCheckoutAction, updateSectionError]);

  const saveDelivery = useCallback(async () => {
    const nextDeliveryVersion = deliveryVersion + 1;
    const trimmedEmail = email.trim();
    const nextFieldErrors: CheckoutFieldErrors = { ...validateAddress("shipping", shippingAddress) };
    if (!trimmedEmail) {
      nextFieldErrors.contact_email = "Enter an email address.";
    } else if (!emailLooksValid(trimmedEmail)) {
      nextFieldErrors.contact_email = "Enter a valid email address.";
    }
    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors((current) => ({ ...current, ...nextFieldErrors }));
      return;
    }

    setSelectedShippingOptionId(null);
    setSelectedPaymentProviderId(null);
    setPaymentRedirectUrl(null);
    setPaymentProviders([]);
    setShippingOptionsLoaded(false);
    setPaymentProvidersLoaded(false);
    setShippingVersion(0);
    try {
      await performCheckoutAction("update_email", { step: "update_email", email: trimmedEmail });
      await performCheckoutAction("update_shipping_address", { step: "update_shipping_address", address: shippingAddress });
      setShippingAddressEdited(false);
      setDeliveryVersion(nextDeliveryVersion);
      updateSectionError("delivery", null);
      await loadShippingOptions();
    } catch (err) {
      updateSectionError("delivery", err instanceof Error ? err.message : "Unable to save your delivery details.");
    }
  }, [deliveryVersion, email, loadShippingOptions, performCheckoutAction, shippingAddress, updateSectionError, validateAddress]);

  const selectShippingOption = useCallback(async (optionId: string) => {
    setSelectedPaymentProviderId(null);
    setPaymentRedirectUrl(null);
    setPaymentProviders([]);
    setPaymentProvidersLoaded(false);
    try {
      await performCheckoutAction("set_shipping_method", { step: "set_shipping_method", optionId });
      setSelectedShippingOptionId(optionId);
      setShippingVersion(deliveryVersion);
      updateSectionError("shipping", null);
      await loadPaymentProviders();
    } catch (err) {
      updateSectionError("shipping", err instanceof Error ? err.message : "Unable to save your shipping method.");
    }
  }, [deliveryVersion, loadPaymentProviders, performCheckoutAction, updateSectionError]);

  const selectPaymentProvider = useCallback(async (providerId: string) => {
    setSelectedPaymentProviderId(providerId);
    try {
      const paymentCollection = await performCheckoutAction("init_payment_session", {
        step: "init_payment_session",
        providerId,
      });
      if ("payment_sessions" in paymentCollection) {
        setPaymentRedirectUrl(getPaymentRedirectUrl(paymentCollection, providerId));
      }
      updateSectionError("payment", null);
    } catch (err) {
      updateSectionError("payment", err instanceof Error ? err.message : "Unable to initialize the payment method.");
    }
  }, [performCheckoutAction, updateSectionError]);

  const handleComplete = useCallback(async () => {
    updateSectionError("payment", null);
    const nextFieldErrors = billingSameAsShipping ? {} : validateAddress("billing", billingAddress);
    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors((current) => ({ ...current, ...nextFieldErrors }));
      return;
    }
    if (!selectedPaymentProviderId) {
      updateSectionError("payment", "Choose a payment method before completing checkout.");
      return;
    }

    setSubmitting(true);
    try {
      const billingPayload = billingSameAsShipping ? shippingAddress : billingAddress;
      if (billingSameAsShipping) {
        setBillingAddressEdited(false);
      }
      await updateCartBillingAddress(billingPayload);
      const paymentCollection = await performCheckoutAction("init_payment_session", {
        step: "init_payment_session",
        providerId: selectedPaymentProviderId,
      });
      if ("payment_sessions" in paymentCollection) {
        const redirectUrl = getPaymentRedirectUrl(paymentCollection, selectedPaymentProviderId);
        if (redirectUrl) {
          window.location.assign(redirectUrl);
          return;
        }
      }
      const result = await completeCheckout();
      if (result.type === "order" && result.order) {
        navigateToOrderConfirmed(result.order.id);
        return;
      }
      updateSectionError("payment", "Checkout could not be completed. Please review your payment details and try again.");
    } catch (err) {
      updateSectionError("payment", err instanceof Error ? err.message : "Unable to complete checkout.");
    } finally {
      setSubmitting(false);
    }
  }, [
    billingAddress,
    billingSameAsShipping,
    completeCheckout,
    navigateToOrderConfirmed,
    performCheckoutAction,
    selectedPaymentProviderId,
    shippingAddress,
    updateCartBillingAddress,
    updateSectionError,
    validateAddress,
  ]);

  if (cartLoading && !cart) {
    return <div className="min-h-screen bg-stone-50 px-4 py-16 text-center text-sm text-zinc-500">Loading checkout…</div>;
  }

  if (!cart || !cart.items?.length) {
    return (
      <div className="min-h-screen bg-stone-50 px-4 py-16 sm:px-6 lg:px-8" data-testid="b2c-checkout-empty-state">
        <div className="mx-auto max-w-xl rounded-[32px] border border-zinc-200 bg-white px-8 py-10 text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-zinc-500">Checkout</p>
          <h1 className="mt-3 text-3xl font-semibold text-zinc-950">Your cart is empty</h1>
          <p className="mt-3 text-sm leading-6 text-zinc-600">
            Add something to your cart before continuing to checkout.
          </p>
          <button
            onClick={() => navigateToCart()}
            className="mt-6 rounded-full bg-zinc-950 px-6 py-3 text-sm font-medium text-white transition hover:bg-zinc-800"
          >
            Back to cart
          </button>
        </div>
      </div>
    );
  }

  return (
    <CheckoutShell
      cartCount={activeCartCount}
      cartTotal={visibleOrderTotal}
      onBackToCart={navigateToCart}
      onToggleMobileSummary={() => setMobileSummaryOpen((current) => !current)}
    >
      <main className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:px-8 lg:py-8">
        <div className="space-y-5">
          {mobileSummaryOpen ? <CheckoutSummary cart={cart} currencyCode={currencyCode} shippingCompleted={shippingCompleted} mobile /> : null}

          <CheckoutSection
            title="Contact"
            description="Use this email for order updates and receipt delivery."
            action={!isAuthenticated ? (
              <button onClick={() => navigateToAccount()} className="text-sm font-medium text-zinc-700 underline underline-offset-4">
                Sign in
              </button>
            ) : <span className="text-sm font-medium text-emerald-700">Signed in</span>}
            testId="b2c-checkout-contact"
          >
            <div className="space-y-4 px-5 py-5 sm:px-6">
              <label className="block text-sm font-medium text-zinc-700">
                Email address
                <input
                  type="email"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setFieldErrors((current) => {
                      const next = { ...current };
                      delete next.contact_email;
                      return next;
                    });
                  }}
                  autoComplete="email"
                  className="mt-2 w-full rounded-2xl border border-zinc-200 bg-stone-50 px-4 py-3 text-sm text-zinc-950 outline-none transition placeholder:text-zinc-400 focus:border-zinc-400 focus:bg-white"
                />
                <CheckoutFieldError message={fieldErrors.contact_email} />
              </label>
              {sectionErrors.contact ? <p className="text-sm font-medium text-red-600">{sectionErrors.contact}</p> : null}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-zinc-500">{contactCompleted ? "Saved for this checkout." : "Save your email before placing the order."}</p>
                <button
                  type="button"
                  onClick={() => void saveContact()}
                  className="rounded-full border border-zinc-300 px-5 py-2.5 text-sm font-medium text-zinc-950 transition hover:border-zinc-500 hover:bg-stone-50"
                >
                  Save contact
                </button>
              </div>
            </div>
          </CheckoutSection>

          <CheckoutSection
            title="Delivery"
            description="Enter the shipping address that should be used to rate available delivery methods."
            testId="b2c-checkout-delivery"
          >
            <CheckoutAddressFields
              prefix="shipping"
              address={shippingAddress}
              errors={fieldErrors}
              onChange={updateShippingField}
              countries={activeCountries}
              countryLocked={activeCountries.length <= 1}
              countryHint={countryHint}
            />
            <div className="space-y-4 border-t border-zinc-100 px-5 py-5 sm:px-6">
              {sectionErrors.delivery ? <p className="text-sm font-medium text-red-600">{sectionErrors.delivery}</p> : null}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-zinc-500">Shipping methods unlock after this address is saved.</p>
                <button
                  type="button"
                  onClick={() => void saveDelivery()}
                  className="rounded-full bg-zinc-950 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800"
                  data-testid="b2c-save-delivery"
                >
                  Continue to shipping
                </button>
              </div>
            </div>
          </CheckoutSection>

          <CheckoutSection
            title="Shipping"
            description="Select one of the live delivery methods available for this address."
            disabled={!deliveryCompleted}
            testId="b2c-checkout-shipping"
          >
            <div className="space-y-4 px-5 py-5 sm:px-6">
              {!deliveryCompleted ? <p className="text-sm text-zinc-500">Save a valid delivery address to load shipping options.</p> : null}
              {deliveryCompleted && shippingOptionsLoading ? <p className="text-sm text-zinc-500">Loading shipping options…</p> : null}
              {sectionErrors.shipping ? <p className="text-sm font-medium text-red-600">{sectionErrors.shipping}</p> : null}
              {deliveryCompleted && !shippingOptionsLoading && shippingOptions.length ? (
                <div className="space-y-3" data-testid="b2c-shipping-options">
                  {shippingOptions.map((option) => {
                    const isSelected = visibleShippingOptionId === option.id;
                    return (
                      <label
                        key={option.id}
                        className={`flex cursor-pointer items-start justify-between gap-4 rounded-2xl border px-4 py-4 transition ${
                          isSelected ? "border-zinc-950 bg-stone-50" : "border-zinc-200 bg-white hover:border-zinc-400"
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <input
                            type="radio"
                            checked={isSelected}
                            onChange={() => void selectShippingOption(option.id)}
                            className="mt-1 h-4 w-4 border-zinc-300 text-zinc-950 focus:ring-zinc-500"
                          />
                          <div>
                            <p className="text-sm font-medium text-zinc-950">{option.name}</p>
                            <p className="text-xs text-zinc-500">Calculated through the active Medusa shipping setup.</p>
                          </div>
                        </div>
                        <p className="text-sm font-medium text-zinc-950">{formatPrice(option.amount || 0, option.currency_code || currencyCode)}</p>
                      </label>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </CheckoutSection>

          <CheckoutSection
            title="Payment"
            description="Choose a real payment provider from the active Medusa configuration."
            disabled={!shippingCompleted}
            testId="b2c-checkout-payment"
          >
            <div className="space-y-4 px-5 py-5 sm:px-6">
              {!shippingCompleted ? <p className="text-sm text-zinc-500">Choose a shipping method before selecting a payment option.</p> : null}
              {shippingCompleted && paymentProvidersLoading ? <p className="text-sm text-zinc-500">Loading payment methods…</p> : null}
              {sectionErrors.payment ? <p className="text-sm font-medium text-red-600">{sectionErrors.payment}</p> : null}
              {shippingCompleted && paymentProviders.length ? (
                <div className="space-y-3" data-testid="b2c-payment-providers">
                  {paymentProviders.map((provider) => {
                    const isSelected = selectedPaymentProviderId === provider.id;
                    return (
                      <label
                        key={provider.id}
                        className={`block cursor-pointer rounded-2xl border px-4 py-4 transition ${
                          isSelected ? "border-zinc-950 bg-stone-50" : "border-zinc-200 bg-white hover:border-zinc-400"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3">
                            <input
                              type="radio"
                              checked={isSelected}
                              onChange={() => void selectPaymentProvider(provider.id)}
                              className="mt-1 h-4 w-4 border-zinc-300 text-zinc-950 focus:ring-zinc-500"
                            />
                            <div>
                              <p className="text-sm font-medium text-zinc-950">{humanizeProviderLabel(provider.id)}</p>
                              <p className="text-xs text-zinc-500">
                                {paymentRedirectUrl && isSelected ? "You’ll continue with this provider after reviewing your order." : "Provider-specific behavior is handled by the live checkout runtime."}
                              </p>
                            </div>
                          </div>
                          <span className="rounded-full bg-zinc-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                            {provider.id}
                          </span>
                        </div>
                      </label>
                    );
                  })}
                </div>
              ) : null}
            </div>
            <div className="space-y-4 border-t border-zinc-100 px-5 py-5 sm:px-6">
              <label className="flex items-start gap-3 rounded-2xl border border-zinc-200 bg-stone-50 px-4 py-3 text-sm text-zinc-700">
                <input
                  type="checkbox"
                  checked={billingSameAsShipping}
                  onChange={(event) => setBillingSameAsShipping(event.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-zinc-950 focus:ring-zinc-500"
                />
                <span>Billing address is the same as shipping.</span>
              </label>
              {!billingSameAsShipping ? (
                <div className="rounded-[24px] border border-zinc-200 bg-white">
                  <div className="border-b border-zinc-100 px-5 py-4 sm:px-6">
                    <h3 className="text-sm font-semibold text-zinc-950">Billing address</h3>
                  </div>
                  <CheckoutAddressFields
                    prefix="billing"
                    address={billingAddress}
                    errors={fieldErrors}
                    onChange={updateBillingField}
                    countries={activeCountries}
                    countryLocked={activeCountries.length <= 1}
                    countryHint={countryHint}
                  />
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => void handleComplete()}
                disabled={submitting || !selectedPaymentProviderId || !shippingCompleted}
                className="w-full rounded-full bg-zinc-950 px-6 py-3 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="b2c-complete-checkout"
              >
                {submitting ? "Submitting…" : paymentRedirectUrl ? "Continue to payment" : "Complete order"}
              </button>
            </div>
          </CheckoutSection>

          <CheckoutFooterLinks />
        </div>

        <div className="hidden lg:block">
          <CheckoutSummary cart={cart} currencyCode={currencyCode} shippingCompleted={shippingCompleted} />
        </div>
      </main>
    </CheckoutShell>
  );
}

// =============================================================================
// Order Confirmed Page
// =============================================================================

export function MedusaB2COrderConfirmedPage() {
  const location = useLocation();
  const orderId = location.pathname.split("/").slice(-2, -1)[0] || "";
  return <PageShell title="Order confirmed" description={orderId ? `Order ${orderId} has been confirmed.` : "Order confirmation route."} />;
}

// =============================================================================
// Order Transfer Pages
// =============================================================================

export function MedusaB2COrderTransferPage() {
  const { navigateToHome } = useB2CRuntime();
  const location = useLocation();
  const pathParts = location.pathname.split("/");
  const orderId = pathParts[pathParts.length - 3] || "";
  const token = pathParts[pathParts.length - 1] || "";
  const acceptPath = `${location.pathname}/accept`;
  const declinePath = `${location.pathname}/decline`;
  
  return (
    <PageShell title="Order transfer" description={`Review the transfer request for order ${orderId}.`}>
      <div className="max-w-2xl space-y-4 rounded-xl border border-zinc-200 p-6">
        <p className="text-sm text-zinc-600">
          You&apos;ve received a request to transfer ownership of order <strong>{orderId}</strong>. If you accept,
          the new owner will take over future access to this order.
        </p>
        <p className="text-sm text-zinc-500">Transfer token: {token}</p>
        <div className="flex gap-3">
          <a href={acceptPath} className="rounded-lg bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800">
            Accept transfer
          </a>
          <a href={declinePath} className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50">
            Decline transfer
          </a>
          <button onClick={() => navigateToHome()} className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-50">
            Cancel
          </button>
        </div>
      </div>
    </PageShell>
  );
}

export function MedusaB2COrderTransferAcceptPage() {
  const { acceptOrderTransfer } = useB2CRuntime();
  const location = useLocation();
  const pathParts = location.pathname.split("/");
  const orderId = pathParts[pathParts.length - 4] || "";
  const token = pathParts[pathParts.length - 2] || "";
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const handleAccept = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      await acceptOrderTransfer(orderId, token);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept transfer");
      setStatus("error");
    }
  }, [acceptOrderTransfer, orderId, token]);

  return (
    <PageShell title="Accept order transfer" description="Confirm the transfer token to accept an order transfer in Medusa.">
      <div className="max-w-md space-y-6">
        {status === "success" ? (
          <div className="rounded-xl bg-green-50 p-6 text-center">
            <p className="font-medium text-green-800">Transfer accepted successfully!</p>
            <p className="mt-2 text-sm text-green-700">The order has been transferred to your account.</p>
          </div>
        ) : (
          <>
            <p className="text-sm text-zinc-600">
              You are about to accept the transfer of order <strong>#{orderId.slice(-8)}</strong> to your account.
            </p>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <div className="flex gap-3">
              <button
                onClick={handleAccept}
                disabled={status === "loading"}
                className="rounded-lg bg-zinc-950 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
              >
                {status === "loading" ? "Accepting..." : "Accept transfer"}
              </button>
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}

export function MedusaB2COrderTransferDeclinePage() {
  const { declineOrderTransfer } = useB2CRuntime();
  const location = useLocation();
  const pathParts = location.pathname.split("/");
  const orderId = pathParts[pathParts.length - 4] || "";
  const token = pathParts[pathParts.length - 2] || "";
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const handleDecline = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      await declineOrderTransfer(orderId, token);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to decline transfer");
      setStatus("error");
    }
  }, [declineOrderTransfer, orderId, token]);

  return (
    <PageShell title="Decline order transfer" description="Confirm the transfer token to decline an order transfer in Medusa.">
      <div className="max-w-md space-y-6">
        {status === "success" ? (
          <div className="rounded-xl bg-zinc-100 p-6 text-center">
            <p className="font-medium text-zinc-800">Transfer declined</p>
            <p className="mt-2 text-sm text-zinc-600">The order transfer has been declined.</p>
          </div>
        ) : (
          <>
            <p className="text-sm text-zinc-600">
              You are about to decline the transfer of order <strong>#{orderId.slice(-8)}</strong>.
            </p>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <div className="flex gap-3">
              <button
                onClick={handleDecline}
                disabled={status === "loading"}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
              >
                {status === "loading" ? "Declining..." : "Decline transfer"}
              </button>
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}

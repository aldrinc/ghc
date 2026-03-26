import { useEffect, useMemo, useState, useCallback, type ReactNode } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import type { MedusaOrder, MedusaCustomerAddress } from "@/types/commerce";
import { B2CStarterShell } from "./B2CStarterShell";
import { resolveB2CSitePath } from "./sitePath";

function PageShell({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return (
    <B2CStarterShell>
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
        <header className="space-y-2 border-b border-zinc-200 pb-4">
          <h1 className="text-3xl font-medium text-zinc-950">{title}</h1>
          {description ? <p className="max-w-2xl text-sm text-zinc-600">{description}</p> : null}
        </header>
        {children}
      </main>
    </B2CStarterShell>
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
  return useMemo(
    () => resolveB2CSitePath(location.pathname, runtime),
    [location.pathname, runtime],
  );
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

export function MedusaB2CCheckoutPage() {
  const { cart, completeCheckout, cartLoading, navigateToOrderConfirmed } = useB2CRuntime();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleComplete = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await completeCheckout();
      if (result.type === "order" && result.order) {
        navigateToOrderConfirmed(result.order.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to complete checkout.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageShell title="Checkout" description="Review the active cart and submit checkout directly to Medusa.">
      {cartLoading ? <p className="text-sm text-zinc-500">Loading checkout...</p> : null}
      <div className="rounded-xl border border-zinc-200 p-4">
        <p className="text-sm text-zinc-600">Items: {cart?.items?.length || 0}</p>
        <p className="mt-2 text-sm text-zinc-600">Total: {cart ? formatPrice(cart.total, cart.currency_code) : "—"}</p>
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <button onClick={() => void handleComplete()} disabled={submitting || !cart} className="w-fit rounded-full bg-zinc-950 px-5 py-2 text-sm font-medium text-white disabled:opacity-50">
        {submitting ? "Submitting..." : "Complete checkout"}
      </button>
    </PageShell>
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

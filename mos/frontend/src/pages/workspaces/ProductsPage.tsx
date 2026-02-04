import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle, DialogClose } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useCreateProduct, useProducts } from "@/api/products";

function parseList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProductsPage() {
  const { workspace } = useWorkspace();
  const { selectProduct } = useProductContext();
  const navigate = useNavigate();
  const { data: products = [], isLoading } = useProducts(workspace?.id);
  const createProduct = useCreateProduct();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [primaryBenefits, setPrimaryBenefits] = useState("");
  const [featureBullets, setFeatureBullets] = useState("");
  const [guaranteeText, setGuaranteeText] = useState("");
  const [disclaimers, setDisclaimers] = useState("");

  const canCreate = useMemo(() => Boolean(workspace && name.trim()), [workspace, name]);

  const resetForm = () => {
    setName("");
    setDescription("");
    setCategory("");
    setPrimaryBenefits("");
    setFeatureBullets("");
    setGuaranteeText("");
    setDisclaimers("");
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workspace) return;
    const payload = {
      clientId: workspace.id,
      name: name.trim(),
      description: description.trim() || undefined,
      category: category.trim() || undefined,
      primaryBenefits: primaryBenefits.trim() ? parseList(primaryBenefits) : undefined,
      featureBullets: featureBullets.trim() ? parseList(featureBullets) : undefined,
      guaranteeText: guaranteeText.trim() || undefined,
      disclaimers: disclaimers.trim() ? parseList(disclaimers) : undefined,
    };
    const created = await createProduct.mutateAsync(payload);
    if (created?.id) {
      selectProduct(created.id, { name: created.name, client_id: created.client_id, category: created.category });
      navigate(`/workspaces/products/${created.id}`);
    }
    resetForm();
    setIsModalOpen(false);
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Products"
        description="Create and manage products for this workspace."
        actions={
          <Button onClick={() => setIsModalOpen(true)} disabled={!workspace}>
            New product
          </Button>
        }
      />

      {!workspace ? (
        <div className="rounded-lg border border-dashed border-border bg-surface px-4 py-6 text-sm text-content-muted">
          Select a workspace to view and create products.
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-surface">
          {isLoading ? (
            <div className="px-4 py-6 text-sm text-content-muted">Loading products…</div>
          ) : (
            <Table variant="ghost">
              <TableHeader>
                <TableRow>
                  <TableHeadCell>Image</TableHeadCell>
                  <TableHeadCell>Name</TableHeadCell>
                  <TableHeadCell>Category</TableHeadCell>
                  <TableHeadCell>Benefits</TableHeadCell>
                  <TableHeadCell>Disclaimers</TableHeadCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {products.map((product) => (
                  <TableRow
                    key={product.id}
                    hover
                    className="cursor-pointer"
                    onClick={() => {
                      selectProduct(product.id, {
                        name: product.name,
                        client_id: product.client_id,
                        category: product.category,
                      });
                      navigate(`/workspaces/products/${product.id}`);
                    }}
                  >
                    <TableCell>
                      <div className="h-12 w-12 rounded-md border border-border bg-surface-2 overflow-hidden flex items-center justify-center">
                        {product.primary_asset_url ? (
                          <img
                            src={product.primary_asset_url}
                            alt={product.name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="text-[10px] font-semibold uppercase text-content-muted">No image</div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="font-semibold text-content">{product.name}</TableCell>
                    <TableCell className="text-xs text-content-muted">{product.category || "—"}</TableCell>
                    <TableCell className="text-xs text-content-muted">
                      {product.primary_benefits?.length ? product.primary_benefits.length : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-content-muted">
                      {product.disclaimers?.length ? product.disclaimers.length : "—"}
                    </TableCell>
                  </TableRow>
                ))}
                {!products.length && (
                  <TableRow>
                    <TableCell className="px-3 py-4 text-sm text-content-muted" colSpan={5}>
                      No products yet. Create one to begin.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      <DialogRoot open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent>
          <DialogTitle>New product</DialogTitle>
          <DialogDescription>Define the core product that offers will reference.</DialogDescription>
          <form className="space-y-3" onSubmit={handleCreate}>
            {workspace ? (
              <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase text-content-muted">Workspace</div>
                <div className="font-semibold text-content">{workspace.name}</div>
              </div>
            ) : null}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Name</label>
              <Input placeholder="Product name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Description</label>
              <Input placeholder="Short description" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Category</label>
              <Input placeholder="e.g. Supplements, SaaS" value={category} onChange={(e) => setCategory(e.target.value)} />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Primary benefits</label>
              <Input
                placeholder="Comma-separated list"
                value={primaryBenefits}
                onChange={(e) => setPrimaryBenefits(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Feature bullets</label>
              <Input
                placeholder="Comma-separated list"
                value={featureBullets}
                onChange={(e) => setFeatureBullets(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Guarantee text</label>
              <Input
                placeholder="Optional guarantee statement"
                value={guaranteeText}
                onChange={(e) => setGuaranteeText(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Disclaimers</label>
              <Input
                placeholder="Comma-separated list"
                value={disclaimers}
                onChange={(e) => setDisclaimers(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={!canCreate || createProduct.isPending}>
                {createProduct.isPending ? "Creating…" : "Create product"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}

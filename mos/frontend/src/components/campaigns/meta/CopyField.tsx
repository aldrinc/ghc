type CopyFieldProps = {
  label: string;
  value?: string | null;
  multiline?: boolean;
};

export function CopyField({ label, value, multiline = false }: CopyFieldProps) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">{label}</div>
      <div
        className={[
          "rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-content",
          multiline ? "whitespace-pre-wrap leading-6" : "",
        ].join(" ")}
      >
        {value || "—"}
      </div>
    </div>
  );
}

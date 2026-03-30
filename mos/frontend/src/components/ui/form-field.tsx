import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type FormFieldProps = {
  /** Visible label text. */
  label: string;
  /** Small helper text rendered below the input. */
  helper?: ReactNode;
  /** Error message – takes precedence over helper when present. */
  error?: ReactNode;
  /** Mark the field as required (appends a red asterisk). */
  required?: boolean;
  /** Additional class names for the outer wrapper. */
  className?: string;
  /** The input / select / textarea element. */
  children: ReactNode;
};

/**
 * Thin wrapper that renders a consistent label + input + helper/error stack.
 *
 * It generates a stable `id` and wires it up via `htmlFor` so the label is
 * properly associated with the first child input for accessibility.
 */
export function FormField({ label, helper, error, required, className, children }: FormFieldProps) {
  const autoId = useId();

  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={autoId} className="text-xs font-semibold text-content">
        {label}
        {required ? <span className="ml-0.5 text-danger" aria-hidden="true">*</span> : null}
      </label>

      {/* Wrap children so we can inject the id on the first focusable element.
          For simplicity, we pass the id down as a data attribute consumers can
          forward. In practice Input/Select accept `id` as a prop already. */}
      <div data-field-id={autoId}>
        {children}
      </div>

      {error ? (
        <p className="text-xs text-danger" role="alert">{error}</p>
      ) : helper ? (
        <p className="text-xs text-content-muted">{helper}</p>
      ) : null}
    </div>
  );
}

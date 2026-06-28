import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
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
  const messageId = `${autoId}-message`;
  let child = children;

  if (isValidElement(children)) {
    const element = children as ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }>;
    child = cloneElement(element, {
      id: element.props.id ?? autoId,
      "aria-describedby": error || helper ? messageId : element.props["aria-describedby"],
      "aria-invalid": Boolean(error) || element.props["aria-invalid"],
    });
  }

  return (
    <div className={cn("space-y-2.5", className)}>
      <label htmlFor={autoId} className="block text-sm font-semibold tracking-normal text-content">
        {label}
        {required ? <span className="ml-0.5 text-danger" aria-hidden="true">*</span> : null}
      </label>

      <div data-field-id={autoId}>{child}</div>

      {error ? (
        <p id={messageId} className="flex items-center gap-1.5 text-sm font-medium text-danger" role="alert">{error}</p>
      ) : helper ? (
        <p id={messageId} className="text-sm text-content-muted">{helper}</p>
      ) : null}
    </div>
  );
}

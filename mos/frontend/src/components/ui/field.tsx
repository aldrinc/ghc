import { Form } from "@base-ui/react/form";
import { Field } from "@base-ui/react/field";
import { cn } from "@/lib/utils";

export const FormRoot = Form;

export const FieldRoot = ({ className, ...props }: Field.Root.Props) => (
  <Field.Root {...props} className={cn("flex flex-col gap-1 text-sm text-content", className)} />
);

export const FieldLabel = ({ className, ...props }: Field.Label.Props) => (
  <Field.Label {...props} className={cn("text-content font-medium", className)} />
);

export const FieldDescription = ({ className, ...props }: Field.Description.Props) => (
  <Field.Description {...props} className={cn("text-xs text-content-muted", className)} />
);

export const FieldError = ({ className, ...props }: Field.Error.Props) => (
  <Field.Error {...props} className={cn("text-xs text-danger", className)} />
);

export const FieldControl = Field.Control;

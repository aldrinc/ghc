import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Table = forwardRef<HTMLTableElement, HTMLAttributes<HTMLTableElement>>(function Table(
  { className, ...props },
  ref
) {
  return (
    <table
      ref={ref}
      className={cn(
        "w-full border-collapse rounded-lg border border-border bg-surface text-sm text-content shadow-sm",
        className
      )}
      {...props}
    />
  );
});

export const TableHeader = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  function TableHeader({ className, ...props }, ref) {
    return (
      <thead
        ref={ref}
        className={cn(
          "bg-surface-2 text-left text-xs uppercase tracking-wide text-content-muted border-b border-border",
          className
        )}
        {...props}
      />
    );
  }
);

export const TableBody = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  function TableBody({ className, ...props }, ref) {
    return <tbody ref={ref} className={cn("divide-y divide-border bg-white", className)} {...props} />;
  }
);

export const TableRow = forwardRef<HTMLTableRowElement, HTMLAttributes<HTMLTableRowElement> & { hover?: boolean }>(
  function TableRow({ className, hover = false, ...props }, ref) {
    return (
      <tr
        ref={ref}
        className={cn(
          hover && "hover:bg-surface-2 transition-colors",
          "border-border/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
          className
        )}
        {...props}
      />
    );
  }
);

export const TableHeadCell = forwardRef<HTMLTableCellElement, HTMLAttributes<HTMLTableCellElement>>(function TableHeadCell(
  { className, ...props },
  ref
) {
  return <th ref={ref} className={cn("px-3 py-2 font-semibold", className)} {...props} />;
});

export const TableCell = forwardRef<HTMLTableCellElement, HTMLAttributes<HTMLTableCellElement>>(function TableCell(
  { className, ...props },
  ref
) {
  return <td ref={ref} className={cn("px-3 py-2 align-middle", className)} {...props} />;
});

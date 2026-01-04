import {
  forwardRef,
  useContext,
  createContext,
  type CSSProperties,
  type HTMLAttributes,
  type TableHTMLAttributes,
  type ThHTMLAttributes,
  type TdHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

type TableVariant = "surface" | "ghost";
type TableSize = 1 | 2 | 3;
type TableLayout = "auto" | "fixed";

type TableContextValue = {
  size: TableSize;
  variant: TableVariant;
};

const TableContext = createContext<TableContextValue>({ size: 2, variant: "ghost" });

const useTableContext = () => useContext(TableContext);

const cellPadding: Record<TableSize, string> = {
  1: "px-3 py-2",
  2: "px-4 py-2.5",
  3: "px-4 py-3",
};

const cellText: Record<TableSize, string> = {
  1: "text-xs",
  2: "text-sm",
  3: "text-sm",
};

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  variant?: TableVariant;
  size?: TableSize;
  layout?: TableLayout;
  containerClassName?: string;
  containerStyle?: CSSProperties;
}

export const Table = forwardRef<HTMLTableElement, TableProps>(function Table(
  {
    className,
    containerClassName,
    containerStyle,
    variant = "ghost",
    size = 2,
    layout = "auto",
    children,
    ...props
  },
  ref
) {
  const containerStyles = {
    ...(variant === "surface" ? { boxShadow: "var(--shadow-1)" } : {}),
    ...containerStyle,
  };

  return (
    <div
      className={cn(
        "w-full overflow-auto rounded-xl",
        variant === "surface"
          ? "border border-border bg-[color:var(--panel)]"
          : "bg-transparent",
        containerClassName
      )}
      style={containerStyles}
    >
      <TableContext.Provider value={{ size, variant }}>
        <table
          ref={ref}
          data-size={size}
          data-variant={variant}
          data-layout={layout}
          className={cn(
            "w-full border-collapse text-sm text-content",
            layout === "fixed" ? "table-fixed" : "table-auto",
            className
          )}
          {...props}
        >
          {children}
        </table>
      </TableContext.Provider>
    </div>
  );
});

export const TableHeader = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  function TableHeader({ className, children, ...props }, ref) {
    return (
      <thead
        ref={ref}
        className={cn(
          "bg-surface-2/60 text-left text-[12px] font-medium text-content-muted border-b border-divider",
          className
        )}
        {...props}
      >
        {children}
      </thead>
    );
  }
);

export const TableBody = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  function TableBody({ className, children, ...props }, ref) {
    const { variant } = useTableContext();
    return (
      <tbody
        ref={ref}
        className={cn(
          "divide-y divide-divider",
          variant === "surface" ? "bg-[color:var(--panel)]" : "bg-transparent",
          className
        )}
        {...props}
      >
        {children}
      </tbody>
    );
  }
);

export const TableRow = forwardRef<HTMLTableRowElement, HTMLAttributes<HTMLTableRowElement> & { hover?: boolean }>(
  function TableRow({ className, hover = true, children, ...props }, ref) {
    return (
      <tr
        ref={ref}
        className={cn(
          "outline-none focus-visible:bg-surface-2/50",
          hover && "hover:bg-surface-2/40 transition-colors",
          className
        )}
        {...props}
      >
        {children}
      </tr>
    );
  }
);

export const TableHeadCell = forwardRef<HTMLTableCellElement, ThHTMLAttributes<HTMLTableCellElement>>(
  function TableHeadCell({ className, children, ...props }, ref) {
    const { size } = useTableContext();
    return (
      <th
        ref={ref}
        className={cn(
          "text-left align-middle font-semibold text-content-muted",
          cellPadding[size],
          cellText[size],
          className
        )}
        {...props}
      >
        {children}
      </th>
    );
  }
);

export const TableCell = forwardRef<HTMLTableCellElement, TdHTMLAttributes<HTMLTableCellElement>>(
  function TableCell({ className, children, ...props }, ref) {
    const { size } = useTableContext();
    return (
      <td
        ref={ref}
        className={cn(
          "align-middle tabular-nums",
          cellPadding[size],
          cellText[size],
          className
        )}
        {...props}
      >
        {children}
      </td>
    );
  }
);

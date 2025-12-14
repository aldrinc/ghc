import { PropsWithChildren } from "react";
import { UserButton } from "@clerk/clerk-react";
import { useLocation } from "react-router-dom";
import { appRoutes } from "@/app/routes";

type HeaderProps = PropsWithChildren<{
  title?: string;
  description?: string;
}>;

export function Header({ title, description, children }: HeaderProps) {
  const location = useLocation();
  const derivedTitle =
    title ||
    appRoutes.find((route) => location.pathname.startsWith(route.path))?.label ||
    "GHC Platform";

  return (
    <header className="flex items-center justify-between border-b border-border bg-white px-6 py-4 shadow-sm">
      <div>
        <h1 className="text-lg font-semibold text-content">{derivedTitle}</h1>
        {description ? <p className="text-sm text-content-muted">{description}</p> : null}
      </div>
      <div className="flex items-center gap-3">
        {children}
        <UserButton />
      </div>
    </header>
  );
}

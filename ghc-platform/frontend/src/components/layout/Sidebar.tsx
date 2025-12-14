import { NavLink } from "react-router-dom";
import { appRoutes } from "@/app/routes";

export function Sidebar() {
  return (
    <aside className="w-64 flex-shrink-0 border-r border-border bg-white shadow-sm">
      <div className="px-4 py-3 border-b border-border">
        <div className="text-sm font-semibold text-content">GHC Platform</div>
        <div className="text-xs text-content-muted">Operations Console</div>
      </div>
      <nav className="p-2 space-y-1">
        {appRoutes.map((route) => (
          <NavLink
            key={route.path}
            to={route.path}
            className={({ isActive }) =>
              [
                "flex items-center gap-2 rounded px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent text-accent-contrast shadow-sm"
                  : "text-content-muted hover:bg-surface-2 hover:text-content",
              ].join(" ")
            }
          >
            <span>{route.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

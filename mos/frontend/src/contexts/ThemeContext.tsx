import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark";

type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
};

const STORAGE_KEY = "mos_theme";

function parseTheme(raw: string | null | undefined): ThemeMode | null {
  return raw === "light" || raw === "dark" ? raw : null;
}

function readThemeFromDocument(): ThemeMode | null {
  if (typeof document === "undefined") return null;
  return parseTheme(document.documentElement.getAttribute("data-theme"));
}

function applyThemeToDocument(theme: ThemeMode) {
  document.documentElement.setAttribute("data-theme", theme);
}

function loadThemeFromStorage(): ThemeMode | null {
  if (typeof window === "undefined") return null;
  return parseTheme(localStorage.getItem(STORAGE_KEY));
}

function saveThemeToStorage(theme: ThemeMode) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Ignore write errors (e.g. blocked storage); theme still applies for this session.
  }
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Prefer stored user intent, then fall back to whatever is already on the document,
  // then default to light.
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const fromStorage = loadThemeFromStorage();
    if (fromStorage) return fromStorage;
    const fromDocument = readThemeFromDocument();
    return fromDocument ?? "light";
  });

  useEffect(() => {
    applyThemeToDocument(theme);
    saveThemeToStorage(theme);
  }, [theme]);

  const setTheme = useCallback((next: ThemeMode) => {
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "nifty-agent:theme";

/** Canvas colour per theme, mirrored from `globals.css` for `<meta name="theme-color">`. */
export const THEME_CANVAS: Record<Theme, string> = {
  light: "#F9EDE3",
  dark: "#1D1D1D",
};

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark";
}

/** Applies the theme to `<html>`. The single place the `.dark` class is written. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

/**
 * Runs before first paint to prevent a light-theme flash on a dark-theme load.
 * Kept as a string so it can be inlined in <head> ahead of hydration; it must
 * stay dependency-free and never throw in private-browsing mode.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");var d=s==="dark"||(s!=="light"&&window.matchMedia("(prefers-color-scheme: dark)").matches);var r=document.documentElement;r.classList.toggle("dark",d);r.style.colorScheme=d?"dark":"light";}catch(e){}})();`;

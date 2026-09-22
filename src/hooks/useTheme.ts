"use client";

import { useCallback, useSyncExternalStore } from "react";

import {
  THEME_STORAGE_KEY,
  applyTheme,
  isTheme,
  type Theme,
} from "@/lib/theme";

type Listener = () => void;

const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  // Other tabs of the dashboard, and the OS preference itself, stay in sync.
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener("storage", listener);
  media.addEventListener("change", listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
    media.removeEventListener("change", listener);
  };
}

function getSnapshot(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (isTheme(stored)) return stored;
  } catch {
    // Storage can be unavailable in private browsing — fall through to the OS.
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function getServerSnapshot(): Theme {
  // The pre-paint script in <head> has already set the real class on <html>;
  // this only needs to match the server-rendered markup.
  return "light";
}

export interface UseThemeResult {
  theme: Theme;
  setTheme: (next: Theme) => void;
  toggleTheme: () => void;
}

/**
 * Active colour theme, persisted to localStorage and defaulting to the OS
 * preference. `useSyncExternalStore` keeps hydration clean without an effect.
 */
export function useTheme(): UseThemeResult {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setTheme = useCallback((next: Theme): void => {
    applyTheme(next);

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // A failed write only costs persistence, not the current session.
    }

    notify();
  }, []);

  const toggleTheme = useCallback((): void => {
    setTheme(getSnapshot() === "dark" ? "light" : "dark");
  }, [setTheme]);

  return { theme, setTheme, toggleTheme };
}

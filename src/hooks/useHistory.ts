// useHistory<T>() — a document-editor-style undo/redo stack for the
// Quotation Builder. One snapshot per meaningful mutation, with optional
// coalescing so a burst of related updates (e.g. typing into an input)
// collapses into a single history entry.
//
// Design goals
//   * Everything the user changes goes through `apply(mut)` — no separate
//     setters — so undo/redo can never miss a mutation.
//   * `coalesceKey` merges adjacent edits with the same key inside a short
//     window (default 800ms). Ideal for text inputs, number steppers,
//     discount sliders.
//   * Bounded stack (default 200 entries) — prevents unbounded memory in
//     long sessions.
//   * `replace(next)` hydrates state without touching the history (used
//     when the initial customer id / recent list resolves).
import { useCallback, useEffect, useRef, useState } from "react";

type ApplyOptions = { coalesceKey?: string; skipHistory?: boolean };

export type HistoryApi<T> = {
  state: T;
  apply: (mutator: (s: T) => T, opts?: ApplyOptions) => void;
  replace: (next: T) => void; // hydration, no history entry
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  reset: () => void;
  pastSize: number;
};

export function useHistory<T>(initial: T, opts: { max?: number; coalesceMs?: number } = {}): HistoryApi<T> {
  const max = opts.max ?? 200;
  const coalesceMs = opts.coalesceMs ?? 800;

  const [present, setPresent] = useState<T>(initial);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);
  const coalesceRef = useRef<{ key: string; ts: number } | null>(null);
  const [, force] = useState(0);
  const rerender = () => force((n) => (n + 1) % 1000000);

  const apply = useCallback(
    (mutator: (s: T) => T, options?: ApplyOptions) => {
      setPresent((prev) => {
        const next = mutator(prev);
        if (Object.is(next, prev)) return prev;
        if (options?.skipHistory) {
          coalesceRef.current = null;
          return next;
        }
        const now = Date.now();
        const co = coalesceRef.current;
        const shouldCoalesce =
          !!options?.coalesceKey && !!co && co.key === options.coalesceKey && now - co.ts < coalesceMs;
        if (!shouldCoalesce) {
          pastRef.current = pastRef.current.length >= max
            ? [...pastRef.current.slice(1), prev]
            : [...pastRef.current, prev];
        }
        coalesceRef.current = options?.coalesceKey ? { key: options.coalesceKey, ts: now } : null;
        futureRef.current = [];
        rerender();
        return next;
      });
    },
    [max, coalesceMs],
  );

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return;
    const prev = pastRef.current[pastRef.current.length - 1];
    pastRef.current = pastRef.current.slice(0, -1);
    setPresent((cur) => {
      futureRef.current = [cur, ...futureRef.current];
      return prev;
    });
    coalesceRef.current = null;
    rerender();
  }, []);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    const next = futureRef.current[0];
    futureRef.current = futureRef.current.slice(1);
    setPresent((cur) => {
      pastRef.current = pastRef.current.length >= max
        ? [...pastRef.current.slice(1), cur]
        : [...pastRef.current, cur];
      return next;
    });
    coalesceRef.current = null;
    rerender();
  }, [max]);

  const replace = useCallback((next: T) => {
    // No history entry; used during initial hydration.
    coalesceRef.current = null;
    setPresent(next);
  }, []);

  const reset = useCallback(() => {
    pastRef.current = [];
    futureRef.current = [];
    coalesceRef.current = null;
    setPresent(initial);
    rerender();
  }, [initial]);

  return {
    state: present,
    apply,
    replace,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
    reset,
    pastSize: pastRef.current.length,
  };
}

// Web-only keyboard shortcut wiring. Silently no-ops on native.
export function useUndoRedoShortcuts(api: HistoryApi<unknown>, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined" || typeof document === "undefined") return;
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      const key = e.key.toLowerCase();
      const target = e.target as HTMLElement | null;
      // If focus is inside a text input, only intercept if user really wants document undo.
      const isTextField = !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (isTextField && !e.shiftKey && key === "z") return; // let the field handle its own undo
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        api.undo();
      } else if ((key === "z" && e.shiftKey) || key === "y") {
        e.preventDefault();
        api.redo();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [api, enabled]);
}

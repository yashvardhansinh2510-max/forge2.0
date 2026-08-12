// Production error monitoring. Sentry stays opt-in so preview and local builds
// do not emit telemetry; product analytics is intentionally not bundled.
export function isSentryEnabled(): boolean {
  return !!(process.env.EXPO_PUBLIC_SENTRY_DSN || "").trim();
}

/** Call once at app startup. Monitoring must never block the application. */
export function initSentry(): void {
  const dsn = (process.env.EXPO_PUBLIC_SENTRY_DSN || "").trim();
  if (!dsn) return;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Sentry = require("@sentry/react-native");
    Sentry.init({
      dsn,
      environment: process.env.EXPO_PUBLIC_SENTRY_ENVIRONMENT || "production",
      tracesSampleRate: 0,
    });
  } catch (e) {
    console.warn("[monitoring] Sentry configured but failed to initialize:", e);
  }
}

/**
 * Development-only browser performance signals. These stay local (no product
 * analytics) but make route audits evidence-based: long tasks and navigation
 * timing are visible in the console without blocking the app.
 */
export function initPerformanceSignals(): void {
  if (!__DEV__ || typeof window === "undefined") return;
  try {
    const perf = window.performance;
    window.addEventListener("load", () => {
      const navigation = perf.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
      if (navigation) {
        console.info("[perf] app navigation", {
          domContentLoaded: Math.round(navigation.domContentLoadedEventEnd),
          load: Math.round(navigation.loadEventEnd),
        });
      }
    }, { once: true });
    const Observer = (window as any).PerformanceObserver;
    if (Observer && Observer.supportedEntryTypes?.includes("longtask")) {
      const observer = new Observer((list: PerformanceObserverEntryList) => {
        for (const entry of list.getEntries()) {
          if (entry.duration >= 50) console.warn("[perf] long task", Math.round(entry.duration), "ms");
        }
      });
      observer.observe({ entryTypes: ["longtask"] });
    }
  } catch {
    // Performance diagnostics must never affect application startup.
  }
}

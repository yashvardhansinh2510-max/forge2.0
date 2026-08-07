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

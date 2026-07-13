// Production monitoring — Sentry (crash/error reporting) + PostHog (product
// analytics), both fully gated behind EXPO_PUBLIC_* env vars. Mirrors the
// backend's services/monitoring.py: a complete no-op until credentials are
// supplied, so this addition changes nothing about today's runtime behavior.
//
// Required env vars to activate (see frontend/.env.example + PRODUCTION.md):
//   EXPO_PUBLIC_SENTRY_DSN          — enables crash/error reporting when set
//   EXPO_PUBLIC_SENTRY_ENVIRONMENT  — optional, defaults to "production"
//   EXPO_PUBLIC_POSTHOG_API_KEY     — enables analytics when set
//   EXPO_PUBLIC_POSTHOG_HOST        — optional, defaults to PostHog Cloud US
//
// Deliberately minimal: no screen-autocapture/session-replay wiring yet (that
// requires real credentials to validate against) — just safe initialization
// plus a `capture()` helper other screens can call once analytics matters.
import { useEffect, useState } from "react";

let posthogClientPromise: Promise<any> | null = null;

export function isSentryEnabled(): boolean {
  return !!(process.env.EXPO_PUBLIC_SENTRY_DSN || "").trim();
}

export function isPostHogEnabled(): boolean {
  return !!(process.env.EXPO_PUBLIC_POSTHOG_API_KEY || "").trim();
}

/** Call once, at app startup (see app/_layout.tsx). Never throws. */
export function initSentry(): void {
  const dsn = (process.env.EXPO_PUBLIC_SENTRY_DSN || "").trim();
  if (!dsn) return; // safe no-op — matches backend behavior when SENTRY_DSN is unset
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

/** Lazily constructs a PostHog client on first use — returns null (no-op)
 * when EXPO_PUBLIC_POSTHOG_API_KEY is unset. Never throws. */
async function getPostHogClient(): Promise<any | null> {
  if (!isPostHogEnabled()) return null;
  if (!posthogClientPromise) {
    posthogClientPromise = (async () => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { default: PostHog } = require("posthog-react-native");
        return new PostHog(process.env.EXPO_PUBLIC_POSTHOG_API_KEY as string, {
          host: process.env.EXPO_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
        });
      } catch (e) {
        console.warn("[monitoring] PostHog configured but failed to initialize:", e);
        return null;
      }
    })();
  }
  return posthogClientPromise;
}

/** Best-effort analytics event — no-op when PostHog is disabled, never throws. */
export async function captureEvent(event: string, properties?: Record<string, any>): Promise<void> {
  const client = await getPostHogClient();
  if (!client) return;
  try {
    client.capture(event, properties);
  } catch {
    // analytics must never break the app
  }
}

/** Optional hook for screens that want to fire a one-time "viewed" event
 * without wiring full autocapture — entirely opt-in per screen. */
export function useCaptureOnMount(event: string, properties?: Record<string, any>): void {
  const [fired, setFired] = useState(false);
  useEffect(() => {
    if (fired) return;
    setFired(true);
    captureEvent(event, properties);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

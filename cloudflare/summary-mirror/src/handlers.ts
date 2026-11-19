import {
  MAX_BODY_BYTES,
  SERVICE_NAME,
  activeAt,
  parseTimestamp,
  validateSnapshot,
  type SummaryBody,
} from "./contract";
import type { D1Database, Store } from "./store";

export interface Env {
  DB: D1Database;
  /** Same value as the notifier's DASHBOARD_API_KEY — read with X-API-Key. */
  DASHBOARD_API_KEY?: string;
  /** Same value as the notifier's SUMMARY_MIRROR_TOKEN — the only write credential. */
  INGEST_TOKEN?: string;
  /** Optional Discord webhook for the freshness alert. */
  DISCORD_WEBHOOK_URL?: string;
  /** Hours without a completed check before alerting. Default 26. */
  STALE_AFTER_HOURS?: string;
}

export interface Deps {
  store: Store;
  env: Env;
  now: () => number;
  fetchImpl?: typeof fetch;
}

export const SUMMARY_PATH = "/api/summary";
export const SNAPSHOT_PATH = "/api/summary/snapshot";
const DEFAULT_STALE_AFTER_HOURS = 26;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-summary-source": "cloudflare-mirror" },
  });
}

// Same {"detail": ...} error shape FastAPI uses on the Python service.
function detail(status: number, message: string): Response {
  return json(status, { detail: message });
}

/** Constant-time string comparison; an unset/empty secret never matches (fail-closed). */
export function secretMatches(provided: string | null, secret: string | undefined): boolean {
  if (!secret || provided === null) return false;
  const a = new TextEncoder().encode(provided);
  const b = new TextEncoder().encode(secret);
  let diff = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let i = 0; i < length; i++) diff |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return diff === 0;
}

function bearerToken(request: Request): string | null {
  const header = request.headers.get("authorization");
  const token = header?.match(/^Bearer\s+(.+)$/i)?.[1]?.trim();
  return token || null;
}

export async function handleRequest(request: Request, deps: Deps): Promise<Response> {
  const path = new URL(request.url).pathname.replace(/\/+$/, "");

  if (path === SUMMARY_PATH) {
    if (request.method !== "GET") return detail(405, "Method Not Allowed");
    return getSummary(request, deps);
  }
  if (path === SNAPSHOT_PATH) {
    if (request.method !== "POST") return detail(405, "Method Not Allowed");
    return ingestSnapshot(request, deps);
  }
  return detail(404, "Not Found");
}

async function getSummary(request: Request, { store, env, now }: Deps): Promise<Response> {
  if (!secretMatches(request.headers.get("x-api-key"), env.DASHBOARD_API_KEY)) {
    return detail(401, "Invalid or missing API key");
  }

  let state;
  try {
    state = await store.get();
  } catch (error) {
    console.error("summary read failed:", error instanceof Error ? error.name : "unknown");
    return detail(503, "Storage backend unavailable");
  }

  const body: SummaryBody = {
    service: SERVICE_NAME,
    // Re-filtered on every request: the host may not push for days.
    active_promotions: activeAt(state?.promotions ?? [], now()),
    last_check_at: state?.lastCheckAt ?? null,
  };
  return json(200, body);
}

async function ingestSnapshot(request: Request, { store, env, now }: Deps): Promise<Response> {
  if (!secretMatches(bearerToken(request), env.INGEST_TOKEN)) {
    return detail(401, "Invalid or missing bearer token");
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (declaredLength > MAX_BODY_BYTES) return detail(413, "Snapshot too large");
  const raw = await request.text();
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) return detail(413, "Snapshot too large");

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return detail(400, "Body must be valid JSON");
  }

  const result = validateSnapshot(parsed);
  if (!result.ok) return detail(400, result.error);

  try {
    await store.saveSnapshot(
      result.value.promotions,
      result.value.lastCheckAt,
      new Date(now()).toISOString(),
    );
  } catch (error) {
    console.error("snapshot write failed:", error instanceof Error ? error.name : "unknown");
    return detail(503, "Storage backend unavailable");
  }

  console.log(`stored snapshot with ${result.value.promotions.length} promotion(s)`);
  return new Response(null, { status: 204 });
}

export type FreshnessOutcome =
  | "no-snapshot"
  | "fresh"
  | "already-alerted"
  | "alert-disabled"
  | "alerted"
  | "alert-failed";

export function staleAfterHours(env: Env): number {
  const parsed = Number(env.STALE_AFTER_HOURS);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_STALE_AFTER_HOURS;
}

/**
 * Cron Trigger body: alert Discord once per stale episode when no check has
 * completed for STALE_AFTER_HOURS. The next successful push re-arms it.
 * A failed Discord call is retried on the next cron run.
 */
export async function checkFreshness({ store, env, now, fetchImpl = fetch }: Deps): Promise<FreshnessOutcome> {
  const state = await store.get();
  if (!state) return "no-snapshot";

  const lastCheckMs = state.lastCheckAt ? parseTimestamp(state.lastCheckAt) : NaN;
  const referenceMs = Number.isNaN(lastCheckMs) ? parseTimestamp(state.receivedAt) : lastCheckMs;
  const thresholdHours = staleAfterHours(env);
  const ageHours = (now() - referenceMs) / 3_600_000;
  if (ageHours <= thresholdHours) return "fresh";
  if (state.staleAlertSentAt) return "already-alerted";

  if (!env.DISCORD_WEBHOOK_URL) {
    console.warn(`summary is stale (${ageHours.toFixed(1)}h) but DISCORD_WEBHOOK_URL is not set`);
    return "alert-disabled";
  }

  const message =
    `⚠️ **${SERVICE_NAME}**: no completed check in ${Math.floor(ageHours)}h ` +
    `(last: ${state.lastCheckAt ?? "unknown"}, threshold: ${thresholdHours}h). ` +
    "The host may be off or the check failing. `/api/summary` keeps serving the last " +
    "snapshot, with expired promotions filtered out.";

  try {
    const response = await fetchImpl(env.DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: message, allowed_mentions: { parse: [] } }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) {
      console.warn(`freshness alert rejected by Discord: HTTP ${response.status}`);
      return "alert-failed";
    }
  } catch (error) {
    console.warn("freshness alert failed:", error instanceof Error ? error.name : "unknown");
    return "alert-failed";
  }

  await store.markStaleAlertSent(new Date(now()).toISOString());
  return "alerted";
}

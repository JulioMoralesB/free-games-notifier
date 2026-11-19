import {
  MAX_GAMES_BYTES,
  MAX_SUMMARY_BYTES,
  SERVICE_NAME,
  activeAt,
  parseHistoryQuery,
  parseTimestamp,
  validateGamesChunk,
  validateSnapshot,
  type SummaryBody,
} from "./contract";
import type { D1Database, Store } from "./store";

export interface Env {
  DB: D1Database;
  /** Same value as the notifier's DASHBOARD_API_KEY — read with X-API-Key. */
  DASHBOARD_API_KEY?: string;
  /** Same value as the notifier's MIRROR_TOKEN — the only write credential. */
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

// Read endpoints: same paths as the Python service.
export const SUMMARY_PATH = "/api/summary";
export const HISTORY_PATH = "/games/history";
// Write endpoints: only the notifier, with INGEST_TOKEN.
export const INGEST_SUMMARY_PATH = "/api/mirror/summary";
export const INGEST_GAMES_PATH = "/api/mirror/games";
// The dashboard itself (/dashboard/*) is served as static assets, before this
// Worker runs — see "assets" in wrangler.example.jsonc.

const DEFAULT_STALE_AFTER_HOURS = 26;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-served-by": "free-games-mirror" },
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
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "");

  switch (path) {
    case SUMMARY_PATH:
      return request.method === "GET" ? getSummary(request, deps) : detail(405, "Method Not Allowed");
    case HISTORY_PATH:
      return request.method === "GET" ? getHistory(url, deps) : detail(405, "Method Not Allowed");
    case INGEST_SUMMARY_PATH:
      return request.method === "POST" ? ingestSummary(request, deps) : detail(405, "Method Not Allowed");
    case INGEST_GAMES_PATH:
      return request.method === "POST" ? ingestGames(request, deps) : detail(405, "Method Not Allowed");
    default:
      return detail(404, "Not Found");
  }
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

// Public, like the Python endpoint the dashboard calls. Status is computed
// against the current time on every request, so it stays right between pushes.
async function getHistory(url: URL, { store, now }: Deps): Promise<Response> {
  const query = parseHistoryQuery(url.searchParams);
  if (!query.ok) return detail(422, query.error);

  try {
    const page = await store.history(query.value, now());
    return json(200, {
      games: page.games,
      total: page.total,
      limit: query.value.limit,
      offset: query.value.offset,
    });
  } catch (error) {
    console.error("history read failed:", error instanceof Error ? error.name : "unknown");
    return detail(500, "Failed to load game history");
  }
}

/** Authenticate, size-check and JSON-parse an ingest body; a Response means reject. */
async function readIngestBody(request: Request, env: Env, maxBytes: number): Promise<unknown | Response> {
  if (!secretMatches(bearerToken(request), env.INGEST_TOKEN)) {
    return detail(401, "Invalid or missing bearer token");
  }
  if (Number(request.headers.get("content-length") ?? "0") > maxBytes) {
    return detail(413, "Payload too large");
  }
  const raw = await request.text();
  if (new TextEncoder().encode(raw).length > maxBytes) return detail(413, "Payload too large");
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return detail(400, "Body must be valid JSON");
  }
}

async function ingestSummary(request: Request, { store, env, now }: Deps): Promise<Response> {
  const body = await readIngestBody(request, env, MAX_SUMMARY_BYTES);
  if (body instanceof Response) return body;

  const result = validateSnapshot(body);
  if (!result.ok) return detail(400, result.error);

  try {
    await store.saveSnapshot(result.value.promotions, result.value.lastCheckAt, new Date(now()).toISOString());
  } catch (error) {
    console.error("summary write failed:", error instanceof Error ? error.name : "unknown");
    return detail(503, "Storage backend unavailable");
  }
  console.log(`stored summary with ${result.value.promotions.length} promotion(s)`);
  return new Response(null, { status: 204 });
}

async function ingestGames(request: Request, { store, env }: Deps): Promise<Response> {
  const body = await readIngestBody(request, env, MAX_GAMES_BYTES);
  if (body instanceof Response) return body;

  const result = validateGamesChunk(body);
  if (!result.ok) return detail(400, result.error);
  const { syncId, final, games, skipped } = result.value;

  try {
    await store.syncGames(syncId, games, final);
  } catch (error) {
    console.error("games write failed:", error instanceof Error ? error.name : "unknown");
    return detail(503, "Storage backend unavailable");
  }
  console.log(`stored ${games.length} game(s), skipped ${skipped}${final ? " (final chunk)" : ""}`);
  return json(200, { stored: games.length, skipped, final });
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
    console.warn(`mirror is stale (${ageHours.toFixed(1)}h) but DISCORD_WEBHOOK_URL is not set`);
    return "alert-disabled";
  }

  const message =
    `⚠️ **${SERVICE_NAME}**: no completed check in ${Math.floor(ageHours)}h ` +
    `(last: ${state.lastCheckAt ?? "unknown"}, threshold: ${thresholdHours}h). ` +
    "The host may be off or the check failing. The dashboard and `/api/summary` keep " +
    "serving the last snapshot, with promotion status computed live.";

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

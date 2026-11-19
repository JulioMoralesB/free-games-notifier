// Contracts mirrored from the Python service. Keep in lockstep with:
// - GET /api/summary   → docs/api.md#dashboard-summary-contract (additive-only)
// - GET /games/history → api/routes/games.py, pinned by test/fixtures/history-parity.json

export const SERVICE_NAME = "free-games-notifier";

// ─── Timestamps ───────────────────────────────────────────────────────────────

const ISO_8601 =
  /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?))?([zZ]|[+-]\d{2}:?\d{2})?$/;

/**
 * Parse an ISO-8601 timestamp to epoch ms, or NaN — mirroring Python's
 * `datetime.fromisoformat`: ISO forms only (unlike Date.parse, which also
 * accepts "March 7, 2026"), and no zone designator means UTC, never the
 * runtime's local time.
 */
export function parseTimestamp(value: string): number {
  const match = ISO_8601.exec(value.trim());
  if (!match) return NaN;
  const [, date, time = "00:00:00", zone] = match;
  const offset = !zone || zone === "z" ? "Z" : zone;
  return Date.parse(`${date}T${time}${offset}`);
}

// ─── /api/summary ─────────────────────────────────────────────────────────────

export interface Promotion {
  title: string;
  link: string;
  store: string;
  end_date: string;
}

export interface SummaryBody {
  service: string;
  active_promotions: Promotion[];
  last_check_at: string | null;
}

export const MAX_PROMOTIONS = 500;
export const MAX_FIELD_LENGTH = 2048;
export const MAX_SUMMARY_BYTES = 256 * 1024;

/**
 * Promotions still running at `nowMs`, soonest-ending first.
 * Applied on every read, so a stale snapshot never lists an ended promotion.
 * Inclusive bound, like the Python `is_still_active`; an unparseable
 * end_date is dropped, since the mirror cannot tell whether it is still free.
 */
export function activeAt(promotions: Promotion[], nowMs: number): Promotion[] {
  return promotions
    .map((p) => ({ p, endsAt: parseTimestamp(p.end_date) }))
    .filter(({ endsAt }) => !Number.isNaN(endsAt) && endsAt >= nowMs)
    .sort((a, b) => a.endsAt - b.endsAt)
    .map(({ p }) => p);
}

export interface ValidSnapshot {
  promotions: Promotion[];
  lastCheckAt: string;
}

export type Validation<T> = { ok: true; value: T } | { ok: false; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "" && value.length <= MAX_FIELD_LENGTH;
}

/** Validate a summary ingest body: the same JSON the Python /api/summary serves. */
export function validateSnapshot(body: unknown): Validation<ValidSnapshot> {
  if (!isRecord(body)) return { ok: false, error: "Body must be a JSON object" };

  if (body.service !== undefined && body.service !== SERVICE_NAME) {
    return { ok: false, error: `service must be "${SERVICE_NAME}"` };
  }

  const lastCheckAt = body.last_check_at;
  if (!boundedString(lastCheckAt) || Number.isNaN(parseTimestamp(lastCheckAt))) {
    return { ok: false, error: "last_check_at must be an ISO-8601 timestamp" };
  }

  const list = body.active_promotions;
  if (!Array.isArray(list)) return { ok: false, error: "active_promotions must be an array" };
  if (list.length > MAX_PROMOTIONS) {
    return { ok: false, error: `active_promotions exceeds ${MAX_PROMOTIONS} items` };
  }

  const promotions: Promotion[] = [];
  for (const [index, item] of list.entries()) {
    if (!isRecord(item)) return { ok: false, error: `active_promotions[${index}] must be an object` };
    const { title, link, store, end_date } = item;
    if (!boundedString(title) || !boundedString(link) || !boundedString(store) || !boundedString(end_date)) {
      return {
        ok: false,
        error: `active_promotions[${index}] needs non-empty string title, link, store and end_date`,
      };
    }
    if (!/^https?:\/\//i.test(link)) {
      return { ok: false, error: `active_promotions[${index}].link must be an http(s) URL` };
    }
    promotions.push({ title, link, store, end_date });
  }

  return { ok: true, value: { promotions, lastCheckAt } };
}

// ─── /games/history ───────────────────────────────────────────────────────────

/** The GameItem DTO (api/schemas.py) — stored and served verbatim. */
export interface GameItem {
  title: string;
  store: string;
  link: string;
  end_date: string;
  description: string;
  thumbnail: string;
  game_type: string;
  original_price: string | null;
  review_scores: string[];
}

export const MAX_GAMES_PER_CHUNK = 200;
export const MAX_GAMES_BYTES = 1024 * 1024;
const MAX_ITEM_FIELD_LENGTH = 100_000;
const SYNC_ID = /^[A-Za-z0-9_-]{1,64}$/;

function itemString(value: unknown): value is string {
  return typeof value === "string" && value.length <= MAX_ITEM_FIELD_LENGTH;
}

/** A valid GameItem with only the contract fields, or null to skip it. */
export function normalizeGameItem(value: unknown): GameItem | null {
  if (!isRecord(value)) return null;
  const { title, store, link, end_date, description, thumbnail, game_type, original_price, review_scores } = value;
  if (
    !itemString(title) || !itemString(store) || !itemString(link) || link.trim() === "" ||
    !itemString(end_date) || !itemString(description) || !itemString(thumbnail) || !itemString(game_type) ||
    !(original_price === null || itemString(original_price)) ||
    !Array.isArray(review_scores) || !review_scores.every(itemString)
  ) {
    return null;
  }
  return {
    title, store, link, end_date, description, thumbnail, game_type,
    original_price: original_price as string | null,
    review_scores: review_scores as string[],
  };
}

export interface GamesChunk {
  syncId: string;
  final: boolean;
  games: GameItem[];
  skipped: number;
}

/** Validate a history sync chunk. Structural errors reject it; bad items are skipped. */
export function validateGamesChunk(body: unknown): Validation<GamesChunk> {
  if (!isRecord(body)) return { ok: false, error: "Body must be a JSON object" };
  const { sync_id, final, games } = body;
  if (typeof sync_id !== "string" || !SYNC_ID.test(sync_id)) {
    return { ok: false, error: "sync_id must be 1-64 characters of [A-Za-z0-9_-]" };
  }
  if (typeof final !== "boolean") return { ok: false, error: "final must be a boolean" };
  if (!Array.isArray(games)) return { ok: false, error: "games must be an array" };
  if (games.length > MAX_GAMES_PER_CHUNK) {
    return { ok: false, error: `games exceeds ${MAX_GAMES_PER_CHUNK} items per chunk` };
  }
  const valid = games.map(normalizeGameItem).filter((g): g is GameItem => g !== null);
  return { ok: true, value: { syncId: sync_id, final, games: valid, skipped: games.length - valid.length } };
}

export interface HistoryQuery {
  limit: number;
  offset: number;
  sortBy: "end_date" | "title";
  sortDir: "asc" | "desc";
  store: "all" | "epic" | "steam";
  status: "all" | "active" | "expired";
}

function intParam(raw: string | null, fallback: number, min: number, max: number): number | null {
  if (raw === null) return fallback;
  if (!/^[+-]?\d+$/.test(raw.trim())) return null;
  const value = Number(raw);
  return value >= min && value <= max ? value : null;
}

function enumParam<T extends string>(raw: string | null, fallback: T, allowed: readonly T[]): T | null {
  if (raw === null) return fallback;
  return (allowed as readonly string[]).includes(raw) ? (raw as T) : null;
}

/** Parse /games/history query params with the same defaults and bounds as FastAPI. */
export function parseHistoryQuery(params: URLSearchParams): Validation<HistoryQuery> {
  const limit = intParam(params.get("limit"), 20, 1, 100);
  const offset = intParam(params.get("offset"), 0, 0, Number.MAX_SAFE_INTEGER);
  const sortBy = enumParam(params.get("sort_by"), "end_date", ["end_date", "title"] as const);
  const sortDir = enumParam(params.get("sort_dir"), "desc", ["asc", "desc"] as const);
  const store = enumParam(params.get("store"), "all", ["all", "epic", "steam"] as const);
  const status = enumParam(params.get("status"), "all", ["all", "active", "expired"] as const);

  if (limit === null) return { ok: false, error: "limit must be an integer between 1 and 100" };
  if (offset === null) return { ok: false, error: "offset must be a non-negative integer" };
  if (sortBy === null) return { ok: false, error: "sort_by must be 'end_date' or 'title'" };
  if (sortDir === null) return { ok: false, error: "sort_dir must be 'asc' or 'desc'" };
  if (store === null) return { ok: false, error: "store must be 'all', 'epic' or 'steam'" };
  if (status === null) return { ok: false, error: "status must be 'all', 'active' or 'expired'" };
  return { ok: true, value: { limit, offset, sortBy, sortDir, store, status } };
}

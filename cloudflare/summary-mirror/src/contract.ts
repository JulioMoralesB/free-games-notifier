// The GET /api/summary contract (docs/api.md#dashboard-summary-contract),
// mirrored from the Python service. Additive-only: never rename, remove or
// repurpose a field here without changing the Python side and the docs too.

export const SERVICE_NAME = "free-games-notifier";

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

/** Hard caps that keep a snapshot well inside Free-plan CPU and D1 limits. */
export const MAX_PROMOTIONS = 500;
export const MAX_FIELD_LENGTH = 2048;
export const MAX_BODY_BYTES = 256 * 1024;

const HAS_TIMEZONE = /([zZ]|[+-]\d{2}:?\d{2})$/;

/**
 * Parse an ISO-8601 timestamp to epoch ms, or NaN.
 * A timestamp without a zone designator is read as UTC, exactly like the
 * Python service's `is_still_active` (never as the runtime's local time).
 */
export function parseTimestamp(value: string): number {
  const trimmed = value.trim();
  if (!trimmed) return NaN;
  return Date.parse(HAS_TIMEZONE.test(trimmed) ? trimmed : `${trimmed}Z`);
}

/**
 * Promotions still running at `nowMs`, soonest-ending first.
 * Applied on every read, so a stale snapshot (host off for days) never
 * lists a promotion that has already ended. Inclusive bound, matching the
 * Python service; an unparseable end_date is dropped, since the mirror
 * cannot tell whether it is still free.
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

export type ValidationResult =
  | { ok: true; value: ValidSnapshot }
  | { ok: false; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "" && value.length <= MAX_FIELD_LENGTH;
}

/**
 * Validate an ingest body — the same JSON the Python service serves at
 * /api/summary. Only the four contract fields of each promotion are kept.
 */
export function validateSnapshot(body: unknown): ValidationResult {
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

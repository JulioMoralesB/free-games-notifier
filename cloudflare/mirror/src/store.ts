import { parseTimestamp, type GameItem, type HistoryQuery, type Promotion } from "./contract";

// Minimal structural types for the slice of the D1 binding API this Worker
// uses — avoids a dependency on @cloudflare/workers-types.
export interface D1Result<T = Record<string, unknown>> {
  results: T[];
}

export interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<D1Result<T>>;
  run(): Promise<unknown>;
}

export interface D1Database {
  prepare(query: string): D1PreparedStatement;
  /** Runs the statements in order as one call (one subrequest). */
  batch<T = Record<string, unknown>>(statements: D1PreparedStatement[]): Promise<D1Result<T>[]>;
}

export interface SummaryState {
  promotions: Promotion[];
  lastCheckAt: string | null;
  receivedAt: string;
  staleAlertSentAt: string | null;
}

export interface HistoryPage {
  games: GameItem[];
  total: number;
}

export interface Store {
  get(): Promise<SummaryState | null>;
  /** Replace the summary snapshot and re-arm the freshness alert. */
  saveSnapshot(promotions: Promotion[], lastCheckAt: string, receivedAt: string): Promise<void>;
  markStaleAlertSent(at: string): Promise<void>;
  /** Upsert one sync chunk; a final chunk also deletes games the sync didn't include. */
  syncGames(syncId: string, games: GameItem[], final: boolean): Promise<void>;
  history(query: HistoryQuery, nowMs: number): Promise<HistoryPage>;
}

interface SummaryRow {
  active_promotions: string;
  last_check_at: string | null;
  received_at: string;
  stale_alert_sent_at: string | null;
}

const UPSERT_GAME =
  "INSERT INTO games (id, store, title_sort, end_date, ends_at_ms, item, sync_id) " +
  "VALUES (?, ?, ?, ?, ?, ?, ?) " +
  "ON CONFLICT (id) DO UPDATE SET " +
  "store = excluded.store, title_sort = excluded.title_sort, end_date = excluded.end_date, " +
  "ends_at_ms = excluded.ends_at_ms, item = excluded.item, sync_id = excluded.sync_id";

export class D1Store implements Store {
  constructor(private readonly db: D1Database) {}

  async get(): Promise<SummaryState | null> {
    const row = await this.db
      .prepare(
        "SELECT active_promotions, last_check_at, received_at, stale_alert_sent_at " +
          "FROM summary_state WHERE id = 1",
      )
      .first<SummaryRow>();
    if (!row) return null;
    return {
      promotions: JSON.parse(row.active_promotions) as Promotion[],
      lastCheckAt: row.last_check_at,
      receivedAt: row.received_at,
      staleAlertSentAt: row.stale_alert_sent_at,
    };
  }

  async saveSnapshot(promotions: Promotion[], lastCheckAt: string, receivedAt: string): Promise<void> {
    await this.db
      .prepare(
        "INSERT INTO summary_state (id, active_promotions, last_check_at, received_at, stale_alert_sent_at) " +
          "VALUES (1, ?, ?, ?, NULL) " +
          "ON CONFLICT (id) DO UPDATE SET " +
          "active_promotions = excluded.active_promotions, " +
          "last_check_at = excluded.last_check_at, " +
          "received_at = excluded.received_at, " +
          "stale_alert_sent_at = NULL",
      )
      .bind(JSON.stringify(promotions), lastCheckAt, receivedAt)
      .run();
  }

  async markStaleAlertSent(at: string): Promise<void> {
    await this.db
      .prepare("UPDATE summary_state SET stale_alert_sent_at = ? WHERE id = 1")
      .bind(at)
      .run();
  }

  async syncGames(syncId: string, games: GameItem[], final: boolean): Promise<void> {
    const statements = games.map((game) => {
      const endsAt = parseTimestamp(game.end_date);
      return this.db.prepare(UPSERT_GAME).bind(
        `${game.store}:${game.link}`,
        game.store,
        game.title.toLowerCase(),
        game.end_date,
        Number.isNaN(endsAt) ? null : endsAt,
        JSON.stringify(game),
        syncId,
      );
    });
    if (final) {
      statements.push(this.db.prepare("DELETE FROM games WHERE sync_id <> ?").bind(syncId));
    }
    if (statements.length > 0) await this.db.batch(statements);
  }

  async history(query: HistoryQuery, nowMs: number): Promise<HistoryPage> {
    const conditions: string[] = [];
    const binds: unknown[] = [];
    if (query.store !== "all") {
      conditions.push("store = ?");
      binds.push(query.store);
    }
    // Same as the Python endpoint: active is strictly after now; an empty or
    // unparseable end_date counts as expired (datetime.min).
    if (query.status === "active") {
      conditions.push("ends_at_ms IS NOT NULL AND ends_at_ms > ?");
      binds.push(nowMs);
    } else if (query.status === "expired") {
      conditions.push("(ends_at_ms IS NULL OR ends_at_ms <= ?)");
      binds.push(nowMs);
    }
    const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    // Whitelisted by parseHistoryQuery, so safe to interpolate. Ties keep
    // insertion order in both directions, like Python's stable sort.
    const column = query.sortBy === "title" ? "title_sort" : "end_date";
    const direction = query.sortDir === "asc" ? "ASC" : "DESC";

    const [count, page] = await this.db.batch([
      this.db.prepare(`SELECT COUNT(*) AS total FROM games ${where}`).bind(...binds),
      this.db
        .prepare(`SELECT item FROM games ${where} ORDER BY ${column} ${direction}, rowid ASC LIMIT ? OFFSET ?`)
        .bind(...binds, query.limit, query.offset),
    ]);
    const total = Number((count?.results[0] as { total?: number } | undefined)?.total ?? 0);
    const games = ((page?.results ?? []) as { item: string }[]).map((row) => JSON.parse(row.item) as GameItem);
    return { games, total };
  }
}

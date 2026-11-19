import type { Promotion } from "./contract";

// Minimal structural types for the slice of the D1 binding API this Worker
// uses — avoids a dependency on @cloudflare/workers-types.
export interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  run(): Promise<unknown>;
}

export interface D1Database {
  prepare(query: string): D1PreparedStatement;
}

export interface SummaryState {
  promotions: Promotion[];
  lastCheckAt: string | null;
  receivedAt: string;
  staleAlertSentAt: string | null;
}

export interface Store {
  get(): Promise<SummaryState | null>;
  /** Replace the snapshot and re-arm the freshness alert. */
  saveSnapshot(promotions: Promotion[], lastCheckAt: string, receivedAt: string): Promise<void>;
  markStaleAlertSent(at: string): Promise<void>;
}

interface Row {
  active_promotions: string;
  last_check_at: string | null;
  received_at: string;
  stale_alert_sent_at: string | null;
}

/** One-row table (see migrations/): the latest snapshot plus alert state. */
export class D1Store implements Store {
  constructor(private readonly db: D1Database) {}

  async get(): Promise<SummaryState | null> {
    const row = await this.db
      .prepare(
        "SELECT active_promotions, last_check_at, received_at, stale_alert_sent_at " +
          "FROM summary_state WHERE id = 1",
      )
      .first<Row>();
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
}

// Test double for the D1 binding backed by Node's built-in SQLite, so tests
// run the real migration and the real SQL instead of a hand-written fake.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import type { D1Database, D1PreparedStatement } from "../src/store";

// Loaded via require() so Vite doesn't try to resolve the node:sqlite builtin.
const require = createRequire(import.meta.url);
const { DatabaseSync } = require("node:sqlite") as typeof import("node:sqlite");

type Sqlite = InstanceType<typeof DatabaseSync>;
type SqlValue = string | number | bigint | null | Uint8Array;

class Statement implements D1PreparedStatement {
  constructor(
    private readonly db: Sqlite,
    private readonly sql: string,
    private readonly values: SqlValue[] = [],
  ) {}

  bind(...values: unknown[]): D1PreparedStatement {
    return new Statement(this.db, this.sql, values as SqlValue[]);
  }

  async first<T>(): Promise<T | null> {
    const row = this.db.prepare(this.sql).get(...this.values);
    return (row ? { ...row } : null) as T | null;
  }

  async run(): Promise<unknown> {
    return this.db.prepare(this.sql).run(...this.values);
  }
}

export function createTestD1(): D1Database {
  const db = new DatabaseSync(":memory:");
  const migration = new URL("../migrations/0001_create_summary_state.sql", import.meta.url);
  db.exec(readFileSync(migration, "utf8"));
  return { prepare: (sql: string) => new Statement(db, sql) };
}

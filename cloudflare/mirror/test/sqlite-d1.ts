// Test double for the D1 binding backed by Node's built-in SQLite, so tests
// run the real migrations and the real SQL instead of a hand-written fake.
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import type { D1Database, D1PreparedStatement, D1Result } from "../src/store";

// Loaded via require() so Vite doesn't try to resolve the node:sqlite builtin.
const require = createRequire(import.meta.url);
const { DatabaseSync } = require("node:sqlite") as typeof import("node:sqlite");

type Sqlite = InstanceType<typeof DatabaseSync>;
type SqlValue = string | number | bigint | null | Uint8Array;

class Statement implements D1PreparedStatement {
  constructor(
    readonly db: Sqlite,
    readonly sql: string,
    readonly values: SqlValue[] = [],
  ) {}

  bind(...values: unknown[]): D1PreparedStatement {
    return new Statement(this.db, this.sql, values as SqlValue[]);
  }

  async first<T>(): Promise<T | null> {
    const row = this.db.prepare(this.sql).get(...this.values);
    return (row ? { ...row } : null) as T | null;
  }

  async all<T>(): Promise<D1Result<T>> {
    return { results: this.db.prepare(this.sql).all(...this.values).map((row) => ({ ...row }) as T) };
  }

  async run(): Promise<unknown> {
    return this.db.prepare(this.sql).run(...this.values);
  }

  isQuery(): boolean {
    return /^\s*SELECT/i.test(this.sql);
  }
}

export function createTestD1(): D1Database {
  const db = new DatabaseSync(":memory:");
  const migrationsDir = new URL("../migrations/", import.meta.url);
  for (const file of readdirSync(migrationsDir).filter((f) => f.endsWith(".sql")).sort()) {
    db.exec(readFileSync(new URL(file, migrationsDir), "utf8"));
  }

  return {
    prepare: (sql: string) => new Statement(db, sql),
    // D1 runs a batch as one implicit transaction: all or nothing.
    async batch<T>(statements: D1PreparedStatement[]): Promise<D1Result<T>[]> {
      db.exec("BEGIN");
      try {
        const results: D1Result<T>[] = [];
        for (const statement of statements as Statement[]) {
          if (statement.isQuery()) {
            results.push(await statement.all<T>());
          } else {
            await statement.run();
            results.push({ results: [] });
          }
        }
        db.exec("COMMIT");
        return results;
      } catch (error) {
        db.exec("ROLLBACK");
        throw error;
      }
    },
  };
}

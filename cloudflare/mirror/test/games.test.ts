import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it } from "vitest";
import { MAX_GAMES_BYTES, MAX_GAMES_PER_CHUNK, type GameItem } from "../src/contract";
import { handleRequest, type Deps, type Env } from "../src/handlers";
import { D1Store, type Store } from "../src/store";
import { createTestD1 } from "./sqlite-d1";

const INGEST_TOKEN = "fake-ingest-token";
const NOW = Date.UTC(2026, 10, 18, 17, 0);

interface ParityFixture {
  games: GameItem[];
  cases: { query: Record<string, string | number>; total: number; titles: string[] }[];
}
const parity = JSON.parse(
  readFileSync(new URL("./fixtures/history-parity.json", import.meta.url), "utf8"),
) as ParityFixture;

const game = (title: string, end_date: string, store = "epic"): GameItem => ({
  title,
  store,
  link: `https://${store}.example.com/${title.toLowerCase()}`,
  end_date,
  description: `About ${title}`,
  thumbnail: `https://${store}.example.com/${title.toLowerCase()}.jpg`,
  game_type: "game",
  original_price: null,
  review_scores: [],
});

let env: Env;
let now: number;
const deps = (): Deps => ({ store: new D1Store(env.DB), env, now: () => now });

beforeEach(() => {
  env = { DB: createTestD1(), DASHBOARD_API_KEY: "fake-dashboard-key", INGEST_TOKEN };
  now = NOW;
});

function pushGames(body: unknown, token: string | null = INGEST_TOKEN): Promise<Response> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token !== null) headers.authorization = `Bearer ${token}`;
  return handleRequest(
    new Request("https://mirror.test/api/mirror/games", {
      method: "POST",
      headers,
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
    deps(),
  );
}

async function history(query = ""): Promise<{ status: number; body: any }> {
  const response = await handleRequest(new Request(`https://mirror.test/games/history${query}`), deps());
  return { status: response.status, body: await response.json() };
}

const titles = async (query = "") => (await history(query)).body.games.map((g: GameItem) => g.title);

describe("POST /api/mirror/games", () => {
  const chunk = { sync_id: "sync1", final: true, games: [game("A", "2099-01-01T00:00:00Z")] };

  it.each([
    ["no bearer token", null],
    ["a wrong token", "nope"],
    ["the read-only dashboard key", "fake-dashboard-key"],
  ])("rejects %s with 401 and stores nothing", async (_label, token) => {
    expect((await pushGames(chunk, token)).status).toBe(401);
    expect((await history()).body.total).toBe(0);
  });

  it("fails closed when INGEST_TOKEN is unset", async () => {
    env.INGEST_TOKEN = undefined;
    expect((await pushGames(chunk, "anything")).status).toBe(401);
  });

  it.each([
    ["malformed JSON", "{nope"],
    ["a bad sync_id", { ...chunk, sync_id: "has spaces" }],
    ["a non-boolean final", { ...chunk, final: "yes" }],
    ["non-array games", { ...chunk, games: {} }],
    ["too many games", { ...chunk, games: Array(MAX_GAMES_PER_CHUNK + 1).fill(chunk.games[0]) }],
  ])("rejects %s with 400", async (_label, body) => {
    expect((await pushGames(body)).status).toBe(400);
  });

  it("rejects oversized chunks with 413", async () => {
    expect((await pushGames({ ...chunk, padding: "x".repeat(MAX_GAMES_BYTES) })).status).toBe(413);
  });

  it("stores valid games, skips invalid ones, and reports the count", async () => {
    const response = await pushGames({
      ...chunk,
      games: [chunk.games[0], { title: "No link" }, { ...game("B", ""), review_scores: [1] }, 42],
    });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ stored: 1, skipped: 3, final: true });
    expect(await titles()).toEqual(["A"]);
  });

  it("keeps only the GameItem contract fields", async () => {
    await pushGames({ ...chunk, games: [{ ...chunk.games[0], secret_internal_field: "x" }] });
    expect((await history()).body.games).toEqual([chunk.games[0]]);
  });

  it("upserts by store + link instead of duplicating", async () => {
    await pushGames(chunk);
    await pushGames({ ...chunk, sync_id: "sync2", games: [{ ...chunk.games[0], title: "A (renamed)" }] });
    expect(await titles()).toEqual(["A (renamed)"]);
  });

  it("deletes games missing from a sync only on its final chunk", async () => {
    await pushGames({ sync_id: "s1", final: true, games: [game("Old", "2099-01-01T00:00:00Z"), game("Kept", "2099-02-01T00:00:00Z")] });

    // A sync that fails before its final chunk only ever upserts.
    await pushGames({ sync_id: "s2", final: false, games: [game("Kept", "2099-02-01T00:00:00Z"), game("New", "2099-03-01T00:00:00Z")] });
    expect((await titles()).sort()).toEqual(["Kept", "New", "Old"]);

    // The final chunk of a complete sync removes what the sync didn't include.
    await pushGames({ sync_id: "s3", final: false, games: [game("Kept", "2099-02-01T00:00:00Z")] });
    await pushGames({ sync_id: "s3", final: true, games: [game("New", "2099-03-01T00:00:00Z")] });
    expect((await titles()).sort()).toEqual(["Kept", "New"]);
  });

  it("syncs an empty history with a single empty final chunk", async () => {
    await pushGames(chunk);
    await pushGames({ sync_id: "empty", final: true, games: [] });
    expect((await history()).body.total).toBe(0);
  });
});

describe("GET /games/history", () => {
  it("uses the same defaults as FastAPI (limit 20, end_date desc)", async () => {
    const games = Array.from({ length: 25 }, (_, i) => game(`G${i}`, `2099-01-${String(i + 1).padStart(2, "0")}T00:00:00Z`));
    await pushGames({ sync_id: "s", final: true, games });
    const { status, body } = await history();
    expect(status).toBe(200);
    expect(Object.keys(body)).toEqual(["games", "total", "limit", "offset"]);
    expect(body).toMatchObject({ total: 25, limit: 20, offset: 0 });
    expect(body.games[0].title).toBe("G24");
    expect(body.games).toHaveLength(20);
  });

  it.each([
    "?limit=0", "?limit=101", "?limit=abc", "?offset=-1", "?sort_by=price",
    "?sort_dir=up", "?store=gog", "?status=soon",
  ])("rejects %s with 422", async (query) => {
    expect((await history(query)).status).toBe(422);
  });

  it("computes active/expired against the current time on every request", async () => {
    await pushGames({ sync_id: "s", final: true, games: [game("Ends soon", "2026-11-19T00:00:00Z")] });
    expect(await titles("?status=active")).toEqual(["Ends soon"]);
    now = Date.UTC(2026, 10, 20);
    expect(await titles("?status=active")).toEqual([]);
    expect(await titles("?status=expired")).toEqual(["Ends soon"]);
  });

  it("returns 500 like the Python endpoint when storage fails", async () => {
    const broken = { history: () => Promise.reject(new Error("D1 down")) } as unknown as Store;
    const response = await handleRequest(new Request("https://mirror.test/games/history"), {
      store: broken, env, now: () => now,
    });
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ detail: "Failed to load game history" });
  });
});

describe("parity with the Python /games/history (shared fixture)", () => {
  beforeEach(async () => {
    expect((await pushGames({ sync_id: "parity", final: true, games: parity.games })).status).toBe(200);
  });

  it.each(parity.cases.map((c) => [new URLSearchParams(c.query as Record<string, string>).toString(), c] as const))(
    "?%s",
    async (query, expected) => {
      const { status, body } = await history(`?${query}`);
      expect(status).toBe(200);
      expect(body.total).toBe(expected.total);
      expect(body.games.map((g: GameItem) => g.title)).toEqual(expected.titles);
      for (const item of body.games) {
        expect(item).toEqual(parity.games.find((g) => g.title === item.title));
      }
    },
  );
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_SUMMARY_BYTES } from "../src/contract";
import { checkFreshness, handleRequest, type Deps, type Env } from "../src/handlers";
import { D1Store, type Store } from "../src/store";
import { createTestD1 } from "./sqlite-d1";

const DASHBOARD_KEY = "fake-dashboard-key";
const INGEST_TOKEN = "fake-ingest-token";
const NOW = Date.UTC(2026, 10, 18, 17, 0); // 11:00 in Mexico City
const HOUR = 3_600_000;

const snapshot = {
  service: "free-games-notifier",
  active_promotions: [
    {
      title: "Later",
      link: "https://store.steampowered.com/app/2/later/",
      store: "steam",
      end_date: "2026-11-25T18:00:00Z",
    },
    {
      title: "Sooner",
      link: "https://store.epicgames.com/p/sooner",
      store: "epic",
      end_date: "2026-11-20T16:00:00.000Z",
    },
  ],
  last_check_at: "2026-11-18T16:20:00+00:00",
};

let env: Env;
let now: number;
let deps: () => Deps;

beforeEach(() => {
  env = {
    DB: createTestD1(),
    DASHBOARD_API_KEY: DASHBOARD_KEY,
    INGEST_TOKEN,
    DISCORD_WEBHOOK_URL: "https://discord.example.com/api/webhooks/1/fake",
  };
  now = NOW;
  deps = () => ({ store: new D1Store(env.DB), env, now: () => now });
});

function getSummary(key: string | null = DASHBOARD_KEY): Promise<Response> {
  const headers: Record<string, string> = key === null ? {} : { "X-API-Key": key };
  return handleRequest(new Request("https://mirror.test/api/summary", { headers }), deps());
}

function push(body: unknown, token: string | null = INGEST_TOKEN): Promise<Response> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token !== null) headers.authorization = `Bearer ${token}`;
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  return handleRequest(
    new Request("https://mirror.test/api/mirror/summary", { method: "POST", headers, body: payload }),
    deps(),
  );
}

describe("GET /api/summary", () => {
  it.each([
    ["no key", null],
    ["a wrong key", "nope"],
  ])("rejects %s with 401", async (_label, key) => {
    expect((await getSummary(key)).status).toBe(401);
  });

  it("fails closed when DASHBOARD_API_KEY is unset, whatever key is sent", async () => {
    env.DASHBOARD_API_KEY = undefined;
    expect((await getSummary("")).status).toBe(401);
    expect((await getSummary("anything")).status).toBe(401);
  });

  it("returns an empty list and null last_check_at before the first snapshot", async () => {
    const response = await getSummary();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      service: "free-games-notifier",
      active_promotions: [],
      last_check_at: null,
    });
  });

  it("serves exactly the contract shape after a push, soonest-ending first", async () => {
    expect((await push(snapshot)).status).toBe(204);

    const body = (await (await getSummary()).json()) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(["active_promotions", "last_check_at", "service"]);
    expect(body).toEqual({
      service: "free-games-notifier",
      active_promotions: [snapshot.active_promotions[1], snapshot.active_promotions[0]],
      last_check_at: snapshot.last_check_at,
    });
  });

  it("filters expired promotions on every request, even with no new push", async () => {
    await push(snapshot);
    now = Date.UTC(2026, 10, 21); // after "Sooner" ended, before "Later"
    const body = (await (await getSummary()).json()) as { active_promotions: { title: string }[] };
    expect(body.active_promotions.map((p) => p.title)).toEqual(["Later"]);

    now = Date.UTC(2026, 11, 1); // both ended
    expect(((await (await getSummary()).json()) as { active_promotions: unknown[] }).active_promotions).toEqual([]);
  });

  it("returns 503 rather than an empty list when storage fails", async () => {
    const broken: Store = {
      get: () => Promise.reject(new Error("D1 down")),
      saveSnapshot: () => Promise.resolve(),
      markStaleAlertSent: () => Promise.resolve(),
      syncGames: () => Promise.resolve(),
      history: () => Promise.resolve({ games: [], total: 0 }),
    };
    const response = await handleRequest(
      new Request("https://mirror.test/api/summary", { headers: { "X-API-Key": DASHBOARD_KEY } }),
      { store: broken, env, now: () => now },
    );
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ detail: "Storage backend unavailable" });
  });

  it("rejects non-GET methods", async () => {
    const response = await handleRequest(
      new Request("https://mirror.test/api/summary", { method: "DELETE", headers: { "X-API-Key": DASHBOARD_KEY } }),
      deps(),
    );
    expect(response.status).toBe(405);
  });
});

describe("POST /api/mirror/summary", () => {
  it.each([
    ["no bearer token", null],
    ["a wrong token", "nope"],
    ["the read-only dashboard key", DASHBOARD_KEY],
  ])("rejects %s with 401 and stores nothing", async (_label, token) => {
    expect((await push(snapshot, token)).status).toBe(401);
    expect(((await (await getSummary()).json()) as { last_check_at: unknown }).last_check_at).toBeNull();
  });

  it("fails closed when INGEST_TOKEN is unset", async () => {
    env.INGEST_TOKEN = undefined;
    expect((await push(snapshot, "")).status).toBe(401);
    expect((await push(snapshot, "anything")).status).toBe(401);
  });

  it("rejects malformed JSON and invalid payloads with 400", async () => {
    expect((await push("{not json")).status).toBe(400);
    expect((await push({ ...snapshot, active_promotions: [{ title: "A" }] })).status).toBe(400);
  });

  it("rejects oversized bodies with 413", async () => {
    const huge = { ...snapshot, padding: "x".repeat(MAX_SUMMARY_BYTES) };
    expect((await push(huge)).status).toBe(413);
  });

  it("replaces the previous snapshot entirely", async () => {
    await push(snapshot);
    await push({ ...snapshot, active_promotions: [], last_check_at: "2026-11-19T16:20:00+00:00" });
    expect(await (await getSummary()).json()).toEqual({
      service: "free-games-notifier",
      active_promotions: [],
      last_check_at: "2026-11-19T16:20:00+00:00",
    });
  });
});

it("returns 404 for any other path (the dashboard is static assets, served before the Worker)", async () => {
  expect((await handleRequest(new Request("https://mirror.test/dashboard/missing.js"), deps())).status).toBe(404);
  expect((await handleRequest(new Request("https://mirror.test/check", { method: "POST" }), deps())).status).toBe(404);
});

describe("freshness check (Cron Trigger)", () => {
  const discordOk = () => vi.fn(async () => new Response(null, { status: 204 }));

  it("does nothing before the first snapshot", async () => {
    const fetchImpl = discordOk();
    expect(await checkFreshness({ ...deps(), fetchImpl })).toBe("no-snapshot");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("stays quiet while the last check is within STALE_AFTER_HOURS", async () => {
    await push(snapshot); // last_check_at = NOW - 40 min
    now = NOW + 25 * HOUR;
    const fetchImpl = discordOk();
    expect(await checkFreshness({ ...deps(), fetchImpl })).toBe("fresh");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("alerts Discord once per stale episode, and the next push re-arms it", async () => {
    await push(snapshot);
    now = NOW + 27 * HOUR;
    const fetchImpl = discordOk();

    expect(await checkFreshness({ ...deps(), fetchImpl })).toBe("alerted");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(env.DISCORD_WEBHOOK_URL);
    const payload = JSON.parse(String(init.body));
    expect(payload.allowed_mentions).toEqual({ parse: [] });
    expect(payload.content).toContain("no completed check in 27h");

    now += HOUR;
    expect(await checkFreshness({ ...deps(), fetchImpl })).toBe("already-alerted");
    expect(fetchImpl).toHaveBeenCalledTimes(1);

    await push({ ...snapshot, last_check_at: new Date(now).toISOString() });
    now += 27 * HOUR;
    expect(await checkFreshness({ ...deps(), fetchImpl })).toBe("alerted");
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("retries on the next run when Discord fails", async () => {
    await push(snapshot);
    now = NOW + 30 * HOUR;
    const failing = vi.fn(async () => new Response("rate limited", { status: 429 }));
    expect(await checkFreshness({ ...deps(), fetchImpl: failing })).toBe("alert-failed");

    const thrown = vi.fn(async () => {
      throw new TypeError("network down");
    });
    expect(await checkFreshness({ ...deps(), fetchImpl: thrown })).toBe("alert-failed");

    expect(await checkFreshness({ ...deps(), fetchImpl: discordOk() })).toBe("alerted");
  });

  it("only logs when no Discord webhook is configured", async () => {
    env.DISCORD_WEBHOOK_URL = undefined;
    await push(snapshot);
    now = NOW + 30 * HOUR;
    expect(await checkFreshness({ ...deps(), fetchImpl: discordOk() })).toBe("alert-disabled");
  });

  it("honours STALE_AFTER_HOURS and falls back to 26 on invalid values", async () => {
    await push(snapshot);
    now = NOW + 10 * HOUR;
    env.STALE_AFTER_HOURS = "6";
    expect(await checkFreshness({ ...deps(), fetchImpl: discordOk() })).toBe("alerted");

    env.STALE_AFTER_HOURS = "banana";
    await push({ ...snapshot, last_check_at: new Date(now).toISOString() });
    now += 25 * HOUR;
    expect(await checkFreshness({ ...deps(), fetchImpl: discordOk() })).toBe("fresh");
  });
});

import { describe, expect, it } from "vitest";
import { MAX_PROMOTIONS, activeAt, parseTimestamp, validateSnapshot, type Promotion } from "../src/contract";

const promo = (title: string, end_date: string): Promotion => ({
  title,
  link: `https://store.epicgames.com/p/${title.toLowerCase()}`,
  store: "epic",
  end_date,
});

describe("parseTimestamp", () => {
  it("reads a timestamp without a zone designator as UTC, like the Python service", () => {
    expect(parseTimestamp("2026-09-10T16:00:00")).toBe(Date.UTC(2026, 8, 10, 16));
  });
  it("honours Z and explicit offsets", () => {
    expect(parseTimestamp("2026-09-10T16:00:00.000Z")).toBe(Date.UTC(2026, 8, 10, 16));
    expect(parseTimestamp("2026-09-10T16:00:00+00:00")).toBe(Date.UTC(2026, 8, 10, 16));
    expect(parseTimestamp("2026-09-10T10:00:00-06:00")).toBe(Date.UTC(2026, 8, 10, 16));
  });
  it("returns NaN for empty or garbage input", () => {
    expect(parseTimestamp("")).toBeNaN();
    expect(parseTimestamp("not a date")).toBeNaN();
  });
});

describe("activeAt", () => {
  const now = Date.UTC(2026, 10, 18, 12);

  it("drops promotions that already ended and sorts the rest soonest-ending first", () => {
    const result = activeAt(
      [
        promo("Later", "2026-11-30T00:00:00Z"),
        promo("Expired", "2026-11-17T00:00:00Z"),
        promo("Sooner", "2026-11-20T00:00:00Z"),
      ],
      now,
    );
    expect(result.map((p) => p.title)).toEqual(["Sooner", "Later"]);
  });

  it("keeps a promotion ending exactly now (inclusive, like is_still_active)", () => {
    expect(activeAt([promo("Edge", new Date(now).toISOString())], now)).toHaveLength(1);
  });

  it("drops promotions whose end_date cannot be parsed", () => {
    expect(activeAt([promo("Weird", "someday")], now)).toEqual([]);
  });
});

describe("validateSnapshot", () => {
  const valid = {
    service: "free-games-notifier",
    active_promotions: [promo("Celeste", "2099-01-01T00:00:00.000Z")],
    last_check_at: "2026-11-18T16:20:00+00:00",
  };

  it("accepts the /api/summary body and keeps only the four contract fields", () => {
    const withExtra = {
      ...valid,
      active_promotions: [{ ...valid.active_promotions[0], description: "extra" }],
    };
    const result = validateSnapshot(withExtra);
    expect(result).toEqual({
      ok: true,
      value: { promotions: valid.active_promotions, lastCheckAt: valid.last_check_at },
    });
  });

  it.each([
    ["non-object body", []],
    ["foreign service", { ...valid, service: "something-else" }],
    ["missing last_check_at", { ...valid, last_check_at: null }],
    ["unparseable last_check_at", { ...valid, last_check_at: "yesterday" }],
    ["non-array promotions", { ...valid, active_promotions: {} }],
    ["empty title", { ...valid, active_promotions: [{ ...valid.active_promotions[0], title: " " }] }],
    ["missing link", { ...valid, active_promotions: [{ title: "A", store: "epic", end_date: "2099-01-01Z" }] }],
    ["non-http link", { ...valid, active_promotions: [{ ...valid.active_promotions[0], link: "javascript:alert(1)" }] }],
    ["too many promotions", { ...valid, active_promotions: Array(MAX_PROMOTIONS + 1).fill(valid.active_promotions[0]) }],
  ])("rejects %s", (_label, body) => {
    expect(validateSnapshot(body).ok).toBe(false);
  });
});

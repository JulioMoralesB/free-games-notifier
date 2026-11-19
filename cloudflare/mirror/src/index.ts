// Always-on, read-only mirror of free-games-notifier: the dashboard
// (static assets), GET /games/history and GET /api/summary, fed by pushes
// from the notifier. See docs/cloudflare-mirror.md.
import { checkFreshness, handleRequest, type Env } from "./handlers";
import { D1Store } from "./store";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, { store: new D1Store(env.DB), env, now: Date.now });
  },

  async scheduled(_controller: unknown, env: Env): Promise<void> {
    try {
      const outcome = await checkFreshness({ store: new D1Store(env.DB), env, now: Date.now });
      console.log(`freshness check: ${outcome}`);
    } catch (error) {
      console.error("freshness check failed:", error instanceof Error ? error.name : "unknown");
    }
  },
};

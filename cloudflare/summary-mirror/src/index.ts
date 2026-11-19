// Always-on mirror of free-games-notifier's GET /api/summary.
// See docs/summary-mirror.md for the architecture and setup.
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

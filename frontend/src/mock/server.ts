import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/**
 * Node-side MSW server for future component/integration tests (vitest + jsdom). The running app in
 * the browser uses ./browser.ts's setupWorker instead -- see main.tsx. Not wired into a test runner
 * yet (no test framework configured for the frontend in P5a/P5b); kept here so the handlers are
 * reusable across both without duplicating the mock API surface.
 */
export const server = setupServer(...handlers);

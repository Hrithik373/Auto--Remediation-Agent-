import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

/** Browser-side MSW worker, started from main.tsx in mock mode (VITE_USE_MOCKS != "false"). */
export const worker = setupWorker(...handlers);

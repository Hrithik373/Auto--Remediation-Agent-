import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./styles/index.css";

// Mock mode (FRONTEND_BLUEPRINT.md §5.3 / CLAUDE.md frontend addendum): "the frontend must build and
// run fully against MSW mocks with the backend down." Default to mocks ON until Phase P5c wires the
// real gateway; flip with VITE_USE_MOCKS=false once src/sentinel/gateway/api.py exists and is running.
async function enableMocking() {
  const useMocks = import.meta.env.VITE_USE_MOCKS !== "false";
  if (!useMocks) return;
  const { worker } = await import("./mock/browser");
  return worker.start({
    onUnhandledRequest: "bypass",
    serviceWorker: { url: "/mockServiceWorker.js" },
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

enableMocking().then(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </React.StrictMode>,
  );
});

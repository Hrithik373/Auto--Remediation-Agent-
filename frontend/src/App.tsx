import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import QueueRoute from "./routes/QueueRoute";
import TriageRoute from "./routes/TriageRoute";
import ResultsRoute from "./routes/ResultsRoute";
import ObservabilityRoute from "./routes/ObservabilityRoute";
import StatusDot from "./features/shared/StatusDot";

const MOCK_MODE = import.meta.env.VITE_USE_MOCKS !== "false";

const NAV_ITEMS = [
  { to: "/", label: "Queue", end: true },
  { to: "/results", label: "Results" },
  { to: "/observability", label: "Observability" },
];

/** Router + layout shell (FRONTEND_BLUEPRINT.md §3). Dense, dark, information-first — an on-call
 * tool, not a marketing dashboard (blueprint §8). */
export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-console-border bg-console-surface px-4">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <img src="/shield.svg" alt="" className="h-5 w-5" />
              <span className="font-mono text-sm font-semibold tracking-tight">sentinel-console</span>
            </div>
            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded px-3 py-1.5 text-sm transition-colors ${
                      isActive
                        ? "bg-console-surface-2 text-console-text"
                        : "text-console-text-muted hover:text-console-text"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2 text-2xs text-console-text-muted" data-testid="mode-indicator">
            <StatusDot tone={MOCK_MODE ? "revise" : "allow"} />
            <span>{MOCK_MODE ? "mock mode (MSW)" : "live gateway"}</span>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<QueueRoute />} />
            <Route path="/incidents/:incidentId" element={<TriageRoute />} />
            <Route path="/results" element={<ResultsRoute />} />
            <Route path="/observability" element={<ObservabilityRoute />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

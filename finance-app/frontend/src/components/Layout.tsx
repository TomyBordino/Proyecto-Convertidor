import { NavLink, Outlet, useParams } from "react-router-dom";
import type { Market } from "../types";

const MARKET_LABEL: Record<Market, string> = { us: "Wall Street", ar: "Argentina" };

export default function Layout() {
  const params = useParams<{ market?: Market }>();
  const market: Market = params.market === "ar" ? "ar" : "us";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <NavLink to={`/${market}`} className="text-lg font-semibold text-slate-900 dark:text-white">
            Finanzas<span className="text-blue-600">.ai</span>
          </NavLink>

          <nav className="flex items-center gap-2 text-sm">
            {(["us", "ar"] as Market[]).map((m) => (
              <NavLink
                key={m}
                to={`/${m}`}
                className={`px-3 py-1.5 rounded-full border transition-colors ${
                  m === market
                    ? "bg-blue-600 text-white border-blue-600"
                    : "border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-blue-400"
                }`}
              >
                {MARKET_LABEL[m]}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-800 py-4 text-center text-xs text-slate-500">
        Datos con fines informativos/educativos. No constituye asesoramiento financiero.
      </footer>
    </div>
  );
}

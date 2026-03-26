import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const ACTIVE_PORTFOLIO_KEY = "active_portfolio_id";

const NAV_LINKS = [
  { label: "Portfolio",     path: "/portfolio",   key: "portfolio" },
  { label: "Stocks",        path: null,           key: "stocks"    },
  { label: "Quality Stocks", path: "/quality-stocks", key: "quality-stocks" },
  { label: "Compare",       path: "/compare",     key: "compare"   },
  { label: "Prediction",    path: "/prediction",  key: "prediction"},
  { label: "Clusters",      path: null,           key: "clusters"  },
];

export default function Navbar() {
  const { isAuthenticated, logout, user } = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const activePortfolioId = sessionStorage.getItem(ACTIVE_PORTFOLIO_KEY);
  const stocksPath   = activePortfolioId ? `/stocks?portfolio=${activePortfolioId}` : "/portfolio?notice=select-portfolio";
  const clustersPath = "/clusters";

  const resolvedPath = (key) => {
    if (key === "stocks")   return stocksPath;
    if (key === "clusters") return clustersPath;
    return NAV_LINKS.find((l) => l.key === key)?.path ?? "/";
  };

  const isActive = (key) => {
    if (key === "portfolio") return location.pathname === "/portfolio";
    if (key === "stocks")    return location.pathname.startsWith("/stocks");
    if (key === "quality-stocks") return location.pathname.startsWith("/quality-stocks");
    if (key === "compare")   return location.pathname.startsWith("/compare");
    if (key === "prediction")return location.pathname.startsWith("/prediction");
    if (key === "clusters")  return location.pathname.includes("/clusters");
    return false;
  };

  const handleLogout = () => { logout(); navigate("/login"); setMobileOpen(false); };

  return (
    <header className="sticky top-0 z-30 border-b border-white/60 bg-gradient-to-r from-white/78 via-indigo-50/78 to-cyan-50/78 backdrop-blur-md shadow-sm">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">

        {/* Logo */}
        <Link
          to="/portfolio"
          className="flex items-center gap-2 text-lg font-extrabold tracking-tight"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-white text-sm font-black shadow">
            AI
          </span>
          <span className="bg-gradient-to-r from-indigo-700 to-violet-700 bg-clip-text text-transparent">
            AUTO INVEST
          </span>
        </Link>

        {/* Desktop nav */}
        {isAuthenticated && (
          <nav className="hidden items-center gap-1 md:flex">
            {NAV_LINKS.map(({ label, key }) => (
              <Link
                key={key}
                to={resolvedPath(key)}
                className={`relative rounded-lg px-3.5 py-2 text-sm font-semibold transition-all ${
                  isActive(key)
                    ? "text-indigo-700 after:absolute after:bottom-0 after:left-3 after:right-3 after:h-0.5 after:rounded-full after:bg-indigo-500"
                    : "text-slate-600 hover:bg-indigo-50/80 hover:text-slate-900"
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>
        )}

        {/* Right side */}
        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <>
              {user?.username && (
                <span className="hidden rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 sm:inline">
                  {user.username}
                </span>
              )}
              <button
                type="button"
                onClick={handleLogout}
                className="hidden rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600 sm:inline-flex"
              >
                Logout
              </button>
              {/* Mobile burger */}
              <button
                className="rounded-lg p-2 text-slate-600 hover:bg-indigo-50 md:hidden"
                onClick={() => setMobileOpen((p) => !p)}
                aria-label="Menu"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {mobileOpen
                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />}
                </svg>
              </button>
            </>
          ) : (
            <>
              {location.pathname !== "/login" && (
                <Link to="/login" className="rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50">
                  Login
                </Link>
              )}
              {location.pathname !== "/register" && (
                <Link to="/register" className="rounded-lg bg-gradient-to-r from-indigo-600 to-violet-600 px-3.5 py-1.5 text-sm font-semibold text-white shadow-sm hover:from-indigo-700 hover:to-violet-700">
                  Register
                </Link>
              )}
            </>
          )}
        </div>
      </div>
      <div className="h-px w-full bg-gradient-to-r from-transparent via-indigo-300/60 to-transparent" />

      {/* Mobile menu */}
      {isAuthenticated && mobileOpen && (
        <div className="border-t border-indigo-100/80 bg-white/95 px-4 pb-4 pt-2 md:hidden">
          <nav className="flex flex-col gap-1">
            {NAV_LINKS.map(({ label, key }) => (
              <Link
                key={key}
                to={resolvedPath(key)}
                onClick={() => setMobileOpen(false)}
                className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                  isActive(key) ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {label}
              </Link>
            ))}
            <button
              onClick={handleLogout}
              className="mt-2 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2.5 text-left text-sm font-semibold text-rose-600"
            >
              Logout
            </button>
          </nav>
        </div>
      )}
    </header>
  );
}

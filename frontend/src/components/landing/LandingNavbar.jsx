import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function LandingNavbar() {
  const { isAuthenticated } = useAuth();

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#050816]/70 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <Link to="/" className="group flex items-center gap-3">
          <span className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-300 via-sky-400 to-indigo-500 text-sm font-black text-slate-950 shadow-lg shadow-cyan-400/30">
            AI
            <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-[#050816]" />
          </span>
          <div>
            <p className="text-lg font-black tracking-tight text-white transition group-hover:text-cyan-300">AUTO INVEST</p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Intelligence Terminal</p>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <Link
              to="/portfolio"
              className="rounded-xl bg-gradient-to-r from-cyan-300 to-indigo-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:from-cyan-200 hover:to-indigo-300"
            >
              Go to Dashboard
            </Link>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-xl border border-white/20 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:border-cyan-300 hover:text-cyan-200"
              >
                Login
              </Link>
              <Link
                to="/register"
                className="rounded-xl bg-gradient-to-r from-cyan-300 to-indigo-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:from-cyan-200 hover:to-indigo-300"
              >
                Get Started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

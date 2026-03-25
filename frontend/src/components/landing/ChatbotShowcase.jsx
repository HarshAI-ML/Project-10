import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function ChatbotShowcase() {
  const { isAuthenticated } = useAuth();

  return (
    <section className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
      <article className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-lg backdrop-blur">
        <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">Key Differentiator</p>
        <h2 className="mt-2 text-2xl font-black text-white">Two-level chatbot intelligence</h2>
        <p className="mt-3 text-sm text-slate-300">
          Your chatbot concept is front-and-center: generic guidance for visitors and portfolio-specific intelligence after login.
        </p>

        <div className="mt-5 space-y-3 text-sm">
          <div className="rounded-xl border border-white/10 bg-slate-900/80 p-3 text-slate-200">
            Visitor: "What are safer sectors this week?"
          </div>
          <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/10 p-3 text-cyan-100">
            AI: "Healthcare and utilities show steadier sentiment. Want a generic watchlist?"
          </div>
          <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-3 text-emerald-100">
            Logged-in AI: "Your portfolio is overweight tech. Here are balancing ideas based on your holdings."
          </div>
        </div>
      </article>

      <article className="rounded-2xl border border-white/10 bg-gradient-to-br from-[#0b1227] to-[#10153a] p-6 shadow-lg">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-300">Product Positioning</p>
        <h3 className="mt-2 text-xl font-bold text-white">From information to action</h3>

        <ul className="mt-4 space-y-2 text-sm text-slate-300">
          <li className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Public landing for discovery and trust building</li>
          <li className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Authenticated workspace for execution workflows</li>
          <li className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Consistent design language across analytics modules</li>
        </ul>

        <div className="mt-5">
          {isAuthenticated ? (
            <Link
              to="/portfolio"
              className="inline-flex rounded-xl bg-gradient-to-r from-cyan-300 to-indigo-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:from-cyan-200 hover:to-indigo-300"
            >
              Open Workspace
            </Link>
          ) : (
            <Link
              to="/register"
              className="inline-flex rounded-xl bg-gradient-to-r from-cyan-300 to-indigo-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:from-cyan-200 hover:to-indigo-300"
            >
              Get Started
            </Link>
          )}
        </div>
      </article>
    </section>
  );
}

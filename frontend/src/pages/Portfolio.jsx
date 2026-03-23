import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Loader from "../components/Loader";
import { createPortfolio, fetchPortfolio } from "../api/stocks";

const ACTIVE_PORTFOLIO_KEY = "active_portfolio_id";

const PORTFOLIO_ICONS = ["📊", "📈", "💹", "🏦", "💰", "🌐", "⚡", "🚀"];

export default function Portfolio() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [portfolios, setPortfolios] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", geography: "ALL" });
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [openingClusterId, setOpeningClusterId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const notice = searchParams.get("notice");
    if (notice === "select-portfolio") {
      setMessage("Please select or create a portfolio first.");
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchPortfolio();
        setPortfolios(Array.isArray(data) ? data : []);
      } catch {
        setError("Unable to load portfolios.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setCreating(true);
    setError("");
    setMessage("");
    try {
      const created = await createPortfolio({
        name: form.name.trim(),
        description: form.description.trim(),
        geography: form.geography,
      });
      sessionStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(created.id));
      setPortfolios((p) => [...p, created]);
      setForm({ name: "", description: "", geography: "ALL" });
      setMessage("Portfolio created successfully.");
    } catch (err) {
      setError(err.response?.data?.name?.[0] || "Unable to create portfolio.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="space-y-8">

      {/* ── Header ── */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Portfolios</h1>
        <p className="mt-1 text-sm text-slate-500">
          Manage your investment portfolios and access stock analytics
        </p>
      </div>

      {/* ── Notices ── */}
      {message && (
        <div className="flex items-center gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700 ring-1 ring-emerald-200">
          <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
          </svg>
          {message}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-3 rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 ring-1 ring-rose-200">
          <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd"/>
          </svg>
          {error}
        </div>
      )}

      {/* ── Create form ── */}
      <div className="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-700 p-1 shadow-lg">
        <div className="rounded-xl bg-white p-6">
          <h2 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
            New Portfolio
          </h2>
          <form onSubmit={handleCreate} className="flex flex-col gap-3 sm:flex-row">
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
              placeholder="Portfolio name (e.g. Tech Growth)"
              required
            />
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
              placeholder="Short description (optional)"
            />
            <select
              value={form.geography}
              onChange={(e) => setForm((p) => ({ ...p, geography: e.target.value }))}
              className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            >
              <option value="ALL">[ALL] All</option>
              <option value="IN">[IN] India</option>
              <option value="US">[US] US</option>
            </select>
            <button
              type="submit"
              disabled={creating}
              className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-2.5 text-sm font-bold text-white shadow transition hover:from-indigo-700 hover:to-violet-700 active:scale-[0.98] disabled:opacity-50 whitespace-nowrap"
            >
              {creating ? (
                <>
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  Creating…
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/>
                  </svg>
                  Create
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* ── Portfolio grid ── */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader /></div>
      ) : portfolios.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl bg-white py-16 text-center shadow-sm ring-1 ring-slate-100">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-3xl">📊</div>
          <p className="font-semibold text-slate-700">No portfolios yet</p>
          <p className="mt-1 text-sm text-slate-400">Create your first portfolio above to get started</p>
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {portfolios.map((portfolio, idx) => (
            <div
              key={portfolio.id}
              role="button"
              tabIndex={0}
              className="group relative cursor-pointer overflow-hidden rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100 transition-all hover:-translate-y-1 hover:shadow-lg hover:ring-indigo-200"
              onClick={() => {
                sessionStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(portfolio.id));
                navigate(`/stocks?portfolio=${portfolio.id}`);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  sessionStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(portfolio.id));
                  navigate(`/stocks?portfolio=${portfolio.id}`);
                }
              }}
            >
              {/* Decorative top bar */}
              <div className="absolute inset-x-0 top-0 h-1 rounded-t-2xl bg-gradient-to-r from-indigo-500 to-violet-500" />

              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-50 to-violet-50 text-2xl ring-1 ring-indigo-100">
                  {PORTFOLIO_ICONS[idx % PORTFOLIO_ICONS.length]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-bold text-slate-900">{portfolio.name}</p>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                      [{portfolio.geography || "ALL"}]
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400 line-clamp-2">
                    {portfolio.description || "No description provided"}
                  </p>
                </div>
              </div>

              <div className="mt-5 flex gap-2">
                <span className="flex-1 rounded-lg bg-indigo-50 py-1.5 text-center text-xs font-semibold text-indigo-700 group-hover:bg-indigo-100 transition">
                  Open Stocks →
                </span>
                <button
                  type="button"
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 disabled:opacity-50"
                  disabled={openingClusterId === portfolio.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpeningClusterId(portfolio.id);
                    sessionStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(portfolio.id));
                    navigate(`/portfolio/${portfolio.id}/clusters`);
                  }}
                >
                  {openingClusterId === portfolio.id ? "…" : "Clusters"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

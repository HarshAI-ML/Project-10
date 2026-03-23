import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  CartesianGrid, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import Loader from "../components/Loader";
import { fetchPortfolio, fetchPortfolioClusters } from "../api/stocks";

const ACTIVE_PORTFOLIO_KEY = "active_portfolio_id";

/* Vivid cluster colour palette */
const CLUSTER_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#e11d48", "#0ea5e9", "#8b5cf6"];

const CLUSTER_MEANINGS = [
  { label: "Uptrend Leaders",   icon: "🚀", description: "Strong momentum with supportive trend behavior." },
  { label: "Possible Rebound",  icon: "📈", description: "Oversold profile with recovery potential." },
  { label: "Stable Stocks",     icon: "🏦", description: "Lower volatility and steadier return profile." },
  { label: "Weak Stocks",       icon: "📉", description: "Lower trend strength and weaker momentum profile." },
];

const fmt = (v) =>
  v == null || Number.isNaN(Number(v)) ? "—" : `${(Number(v) * 100).toFixed(2)}%`;
const fmtD = (v) =>
  v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(4);

/* ── Custom scatter tooltip ──────────────────────────────────── */
const ScatterTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload;
  if (!p) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur text-sm">
      <p className="font-bold text-slate-900">{p.stock || "—"}</p>
      <p className="mt-0.5 text-xs font-medium text-indigo-600">{p.cluster_label || "—"}</p>
      <div className="mt-2 space-y-0.5 text-xs text-slate-500">
        <p>Momentum: <span className="font-semibold text-slate-800">{fmt(p.momentum)}</span></p>
        <p>Volatility: <span className="font-semibold text-slate-800">{fmt(p.volatility)}</span></p>
        <p>RSI(14): <span className="font-semibold text-slate-800">{fmtD(p.rsi)}</span></p>
      </div>
    </div>
  );
};

/* ── Stat card ───────────────────────────────────────────────── */
const StatCard = ({ label, value, accent }) => {
  const bg = {
    indigo: "from-indigo-500 to-indigo-600",
    emerald: "from-emerald-500 to-emerald-600",
    violet: "from-violet-500 to-violet-600",
    amber: "from-amber-500 to-amber-600",
  }[accent] ?? "from-slate-400 to-slate-500";
  return (
    <div className="relative overflow-hidden rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
      <div className={`absolute right-0 top-0 h-16 w-16 rounded-bl-3xl bg-gradient-to-br ${bg} opacity-[0.08]`} />
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-extrabold text-slate-900">{value}</p>
    </div>
  );
};

export default function PortfolioClusters() {
  const [searchParams] = useSearchParams();
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const portfolioId = routeId || searchParams.get("portfolio") || sessionStorage.getItem(ACTIVE_PORTFOLIO_KEY);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [portfolios, setPortfolios] = useState([]);
  const [clusterData, setClusterData] = useState(null);
  const [loadingStep, setLoadingStep] = useState("Analyzing portfolio…");

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === String(portfolioId)) || null,
    [portfolios, portfolioId]
  );

  useEffect(() => {
    if (!portfolioId) { navigate("/portfolio?notice=select-portfolio", { replace: true }); return; }
    const steps = ["Analyzing portfolio…", "Computing factors…", "Generating clusters…"];
    let i = 0;
    const timer = window.setInterval(() => { i = (i + 1) % steps.length; setLoadingStep(steps[i]); }, 900);
    setLoading(true); setError(""); setMessage("");
    Promise.all([fetchPortfolio(), fetchPortfolioClusters(portfolioId, 4)])
      .then(([pRows, clusters]) => {
        const pArr = Array.isArray(pRows) ? pRows : [];
        if (!pArr.some((p) => String(p.id) === String(portfolioId))) {
          navigate("/portfolio?notice=select-portfolio", { replace: true }); return;
        }
        sessionStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(portfolioId));
        setPortfolios(pArr);
        setClusterData(clusters);
        if (clusters?.status !== "ok") setMessage(clusters?.detail || "Clustering analysis unavailable.");
      })
      .catch((err) =>
        setError(
          err?.code === "ECONNABORTED"
            ? "Clustering is taking longer than expected. Please try again."
            : err?.response?.data?.detail || "Failed to load clustering analysis."
        )
      )
      .finally(() => { window.clearInterval(timer); setLoading(false); });
  }, [navigate, portfolioId]);

  const scatterGroups = useMemo(() => {
    const map = new Map();
    (clusterData?.features || []).forEach((row) => {
      const k = Number(row.cluster);
      const bucket = map.get(k) || [];
      bucket.push({ ...row, x: Number(row.umap_x), y: Number(row.umap_y) });
      map.set(k, bucket);
    });
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [clusterData]);

  const stats = useMemo(() => {
    const rows = clusterData?.features || [];
    return {
      stockCount: rows.length,
      clusterCount: new Set(rows.map((r) => r.cluster)).size,
      featureCount: 6,
    };
  }, [clusterData]);

  /* ── Loading ── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-600 shadow-xl">
          <svg className="h-10 w-10 animate-spin text-white" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
        </div>
        <p className="text-base font-semibold text-slate-700">{loadingStep}</p>
        <p className="mt-1 text-sm text-slate-400">UMAP + KMeans segmentation running</p>
      </div>
    );
  }

  const ok = clusterData?.status === "ok";

  return (
    <section className="space-y-8">
      {/* ── Hero header ── */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-violet-950 p-8 text-white shadow-xl">
        <div className="pointer-events-none absolute -right-12 -top-12 h-56 w-56 rounded-full bg-indigo-500/10" />
        <div className="pointer-events-none absolute -bottom-10 -left-10 h-40 w-40 rounded-full bg-violet-500/10" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              {selectedPortfolio?.name || "Portfolio"}
            </p>
            <h1 className="mt-1 text-3xl font-extrabold">Clustering Analysis</h1>
            <p className="mt-1 text-sm text-slate-400">
              UMAP projection + KMeans segmentation · Factor-based opportunity clusters
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to={`/stocks?portfolio=${portfolioId}`}
              className="rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/20"
            >
              ← Stocks
            </Link>
            <Link
              to="/portfolio"
              className="rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/20"
            >
              Portfolios
            </Link>
          </div>
        </div>
      </div>

      {/* ── Stat row ── */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Stocks Analysed" value={stats.stockCount} accent="indigo" />
        <StatCard label="Clusters Found" value={stats.clusterCount} accent="violet" />
        <StatCard label="Factors Used" value={stats.featureCount} accent="emerald" />
      </div>

      {/* ── Alerts ── */}
      {error && (
        <div className="flex items-center gap-2 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-200">
          <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd"/>
          </svg>
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-700 ring-1 ring-amber-200">{message}</div>
      )}

      {!ok && !error && (
        <div className="flex flex-col items-center rounded-2xl bg-white py-16 text-center shadow-sm ring-1 ring-slate-100">
          <div className="mb-4 text-4xl">🔬</div>
          <p className="font-semibold text-slate-700">Clustering unavailable</p>
          <p className="mt-1 text-sm text-slate-400">Add more stocks with longer trading history and retry.</p>
          <button onClick={() => window.location.reload()} className="mt-5 rounded-xl bg-indigo-600 px-5 py-2 text-sm font-bold text-white hover:bg-indigo-700 transition">
            Retry Analysis
          </button>
        </div>
      )}

      {ok && (
        <>
          {/* ── UMAP Scatter ── */}
          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-slate-800">UMAP Cluster Scatter</h2>
                <p className="mt-0.5 text-xs text-slate-400">X/Y coordinates are UMAP embeddings of factor features</p>
              </div>
              {/* Legend chips */}
              <div className="flex flex-wrap gap-2">
                {scatterGroups.map(([clusterId, points], idx) => (
                  <span key={clusterId} className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-slate-200" style={{ color: CLUSTER_COLORS[idx % CLUSTER_COLORS.length] }}>
                    <span className="h-2 w-2 rounded-full" style={{ background: CLUSTER_COLORS[idx % CLUSTER_COLORS.length] }} />
                    {points[0]?.cluster_label || `Cluster ${clusterId}`}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-5 h-[420px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis type="number" dataKey="x" name="UMAP X" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                  <YAxis type="number" dataKey="y" name="UMAP Y" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={60} />
                  <Tooltip content={<ScatterTooltip />} />
                  {scatterGroups.map(([clusterId, points], idx) => (
                    <Scatter
                      key={`cluster-${clusterId}`}
                      name={`${points[0]?.cluster_label || `Cluster ${clusterId}`}`}
                      data={points}
                      fill={CLUSTER_COLORS[idx % CLUSTER_COLORS.length]}
                      fillOpacity={0.85}
                      r={6}
                    />
                  ))}
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ── Cluster Summary ── */}
          <div className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-base font-bold text-slate-800">Cluster Summary</h2>
              <p className="mt-0.5 text-xs text-slate-400">Aggregated factor statistics per cluster</p>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="bg-slate-900 text-white">
                    {["Cluster", "Stocks", "Avg Momentum", "Avg Volatility", "Avg Trend", "Avg Opportunity", "Insight"].map((h) => (
                      <th key={h} className={`px-5 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap ${h === "Cluster" || h === "Insight" ? "text-left" : "text-right"}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {clusterData.cluster_summary.map((row, idx) => (
                    <tr key={`summary-${row.cluster}`} className="hover:bg-slate-50 transition">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="h-3 w-3 rounded-full flex-shrink-0" style={{ background: CLUSTER_COLORS[idx % CLUSTER_COLORS.length] }} />
                          <span className="text-sm font-bold text-slate-900">{row.cluster_label}</span>
                          <span className="text-xs text-slate-400">#{row.cluster}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-right text-sm font-semibold text-slate-700">{row.stock_count}</td>
                      <td className={`px-5 py-3.5 text-right text-sm font-semibold ${Number(row.avg_momentum) >= 0 ? "text-emerald-600" : "text-rose-500"}`}>
                        {fmt(row.avg_momentum)}
                      </td>
                      <td className="px-5 py-3.5 text-right text-sm text-slate-600">{fmt(row.avg_volatility)}</td>
                      <td className={`px-5 py-3.5 text-right text-sm font-semibold ${Number(row.avg_trend) >= 0 ? "text-emerald-600" : "text-rose-500"}`}>
                        {fmtD(row.avg_trend)}
                      </td>
                      <td className="px-5 py-3.5 text-right text-sm font-bold text-indigo-600">{fmtD(row.avg_opportunity)}</td>
                      <td className="max-w-[200px] px-5 py-3.5 text-xs text-slate-500">{row.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Top Opportunities ── */}
          {clusterData.top_opportunities?.length > 0 && (
            <div className="rounded-2xl bg-gradient-to-br from-indigo-950 to-violet-950 p-6 text-white shadow-xl">
              <h2 className="text-base font-bold">🏆 Top Opportunity Stocks</h2>
              <p className="mt-0.5 text-xs text-slate-400">Ranked by multi-factor opportunity score</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {clusterData.top_opportunities.slice(0, 8).map((row, idx) => (
                  <div key={`op-${row.stock}`} className="flex items-center gap-3 rounded-xl bg-white/10 px-4 py-3 backdrop-blur ring-1 ring-white/10">
                    <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white/20 text-sm font-black">
                      #{idx + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-mono text-sm font-bold">{row.stock}</p>
                      <p className="text-xs text-indigo-300">Score: {fmtD(row.opportunity_score)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Stock Factor Table ── */}
          <div className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-base font-bold text-slate-800">Stock Factor Table</h2>
              <p className="mt-0.5 text-xs text-slate-400">All factor metrics per stock used in clustering</p>
            </div>
            <div className="max-h-[520px] overflow-auto thin-scroll">
              <table className="min-w-full">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-slate-800 text-white">
                    {["Stock", "Momentum", "Volatility", "Dist MA50", "Dist MA200", "Drawdown", "52W High", "RSI(14)", "Beta", "Trend", "Score", "Cluster"].map((h) => (
                      <th key={h} className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap ${h === "Stock" || h === "Cluster" ? "text-left" : "text-right"}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {clusterData.features.map((row, idx) => {
                    const clusterIdx = scatterGroups.findIndex(([k]) => k === Number(row.cluster));
                    const color = CLUSTER_COLORS[clusterIdx % CLUSTER_COLORS.length] ?? CLUSTER_COLORS[0];
                    return (
                      <tr key={`row-${row.stock}`} className="hover:bg-slate-50 transition">
                        <td className="px-4 py-2.5 font-mono text-sm font-bold text-slate-900">{row.stock}</td>
                        <td className={`px-4 py-2.5 text-right text-xs font-semibold ${Number(row.momentum) >= 0 ? "text-emerald-600" : "text-rose-500"}`}>{fmt(row.momentum)}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmt(row.volatility)}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmt(row.dist_ma50)}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmt(row.dist_ma200)}</td>
                        <td className={`px-4 py-2.5 text-right text-xs font-semibold ${Number(row.drawdown) >= 0 ? "text-slate-500" : "text-rose-500"}`}>{fmt(row.drawdown)}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmt(row.dist_52w_high)}</td>
                        <td className={`px-4 py-2.5 text-right text-xs font-semibold ${Number(row.rsi) > 70 ? "text-rose-500" : Number(row.rsi) < 30 ? "text-emerald-600" : "text-slate-600"}`}>{fmtD(row.rsi)}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-500">{fmtD(row.beta)}</td>
                        <td className={`px-4 py-2.5 text-right text-xs font-semibold ${Number(row.trend) >= 0 ? "text-emerald-600" : "text-rose-500"}`}>{fmtD(row.trend)}</td>
                        <td className="px-4 py-2.5 text-right text-xs font-bold text-indigo-600">{fmtD(row.opportunity_score)}</td>
                        <td className="px-4 py-2.5">
                          <span className="inline-block rounded-full px-2.5 py-0.5 text-xs font-bold text-white" style={{ background: color }}>
                            {row.cluster_label || `C${row.cluster}`}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Cluster Meanings ── */}
          <div className="grid gap-4 sm:grid-cols-2">
            {CLUSTER_MEANINGS.map((m, idx) => (
              <div key={m.label} className="flex items-start gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl text-2xl" style={{ background: `${CLUSTER_COLORS[idx]}18` }}>
                  {m.icon}
                </div>
                <div>
                  <p className="font-bold text-slate-900">{m.label}</p>
                  <p className="mt-0.5 text-sm text-slate-500">{m.description}</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

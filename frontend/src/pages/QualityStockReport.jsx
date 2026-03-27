import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import Loader from "../components/Loader";
import {
  deleteQualityStock, fetchQualityStockDetail, rerunQualityStockReport,
} from "../api/stocks";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

// â”€â”€â”€ signal config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const signalConfig = {
  BUY:  { pill: "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200", dot: "bg-emerald-500" },
  HOLD: { pill: "bg-amber-100 text-amber-700 ring-1 ring-amber-200",       dot: "bg-amber-500"  },
  SELL: { pill: "bg-rose-100 text-rose-600 ring-1 ring-rose-200",          dot: "bg-rose-500"   },
};

// â”€â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const numberOrDash = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "â€”";
  return Number(value).toFixed(digits);
};

const percentOrDash = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "â€”";
  const numeric = Number(value);
  const normalized = Math.abs(numeric) <= 2 ? numeric * 100 : numeric;
  return `${normalized >= 0 ? "+" : ""}${normalized.toFixed(2)}%`;
};

// â”€â”€â”€ SVG ring progress â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function RatingRing({ rating }) {
  const r = 52, cx = 64, cy = 64;
  const circ = 2 * Math.PI * r;
  const filled = circ * (rating / 10);
  const color = rating >= 7 ? "#34d399" : rating >= 5 ? "#fbbf24" : "#f87171";
  return (
    <svg viewBox="0 0 128 128" className="h-32 w-32 -rotate-90">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="10"
        strokeDasharray={`${filled} ${circ}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray 0.8s cubic-bezier(.4,0,.2,1)" }} />
    </svg>
  );
}

// â”€â”€â”€ custom chart tooltip â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function ChartTooltip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-slate-100 bg-white px-3 py-2 shadow-lg text-xs">
      <p className="mb-1 font-semibold text-slate-500">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }} className="font-bold">
          {p.name}: {currency ? formatMoney(p.value, currency) : p.value}
        </p>
      ))}
    </div>
  );
}

function Alert({ variant, children }) {
  const styles = {
    error:   "border-rose-200 bg-rose-50 text-rose-700",
    neutral: "border-slate-200 bg-white text-slate-500 text-center py-8",
  };
  return <div className={`rounded-xl border px-4 py-3 text-sm ${styles[variant]}`}>{children}</div>;
}

function Spinner() {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function InfoHint({ text }) {
  return (
    <span className="group relative inline-flex">
      <span
        aria-label={text}
        tabIndex={0}
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-300 bg-slate-50 text-[10px] font-bold text-slate-500"
      >
        i
      </span>
      <span className="pointer-events-none absolute left-1/2 top-6 z-50 w-56 -translate-x-1/2 rounded-lg bg-slate-900 px-2.5 py-1.5 text-[11px] leading-4 text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
        {text}
      </span>
    </span>
  );
}

function ChartCard({ title, subtitle, infoText, children }) {
  return (
    <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-bold text-slate-900">{title}</h2>
          {infoText && <InfoHint text={infoText} />}
        </div>
        <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

function InsightCard({ title, items, variant, infoText }) {
  const isRisk  = variant === "risk";
  const hBg     = isRisk ? "bg-rose-50"    : "bg-emerald-50";
  const hTxt    = isRisk ? "text-rose-700"  : "text-emerald-700";
  const iconBg  = isRisk ? "bg-rose-100"    : "bg-emerald-100";
  const itemCls = isRisk
    ? "bg-rose-50/60 border-rose-100 text-rose-700"
    : "bg-emerald-50/60 border-emerald-100 text-emerald-700";
  const numBg   = isRisk ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-700";
  const d = isRisk
    ? "M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
    : "M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z";
  return (
    <div className="overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-slate-100">
      <div className={`flex items-center gap-3 px-6 py-4 ${hBg}`}>
        <div className={`flex h-8 w-8 items-center justify-center rounded-xl ${iconBg}`}>
          <svg className={`h-4 w-4 ${hTxt}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d={d} />
          </svg>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className={`text-sm font-bold ${hTxt}`}>{title}</h2>
            {infoText && <InfoHint text={infoText} />}
          </div>
          <p className="text-xs text-slate-400">{items.length} item{items.length !== 1 ? "s" : ""}</p>
        </div>
      </div>
      <div className="space-y-2.5 p-5">
        {items.length === 0 && (
          <p className="py-4 text-center text-sm text-slate-400">No {title.toLowerCase()} identified.</p>
        )}
        {items.map((item, index) => (
          <div key={`${item}-${index}`} className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${itemCls}`}>
            <span className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${numBg}`}>
              {index + 1}
            </span>
            <span className="leading-5">{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// â”€â”€â”€ main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function QualityStockReport() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [report, setReport]         = useState(null);
  const [loading, setLoading]       = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError]           = useState("");

  const loadReport = async () => {
    setLoading(true); setError("");
    try { setReport(await fetchQualityStockDetail(id)); }
    catch (err) { setError(err?.response?.data?.detail || "Unable to load the quality stock report."); setReport(null); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadReport(); }, [id]);

  const priceHistory  = useMemo(() => report?.graphs_data?.price_history || [], [report]);
  const financialBars = useMemo(() =>
    (report?.graphs_data?.financial_metrics || []).map((r) => ({
      metric: r.metric, stock: r.stock_value, sector: r.sector_average,
    })), [report]);

  const handleRerun = async () => {
    setBusyAction("rerun"); setError("");
    try { setReport(await rerunQualityStockReport(id)); }
    catch (err) { setError(err?.response?.data?.detail || "Unable to regenerate this report."); }
    finally { setBusyAction(""); }
  };

  const handleDelete = async () => {
    setBusyAction("delete"); setError("");
    try { await deleteQualityStock(id); navigate("/quality-stocks"); }
    catch (err) { setError(err?.response?.data?.detail || "Unable to delete this report."); setBusyAction(""); }
  };

  if (loading) return <div className="flex justify-center py-16"><Loader /></div>;
  if (error && !report) return <Alert variant="error">{error}</Alert>;
  if (!report) return <Alert variant="neutral">Report not found.</Alert>;

  const signal = String(report.buy_signal || report.recommended_action || "").toUpperCase();
  const sigCfg = signalConfig[signal] || { pill: "bg-slate-100 text-slate-600", dot: "bg-slate-400" };
  const rating = Math.max(0, Math.min(10, Number(report.ai_rating || 0)));
  const currency = currencyCodeFromItem(report);
  const kf = report.key_financials || {};

  const valueColor = (type, raw) => {
    if (raw === null || raw === undefined || Number.isNaN(Number(raw))) return "text-slate-900";
    const v = Number(raw);
    if (type === "percent") return v > 0 ? "text-emerald-600" : v < 0 ? "text-rose-600" : "text-slate-900";
    if (type === "pe")  return v < 20 ? "text-emerald-600" : v > 40 ? "text-rose-600" : "text-amber-600";
    if (type === "de")  return v <  1 ? "text-emerald-600" : v >  2 ? "text-rose-600" : "text-amber-600";
    if (type === "cr")  return v >= 1.5 ? "text-emerald-600" : v < 1 ? "text-rose-600" : "text-amber-600";
    return "text-slate-900";
  };

  const financialRows = [
    { label: "Revenue Growth",   value: percentOrDash(kf.revenue_growth),   raw: kf.revenue_growth,   type: "percent", info: "Year-over-year change in company revenue." },
    { label: "Earnings Growth",  value: percentOrDash(kf.earnings_growth),  raw: kf.earnings_growth,  type: "percent", info: "Year-over-year growth in earnings/profit." },
    { label: "EPS",              value: numberOrDash(kf.eps_trailing),       raw: kf.eps_trailing,     type: "number",  info: "Trailing earnings per share from recent results." },
    { label: "Forward EPS",      value: numberOrDash(kf.eps_forward),        raw: kf.eps_forward,      type: "number",  info: "Estimated earnings per share for the next period." },
    { label: "PE Ratio",         value: numberOrDash(kf.trailing_pe),        raw: kf.trailing_pe,      type: "pe",      info: "Price divided by trailing earnings per share." },
    { label: "Forward PE",       value: numberOrDash(kf.forward_pe),         raw: kf.forward_pe,       type: "pe",      info: "Price divided by projected earnings per share." },
    { label: "Price to Book",    value: numberOrDash(kf.price_to_book),      raw: kf.price_to_book,    type: "neutral", info: "Market value relative to book value of equity." },
    { label: "Profit Margin",    value: percentOrDash(kf.profit_margin),     raw: kf.profit_margin,    type: "percent", info: "Net income as a percentage of revenue." },
    { label: "Operating Margin", value: percentOrDash(kf.operating_margin),  raw: kf.operating_margin, type: "percent", info: "Operating income as a percentage of revenue." },
    { label: "Gross Margin",     value: percentOrDash(kf.gross_margin),      raw: kf.gross_margin,     type: "percent", info: "Gross profit as a percentage of revenue." },
    { label: "ROE",              value: percentOrDash(kf.return_on_equity),  raw: kf.return_on_equity, type: "percent", info: "Return generated on shareholders' equity." },
    { label: "ROA",              value: percentOrDash(kf.return_on_assets),  raw: kf.return_on_assets, type: "percent", info: "Return generated from total assets." },
    { label: "Debt to Equity",   value: numberOrDash(kf.debt_to_equity),     raw: kf.debt_to_equity,   type: "de",      info: "Leverage ratio: total debt divided by equity." },
    { label: "Current Ratio",    value: numberOrDash(kf.current_ratio),      raw: kf.current_ratio,    type: "cr",      info: "Short-term liquidity: current assets/current liabilities." },
    { label: "Market Cap",       value: kf.market_cap ? Number(kf.market_cap).toLocaleString() : "--",       raw: null, type: "neutral", info: "Total market value of outstanding shares." },
    { label: "Total Revenue",    value: kf.total_revenue ? Number(kf.total_revenue).toLocaleString() : "--", raw: null, type: "neutral", info: "Company total sales during the reported period." },
    { label: "52 Week High",     value: kf.week52_high ? formatMoney(kf.week52_high, currency) : "--",        raw: null, type: "neutral", info: "Highest traded price in the last 52 weeks." },
    { label: "52 Week Low",      value: kf.week52_low  ? formatMoney(kf.week52_low,  currency) : "--",        raw: null, type: "neutral", info: "Lowest traded price in the last 52 weeks." },
    { label: "Beta",             value: numberOrDash(kf.beta),               raw: kf.beta,             type: "neutral", info: "Volatility relative to the broader market." },
    { label: "Dividend Yield",   value: percentOrDash(kf.dividend_yield),    raw: kf.dividend_yield,   type: "percent", info: "Annual dividend income as a percentage of price." },
  ];

  return (
    <section className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/quality-stocks"
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-400 transition hover:text-indigo-600">
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Back to Quality Stocks
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-slate-900">{report.symbol}</h1>
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${sigCfg.pill}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${sigCfg.dot}`} />
              {signal || "â€”"}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            <span className="font-medium text-slate-700">{report.company_name}</span>
            <span className="mx-2 text-slate-300">Â·</span>
            <span className="font-semibold text-indigo-600">{formatMoney(report.current_price, currency)}</span>
            <span className="mx-2 text-slate-300">Â·</span>
            {report.portfolio_name}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={handleRerun} disabled={busyAction === "rerun"}
            className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-700 transition hover:bg-amber-100 disabled:opacity-50">
            {busyAction === "rerun" ? <><Spinner /> Runningâ€¦</> : <>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Re-run Report
            </>}
          </button>
          <button type="button" onClick={handleDelete} disabled={busyAction === "delete"}
            className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-600 transition hover:bg-rose-100 disabled:opacity-50">
            {busyAction === "delete" ? <><Spinner /> Deletingâ€¦</> : <>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete
            </>}
          </button>
        </div>
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      {/* AI Rating + Key Financials */}
      <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
        {/* Rating card */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-[#0f1535] to-slate-900 p-7 text-white shadow-xl">
          <div className="pointer-events-none absolute inset-0 opacity-[0.03]"
            style={{ backgroundImage: "linear-gradient(rgba(255,255,255,.5) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.5) 1px,transparent 1px)", backgroundSize: "24px 24px" }} />
          <div className="relative flex items-center gap-2">
            <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-cyan-300/80">AI Quality Rating</p>
            <InfoHint text="Model-generated score from 0 to 10 based on fundamentals, momentum, and current signal profile." />
          </div>
          <div className="relative mt-5 flex items-center gap-6">
            <div className="relative flex-shrink-0">
              <RatingRing rating={rating} />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-black leading-none">{rating.toFixed(1)}</span>
                <span className="text-[10px] font-semibold text-white/40">/ 10</span>
              </div>
            </div>
            <div className="flex-1 space-y-3">
              <div className="flex items-center gap-1">
                {[...Array(10)].map((_, i) => {
                  const filled  = i < Math.floor(rating);
                  const partial = i === Math.floor(rating) && rating % 1 > 0;
                  return (
                    <div key={i} className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                      {(filled || partial) && (
                        <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400"
                          style={{ width: filled ? "100%" : `${(rating % 1) * 100}%` }} />
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="text-sm leading-6 text-slate-300/90">
                {report.justification || "No justification was returned for this report."}
              </p>
            </div>
          </div>
          <div className="relative mt-6 flex flex-wrap gap-2 border-t border-white/10 pt-5">
            {[
              { label: "PE",   val: numberOrDash(kf.trailing_pe) },
              { label: "ROE",  val: percentOrDash(kf.return_on_equity) },
              { label: "EPS",  val: numberOrDash(kf.eps_trailing) },
              { label: "Beta", val: numberOrDash(kf.beta) },
            ].map(({ label, val }) => (
              <div key={label} className="rounded-xl bg-white/5 px-3 py-2 text-center ring-1 ring-white/10">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">{label}</p>
                <p className="mt-0.5 text-sm font-bold text-white">{val}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Key Financials */}
        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-slate-900">Key Financials</h2>
              <InfoHint text="Latest fundamental and valuation metrics used to support this quality report." />
            </div>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
              {financialRows.length} metrics
            </span>
          </div>
          <div className="max-h-[420px] overflow-y-auto rounded-2xl border border-slate-100">
            <table className="min-w-full text-sm">
              <tbody>
                {financialRows.map(({ label, value, raw, type, info }, i) => (
                  <tr key={label} className={i % 2 === 0 ? "bg-white" : "bg-slate-50/60"}>
                    <td className="px-4 py-2.5 text-slate-500">
                      <div className="flex items-center gap-2">
                        <span>{label}</span>
                        {info && <InfoHint text={info} />}
                      </div>
                    </td>
                    <td className={`px-4 py-2.5 text-right font-semibold tabular-nums ${valueColor(type, raw)}`}>
                      {value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {report.key_metrics_summary && (
            <p className="mt-3 text-xs leading-5 text-slate-400">{report.key_metrics_summary}</p>
          )}
        </div>
      </div>

      {/* Charts */}
      <div className="grid gap-5 xl:grid-cols-2">
        <ChartCard
          title="Price History"
          subtitle="Last 90 days Â· actual closing values"
          infoText="Historical closing-price trend for the stock across recent sessions."
        >
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={priceHistory} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false}
                tickFormatter={(v) => formatMoney(v, currency)} width={72} />
              <Tooltip content={<ChartTooltip currency={currency} />} />
              <Line type="monotone" dataKey="price" name="Price" stroke="#4f46e5" strokeWidth={2}
                dot={false} activeDot={{ r: 5, strokeWidth: 0 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Metrics vs Sector"
          subtitle="Revenue, EPS, PE & ROE benchmarked against sector"
          infoText="Stock metrics versus sector averages. Revenue values are normalized in billions."
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={financialBars} margin={{ top: 8, right: 16, left: 4, bottom: 4 }} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="metric" tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
              <Bar dataKey="stock"  name={report.symbol} fill="#4f46e5" radius={[5, 5, 0, 0]} maxBarSize={32} />
              <Bar dataKey="sector" name="Sector Avg"    fill="#14b8a6" radius={[5, 5, 0, 0]} maxBarSize={32} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Risks & Catalysts */}
      <div className="grid gap-5 lg:grid-cols-2">
        <InsightCard
          title="Top Risks"
          items={report.risks || []}
          variant="risk"
          infoText="Main downside factors that may pressure performance."
        />
        <InsightCard
          title="Growth Catalysts"
          items={report.catalysts || []}
          variant="catalyst"
          infoText="Potential positive triggers that can improve growth, sentiment, or valuation."
        />
      </div>
    </section>
  );
}



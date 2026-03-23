import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Loader from "../components/Loader";
import { fetchStockById } from "../api/stocks";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

/* ── Custom chart tooltip ────────────────────────────────────── */
const CustomTooltip = ({ active, payload, label, currency }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur">
      <p className="mb-1.5 text-xs font-semibold text-slate-500">{label}</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-sm">
          <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
          <span className="text-slate-500">{entry.name}:</span>
          <span className="font-bold text-slate-900">{formatMoney(entry.value, currency)}</span>
        </div>
      ))}
    </div>
  );
};

/* ── Signal badge ─────────────────────────────────────────────── */
const SignalBadge = ({ signal }) => {
  const up = signal?.toLowerCase().includes("increase");
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold ${
        up
          ? "bg-emerald-100 text-emerald-700"
          : "bg-rose-100 text-rose-600"
      }`}
    >
      <span>{up ? "▲" : "▼"}</span>
      {signal || "—"}
    </span>
  );
};

/* ── Discount badge ───────────────────────────────────────────── */
const DiscountBadge = ({ level }) => {
  const styles = {
    HIGH: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    MEDIUM: "bg-amber-100 text-amber-700 ring-amber-200",
    LOW: "bg-rose-100 text-rose-600 ring-rose-200",
    UNKNOWN: "bg-slate-100 text-slate-500 ring-slate-200",
  };
  return (
    <span className={`rounded-full px-3 py-0.5 text-xs font-bold uppercase tracking-wide ring-1 ${styles[level] || styles.UNKNOWN}`}>
      {level || "—"}
    </span>
  );
};

/* ── Metric card ─────────────────────────────────────────────── */
const MetricCard = ({ label, value, sub, accent = "indigo", large = false }) => {
  const accents = {
    indigo: "border-indigo-100 bg-gradient-to-br from-white to-indigo-50/40",
    emerald: "border-emerald-100 bg-gradient-to-br from-white to-emerald-50/40",
    rose: "border-rose-100 bg-gradient-to-br from-white to-rose-50/40",
    amber: "border-amber-100 bg-gradient-to-br from-white to-amber-50/40",
    violet: "border-violet-100 bg-gradient-to-br from-white to-violet-50/40",
    slate: "border-slate-100 bg-white",
  };
  return (
    <div className={`rounded-2xl border p-5 shadow-sm ${accents[accent]}`}>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`mt-2 font-bold text-slate-900 ${large ? "text-3xl" : "text-xl"}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
    </div>
  );
};

/* ════════════════════════════════════════════════════════════════
   Main Page
════════════════════════════════════════════════════════════════ */
export default function StockDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (id && !/^\d+$/.test(String(id))) {
      navigate(`/stocks/live/${encodeURIComponent(id)}`, {
        replace: true,
        state: { from: `${location.pathname}${location.search}` },
      });
      return;
    }

    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchStockById(id);
        setStock(data);
      } catch {
        setError("Failed to load stock details.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id, location.pathname, location.search, navigate]);

  const chartData = useMemo(() => {
    const graph = stock?.analytics?.graph_data;
    const dates = graph?.dates || [];
    const prices = graph?.price || [];
    const movingAvg = graph?.moving_avg || [];
    return dates.map((date, i) => ({
      date,
      price: prices[i],
      moving_avg: movingAvg[i],
    }));
  }, [stock]);

  if (loading)
    return (
      <div className="flex items-center justify-center py-20">
        <Loader />
      </div>
    );

  if (error)
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        {error}
      </div>
    );

  if (!stock)
    return (
      <div className="rounded-xl bg-white px-4 py-8 text-center text-sm text-slate-400 shadow-sm ring-1 ring-slate-100">
        Stock not found.
      </div>
    );

  const backQuery = stock.portfolio ? `?portfolio=${stock.portfolio}` : "";
  const currency = currencyCodeFromItem(stock);
  const hasPrediction = stock.prediction_status === "ok";
  const predMissing =
    stock.prediction_status === "insufficient_data" ? "Insufficient Data" : "Unavailable";

  /* price change from historical series */
  const prices = stock.analytics?.graph_data?.price || [];
  const priceChange =
    prices.length >= 2
      ? (((prices[prices.length - 1] - prices[0]) / prices[0]) * 100).toFixed(2)
      : null;
  const priceUp = priceChange !== null && Number(priceChange) >= 0;

  /* chart Y domain with padding */
  const chartMin = prices.length ? Math.min(...prices) * 0.97 : "auto";
  const chartMax = prices.length ? Math.max(...prices) * 1.03 : "auto";

  /* forecast change */
  const forecastUp =
    hasPrediction && Number(stock.expected_change_pct || 0) >= 0;

  return (
    <section className="space-y-8">

      {/* ── Back + title ── */}
      <div className="flex items-center justify-between">
        <div>
          <Link
            to={`/stocks${backQuery}`}
            className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-slate-400 hover:text-indigo-600 transition-colors"
          >
            ← Back to Stocks
          </Link>
          <h1 className="text-2xl font-bold text-slate-900">{stock.company_name}</h1>
          <p className="mt-0.5 font-mono text-sm text-slate-400">{stock.symbol}</p>
        </div>
        <DiscountBadge level={stock.analytics?.discount_level} />
      </div>

      {/* ── Hero price strip ── */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-violet-950 p-8 text-white shadow-xl">
        {/* decorative circle */}
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-indigo-500/10" />
        <div className="pointer-events-none absolute -bottom-12 -left-12 h-48 w-48 rounded-full bg-violet-500/10" />

        <div className="relative grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Current Price</p>
            <p className="mt-2 text-4xl font-extrabold">{formatMoney(stock.current_price, currency)}</p>
            {priceChange !== null && (
              <p className={`mt-1.5 text-sm font-medium ${priceUp ? "text-emerald-400" : "text-rose-400"}`}>
                {priceUp ? "+" : ""}{priceChange}% (1-year)
              </p>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">1-Year Range</p>
            <p className="mt-2 text-lg font-bold">{formatMoney(stock.min_price, currency)}</p>
            <p className="text-xs text-slate-500">Min</p>
            <p className="mt-1 text-lg font-bold">{formatMoney(stock.max_price, currency)}</p>
            <p className="text-xs text-slate-500">Max</p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Next-Day Forecast</p>
            <p className="mt-2 text-3xl font-extrabold">
              {hasPrediction ? formatMoney(stock.predicted_price_1d, currency) : <span className="text-xl text-slate-500">{predMissing}</span>}
            </p>
            {hasPrediction && (
              <p className={`mt-1.5 text-sm font-semibold ${forecastUp ? "text-emerald-400" : "text-rose-400"}`}>
                {forecastUp ? "+" : ""}{Number(stock.expected_change_pct || 0).toFixed(2)}% expected
              </p>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Opportunity Score</p>
            <p className="mt-2 text-4xl font-extrabold text-amber-400">
              {stock.analytics?.opportunity_score ?? "—"}
            </p>
            <p className="mt-1.5 text-xs text-slate-400">
              PE&nbsp;
              <span className="font-bold text-slate-200">{stock.analytics?.pe_ratio ?? "—"}</span>
              &nbsp;· Sector&nbsp;
              <span className="font-bold text-slate-200">{stock.sector || "—"}</span>
            </p>
          </div>
        </div>
      </div>

      {/* ── Analytics metrics row ── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Signal"
          value={
            hasPrediction ? (
              <SignalBadge signal={stock.direction_signal} />
            ) : (
              <span className="text-base text-slate-400">{predMissing}</span>
            )
          }
          sub="1D linear trend direction"
          accent="slate"
        />
        <MetricCard
          label="Model Confidence (R²)"
          value={hasPrediction ? Number(stock.model_confidence_r2 || 0).toFixed(3) : predMissing}
          sub="1 = perfect fit"
          accent={hasPrediction && Number(stock.model_confidence_r2) > 0.7 ? "emerald" : "amber"}
        />
        <MetricCard
          label="Discount Level"
          value={<DiscountBadge level={stock.analytics?.discount_level} />}
          sub="Based on price vs moving avg"
          accent="slate"
        />
        <MetricCard
          label="PE Ratio"
          value={stock.analytics?.pe_ratio ?? "—"}
          sub="Trailing / forward PE"
          accent="violet"
        />
      </div>

      {/* ── Opportunity chart ── */}
      <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-800">Opportunity Graph</h2>
            <p className="mt-0.5 text-xs text-slate-400">1-year daily close · 5-day moving average</p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5 text-indigo-600">
              <span className="h-2 w-4 rounded bg-indigo-500" />Price
            </span>
            <span className="flex items-center gap-1.5 text-emerald-600">
              <span className="h-2 w-4 rounded bg-emerald-500" />Moving Avg
            </span>
          </div>
        </div>

        <div className="mt-5 h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => formatMoney(v, currency)}
                domain={[chartMin, chartMax]}
                width={90}
              />
              <Tooltip content={<CustomTooltip currency={currency} />} />
              <Legend wrapperStyle={{ fontSize: "12px" }} />
              <Area
                type="monotone"
                dataKey="price"
                name="Price"
                stroke="#6366f1"
                strokeWidth={2.5}
                fill="url(#priceGrad)"
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="moving_avg"
                name="Moving Avg"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                strokeDasharray="4 3"
              />
              {/* Mark current (last) price */}
              {chartData.length > 0 && (
                <ReferenceLine
                  y={chartData[chartData.length - 1]?.price}
                  stroke="#6366f1"
                  strokeDasharray="4 2"
                  strokeOpacity={0.4}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Prediction detail card ── */}
      {hasPrediction && (
        <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <h2 className="text-base font-semibold text-slate-800">Prediction Detail</h2>
          <p className="mt-0.5 text-xs text-slate-400">Based on 1-year linear regression trend. For informational purposes only.</p>

          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Predicted (1D)</p>
              <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(stock.predicted_price_1d, currency)}</p>
            </div>
            <div className={`rounded-xl p-4 ${forecastUp ? "bg-emerald-50" : "bg-rose-50"}`}>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Expected Change</p>
              <p className={`mt-2 text-xl font-bold ${forecastUp ? "text-emerald-700" : "text-rose-600"}`}>
                {forecastUp ? "+" : ""}{Number(stock.expected_change_pct || 0).toFixed(2)}%
              </p>
            </div>
            <div className="rounded-xl bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Signal</p>
              <div className="mt-2">
                <SignalBadge signal={stock.direction_signal} />
              </div>
            </div>
            <div className="rounded-xl bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Confidence R²</p>
              <p className="mt-2 text-xl font-bold text-slate-900">
                {Number(stock.model_confidence_r2 || 0).toFixed(3)}
              </p>
            </div>
          </div>

          {/* Visual confidence bar */}
          <div className="mt-5">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span>Model Confidence</span>
              <span className="font-semibold text-slate-700">{(Number(stock.model_confidence_r2 || 0) * 100).toFixed(1)}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-700"
                style={{ width: `${Math.min(100, Number(stock.model_confidence_r2 || 0) * 100).toFixed(1)}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ── Quick actions ── */}
      <div className="flex flex-wrap gap-3">
        <Link
          to={`/stocks${backQuery}`}
          className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 hover:border-slate-300"
        >
          ← All Stocks
        </Link>
        <Link
          to="/prediction"
          className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:from-indigo-700 hover:to-violet-700"
        >
          Run ML Prediction →
        </Link>
      </div>
    </section>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Loader from "../components/Loader";
import { fetchStockById } from "../api/stocks";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

/* Custom chart tooltip */
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

/* Signal badge */
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
      {signal || "-"}
    </span>
  );
};

/* Discount badge */
const DiscountBadge = ({ level }) => {
  const styles = {
    HIGH: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    MEDIUM: "bg-amber-100 text-amber-700 ring-amber-200",
    LOW: "bg-rose-100 text-rose-600 ring-rose-200",
    UNKNOWN: "bg-slate-100 text-slate-500 ring-slate-200",
  };
  return (
    <span className={`rounded-full px-3 py-0.5 text-xs font-bold uppercase tracking-wide ring-1 ${styles[level] || styles.UNKNOWN}`}>
      {level || "-"}
    </span>
  );
};

const SentimentBadge = ({ score, label }) => {
  if (score === null || score === undefined) {
    return (
      <span className="rounded-full px-3 py-0.5 text-xs font-bold uppercase tracking-wide ring-1 bg-slate-100 text-slate-500 ring-slate-200">
        No Data
      </span>
    );
  }
  const styles =
    Number(score) >= 6.5
      ? "bg-emerald-100 text-emerald-700 ring-emerald-200"
      : Number(score) >= 4.0
      ? "bg-amber-100 text-amber-700 ring-amber-200"
      : "bg-rose-100 text-rose-600 ring-rose-200";
  return (
    <span className={`rounded-full px-3 py-0.5 text-xs font-bold uppercase tracking-wide ring-1 ${styles}`}>
      {Number(score).toFixed(2)} ({label || "Neutral"})
    </span>
  );
};

/* Metric card */
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

/* Main page */
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
  const hasPrediction =
    stock.prediction_status === "ok" ||
    stock.prediction_status === "ready" ||
    (stock.predicted_price_1d !== null && stock.predicted_price_1d !== undefined);
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
    <section className="mx-auto max-w-6xl space-y-8 px-4 py-8">

      {/* Back + title */}
      <div className="flex items-center justify-between">
        <div>
          <Link
            to={`/stocks${backQuery}`}
            className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-slate-400 hover:text-indigo-600 transition-colors"
          >
            &larr; Back to Stocks
          </Link>
          <h1 className="text-2xl font-bold text-slate-900">{stock.company_name}</h1>
          <p className="mt-0.5 font-mono text-sm text-slate-400">{stock.symbol}</p>
        </div>
        <DiscountBadge level={stock.analytics?.discount_level} />
      </div>

      {/* Hero price strip */}
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
            {stock.sentiment_score !== null && stock.sentiment_score !== undefined && (
              <p className={`mt-2 text-sm font-medium ${
                Number(stock.sentiment_score) >= 6.5
                  ? "text-emerald-400"
                  : Number(stock.sentiment_score) >= 4.0
                  ? "text-amber-400"
                  : "text-rose-400"
              }`}>
                Sentiment: {Number(stock.sentiment_score).toFixed(2)}
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
              {stock.analytics?.opportunity_score ?? "-"}
            </p>
            <p className="mt-1.5 text-xs text-slate-400">
              PE&nbsp;
              <span className="font-bold text-slate-200">{stock.analytics?.pe_ratio ?? "-"}</span>
              &nbsp;| Sector&nbsp;
              <span className="font-bold text-slate-200">{stock.sector || "-"}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Analytics metrics row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
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
          label="Model Confidence (R2)"
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
          value={stock.analytics?.pe_ratio ?? "-"}
          sub="Trailing / forward PE"
          accent="violet"
        />
        <MetricCard
          label="Sentiment"
          value={<SentimentBadge score={stock.sentiment_score} label={stock.sentiment_label} />}
          sub={stock.sentiment_source ? `Source: ${stock.sentiment_source}` : "Source unavailable"}
          accent="amber"
        />
      </div>

      {/* Prediction detail card */}
      {hasPrediction && (
        <div className="relative rounded-3xl bg-gradient-to-br from-slate-50 via-white to-slate-50 p-8 shadow-lg ring-1 ring-slate-100 overflow-hidden">
          {/* Decorative accent */}
          <div className="absolute top-0 right-0 -mr-20 -mt-20 h-40 w-40 rounded-full bg-indigo-100/40" />
          <div className="absolute bottom-0 left-0 -ml-32 -mb-16 h-64 w-64 rounded-full bg-violet-100/20" />
          
          <div className="relative">
            <h2 className="text-lg font-bold text-slate-900">ML Prediction Analysis</h2>
            <p className="mt-1 text-xs text-slate-500">Linear regression trend model. Updated daily for informational purposes.</p>

            <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-indigo-300 hover:shadow-md">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Predicted Price (1D)</p>
                <p className="mt-3 text-2xl font-extrabold text-indigo-600">{formatMoney(stock.predicted_price_1d, currency)}</p>
                <p className="mt-1 text-xs text-slate-400">Next 24 hours</p>
              </div>
              
              <div className={`group rounded-2xl border-2 p-5 transition hover:shadow-md ${
                forecastUp 
                  ? "border-emerald-200 bg-gradient-to-br from-emerald-50 to-white hover:border-emerald-300" 
                  : "border-rose-200 bg-gradient-to-br from-rose-50 to-white hover:border-rose-300"
              }`}>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Expected Change</p>
                <p className={`mt-3 text-2xl font-extrabold ${forecastUp ? "text-emerald-600" : "text-rose-600"}`}>
                  {forecastUp ? "+ " : "- "}{Number(stock.expected_change_pct || 0).toFixed(2)}%
                </p>
                <p className="mt-1 text-xs text-slate-400">From current price</p>
              </div>
              
              <div className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-violet-300 hover:shadow-md">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Trend Signal</p>
                <div className="mt-3">
                  <SignalBadge signal={stock.direction_signal} />
                </div>
                <p className="mt-2 text-xs text-slate-400">Direction indicator</p>
              </div>
              
              <div className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-amber-300 hover:shadow-md">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Model Confidence (R2)</p>
                <p className="mt-3 text-2xl font-extrabold text-amber-600">
                  {(Number(stock.model_confidence_r2 || 0) * 100).toFixed(1)}%
                </p>
                <p className="mt-1 text-xs text-slate-400">Model fit quality</p>
              </div>
            </div>

            {/* Enhanced confidence visualization */}
            <div className="mt-8 rounded-2xl bg-white border border-slate-200 p-6">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-slate-700">Model Confidence Score</span>
                <span className="inline-block px-3 py-1 rounded-lg bg-amber-100 text-amber-700 text-sm font-bold">
                  {(Number(stock.model_confidence_r2 || 0) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-amber-500 transition-all duration-1000 shadow-lg"
                  style={{ width: `${Math.min(100, Number(stock.model_confidence_r2 || 0) * 100).toFixed(1)}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                {Number(stock.model_confidence_r2 || 0) > 0.8
                  ? "Excellent fit - highly reliable trend"
                  : Number(stock.model_confidence_r2 || 0) > 0.6
                  ? "Good fit - moderately reliable"
                  : "Fair fit - use with caution"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Opportunity chart */}
      <div className="relative rounded-3xl bg-white p-8 shadow-lg ring-1 ring-slate-100 overflow-hidden">
        {/* Subtle accent line at top */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 via-violet-500 to-transparent" />
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Opportunity Graph</h2>
            <p className="mt-0.5 text-xs text-slate-500">1-year daily close · 5-day moving average</p>
          </div>
        </div>

        <div className="mt-6 h-96 w-full rounded-2xl bg-gradient-to-b from-slate-50 to-white p-4 border border-slate-100">
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
      {/* Quick actions */}
      <div className="flex flex-wrap gap-4">
        <Link
          to={`/stocks${backQuery}`}
          className="group relative inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-md transition hover:shadow-lg hover:border-slate-400 hover:bg-slate-50"
        >
          <span className="transition group-hover:-translate-x-0.5">&larr;</span>
          <span>All Stocks</span>
        </Link>
        <Link
          to="/prediction"
          className="group relative inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg transition hover:from-indigo-700 hover:to-violet-700 hover:shadow-xl overflow-hidden"
        >
          <span className="absolute inset-0 bg-gradient-to-r from-white/20 to-transparent opacity-0 transition group-hover:opacity-100" />
          <span className="relative">Run ML Prediction</span>
          <span className="relative transition group-hover:translate-x-0.5">&rarr;</span>
        </Link>
      </div>
    </section>
  );
}



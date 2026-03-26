import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Loader from "../components/Loader";
import {
  deleteQualityStock,
  fetchQualityStockDetail,
  rerunQualityStockReport,
} from "../api/stocks";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

const signalStyles = {
  BUY: "bg-emerald-100 text-emerald-700",
  HOLD: "bg-amber-100 text-amber-700",
  SELL: "bg-rose-100 text-rose-600",
};

const numberOrDash = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
};

const percentOrDash = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const numeric = Number(value);
  const normalized = Math.abs(numeric) <= 2 ? numeric * 100 : numeric;
  return `${normalized.toFixed(2)}%`;
};

export default function QualityStockReport() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");

  const loadReport = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchQualityStockDetail(id);
      setReport(data);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load the quality stock report.");
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, [id]);

  const priceHistory = useMemo(() => report?.graphs_data?.price_history || [], [report]);
  const financialBars = useMemo(
    () =>
      (report?.graphs_data?.financial_metrics || []).map((row) => ({
        metric: row.metric,
        stock: row.stock_value,
        sector: row.sector_average,
      })),
    [report]
  );

  const handleRerun = async () => {
    setBusyAction("rerun");
    setError("");
    try {
      const response = await rerunQualityStockReport(id);
      setReport(response);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to regenerate this report.");
    } finally {
      setBusyAction("");
    }
  };

  const handleDelete = async () => {
    setBusyAction("delete");
    setError("");
    try {
      await deleteQualityStock(id);
      navigate("/quality-stocks");
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to delete this report.");
      setBusyAction("");
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader />
      </div>
    );
  }

  if (error && !report) {
    return <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>;
  }

  if (!report) {
    return <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">Report not found.</div>;
  }

  const signal = String(report.buy_signal || report.recommended_action || "").toUpperCase();
  const rating = Math.max(0, Math.min(10, Number(report.ai_rating || 0)));
  const currency = currencyCodeFromItem(report);
  const keyFinancials = report.key_financials || {};
  const financialRows = [
    ["Revenue Growth", percentOrDash(keyFinancials.revenue_growth)],
    ["Earnings Growth", percentOrDash(keyFinancials.earnings_growth)],
    ["EPS", numberOrDash(keyFinancials.eps_trailing)],
    ["Forward EPS", numberOrDash(keyFinancials.eps_forward)],
    ["PE Ratio", numberOrDash(keyFinancials.trailing_pe)],
    ["Forward PE", numberOrDash(keyFinancials.forward_pe)],
    ["Price to Book", numberOrDash(keyFinancials.price_to_book)],
    ["Profit Margin", percentOrDash(keyFinancials.profit_margin)],
    ["Operating Margin", percentOrDash(keyFinancials.operating_margin)],
    ["Gross Margin", percentOrDash(keyFinancials.gross_margin)],
    ["ROE", percentOrDash(keyFinancials.return_on_equity)],
    ["ROA", percentOrDash(keyFinancials.return_on_assets)],
    ["Debt to Equity", numberOrDash(keyFinancials.debt_to_equity)],
    ["Current Ratio", numberOrDash(keyFinancials.current_ratio)],
    ["Market Cap", keyFinancials.market_cap ? Number(keyFinancials.market_cap).toLocaleString() : "—"],
    ["Total Revenue", keyFinancials.total_revenue ? Number(keyFinancials.total_revenue).toLocaleString() : "—"],
    ["52 Week High", keyFinancials.week52_high ? formatMoney(keyFinancials.week52_high, currency) : "—"],
    ["52 Week Low", keyFinancials.week52_low ? formatMoney(keyFinancials.week52_low, currency) : "—"],
    ["Beta", numberOrDash(keyFinancials.beta)],
    ["Dividend Yield", percentOrDash(keyFinancials.dividend_yield)],
  ];

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/quality-stocks" className="text-xs font-semibold text-slate-400 transition hover:text-indigo-600">
            ← Back to Quality Stocks
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold text-slate-900">{report.symbol}</h1>
            <span className={`inline-flex rounded-full px-3 py-1 text-sm font-semibold ${signalStyles[signal] || "bg-slate-100 text-slate-600"}`}>
              {signal || "—"}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {report.company_name} · {formatMoney(report.current_price, currency)} · {report.portfolio_name}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRerun}
            disabled={busyAction === "rerun"}
            className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-700 transition hover:bg-amber-100 disabled:opacity-50"
          >
            {busyAction === "rerun" ? "Running..." : "Re-run Report"}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={busyAction === "delete"}
            className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-600 transition hover:bg-rose-100 disabled:opacity-50"
          >
            {busyAction === "delete" ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 p-8 text-white shadow-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.25em] text-cyan-200">AI Quality Rating</p>
          <div className="mt-5 flex items-center gap-5">
            <div className="relative h-28 w-28 rounded-full border border-white/10 bg-white/5 p-3">
              <div className="flex h-full w-full items-center justify-center rounded-full border border-white/10 bg-slate-950/35 text-3xl font-bold">
                {rating.toFixed(1)}
              </div>
            </div>
            <div className="flex-1">
              <div className="h-4 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-emerald-400 to-lime-300"
                  style={{ width: `${rating * 10}%` }}
                />
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-200">{report.justification || "No justification was returned for this report."}</p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <h2 className="text-lg font-bold text-slate-900">Key Financials</h2>
          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100">
            <table className="min-w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {financialRows.map(([label, value]) => (
                  <tr key={label} className="bg-white">
                    <td className="px-4 py-3 font-medium text-slate-600">{label}</td>
                    <td className="px-4 py-3 text-right font-semibold text-slate-900">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-xs text-slate-500">{report.key_metrics_summary}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <div className="mb-4">
            <h2 className="text-lg font-bold text-slate-900">Price History</h2>
            <p className="mt-1 text-xs text-slate-500">Last 90 days of actual closing values.</p>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceHistory} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(value) => formatMoney(value, currency)} />
                <Tooltip formatter={(value) => formatMoney(value, currency)} />
                <Line type="monotone" dataKey="price" name="Price" stroke="#4f46e5" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <div className="mb-4">
            <h2 className="text-lg font-bold text-slate-900">Financial Metrics vs Sector</h2>
            <p className="mt-1 text-xs text-slate-500">Revenue, EPS, PE, and ROE benchmarked against sector averages.</p>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={financialBars} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="metric" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="stock" name={report.symbol} fill="#4f46e5" radius={[6, 6, 0, 0]} />
                <Bar dataKey="sector" name="Sector Avg" fill="#14b8a6" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <h2 className="text-lg font-bold text-slate-900">Top Risks</h2>
          <div className="mt-4 space-y-3">
            {(report.risks || []).map((risk, index) => (
              <div key={`${risk}-${index}`} className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {risk}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
          <h2 className="text-lg font-bold text-slate-900">Growth Catalysts</h2>
          <div className="mt-4 space-y-3">
            {(report.catalysts || []).map((catalyst, index) => (
              <div key={`${catalyst}-${index}`} className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {catalyst}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

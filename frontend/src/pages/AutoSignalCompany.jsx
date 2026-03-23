import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { fetchCompanyDetail } from "../api/autosignal";

const SIGNAL_COLORS = {
  BUY: { bg: "bg-green-100", text: "text-green-800", border: "border-green-300" },
  NEUTRAL: { bg: "bg-amber-100", text: "text-amber-800", border: "border-amber-300" },
  RISK_ALERT: { bg: "bg-rose-100", text: "text-rose-800", border: "border-rose-300" },
};

const SENTIMENT_BG = (score) => {
  if (score >= 7) return "bg-green-500";
  if (score >= 5) return "bg-yellow-500";
  return "bg-red-500";
};

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 flex flex-col gap-1 shadow-sm">
      <span className="text-xs text-slate-600 uppercase tracking-wide">{label}</span>
      <span className={`text-2xl font-bold ${color || "text-slate-900"}`}>{value}</span>
      {sub && <span className="text-xs text-slate-600">{sub}</span>}
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs shadow-lg">
      <p className="text-slate-300 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(2) : p.value}
        </p>
      ))}
    </div>
  );
}

function renderInlineBold(text) {
  const parts = String(text || "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    const boldMatch = part.match(/^\*\*([^*]+)\*\*$/);
    if (boldMatch) {
      return <strong key={`b-${index}`} className="font-semibold text-slate-900">{boldMatch[1]}</strong>;
    }
    return <span key={`t-${index}`}>{part}</span>;
  });
}

function formatReportText(reportText) {
  if (!reportText) return null;

  const blocks = String(reportText)
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);

  return blocks.map((block, index) => {
    const headingMatch = block.match(/^\*\*([^*]+)\*\*$/);
    if (headingMatch) {
      const isMainTitle = index === 0;
      return isMainTitle ? (
        <h3 key={`h-${index}`} className="text-base font-semibold text-slate-900">
          {headingMatch[1]}
        </h3>
      ) : (
        <h4 key={`h-${index}`} className="text-sm font-semibold text-slate-800 pt-1">
          {headingMatch[1]}
        </h4>
      );
    }

    return (
      <p key={`p-${index}`} className="text-sm leading-8 text-slate-700">
        {renderInlineBold(block)}
      </p>
    );
  });
}

export default function AutoSignalCompany() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [chartMode, setChartMode] = useState("price");

  useEffect(() => {
    const load = async () => {
      try {
        const result = await fetchCompanyDetail(slug);
        if (result.error) {
          setError(result.error);
        } else {
          setData(result);
        }
      } catch (err) {
        setError(
          err?.response?.data?.error ||
          err?.message ||
          "Failed to load company data"
        );
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [slug]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-slate-500 text-sm">Loading company data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <span className="text-red-600">{error}</span>
        <button
          onClick={() => navigate("/autosignal")}
          className="text-sm text-blue-600 hover:text-blue-500"
        >
          Back to AutoSignal
        </button>
      </div>
    );
  }

  const colors = SIGNAL_COLORS[data.signal] || SIGNAL_COLORS.NEUTRAL;
  const history = data.stock_history || [];

  // Step 1: Add sentiment data to chartData
  const chartData = history.map((row) => ({
    date: row.date?.slice(5),
    Close: row.close ? parseFloat(row.close.toFixed(2)) : null,
    MA20: row.ma_20 ? parseFloat(row.ma_20.toFixed(2)) : null,
    MA5: row.ma_5 ? parseFloat(row.ma_5.toFixed(2)) : null,
    RSI: row.rsi_14 ? parseFloat(row.rsi_14.toFixed(2)) : null,
    Volatility: row.volatility_20d ? parseFloat((row.volatility_20d * 100).toFixed(3)) : null,
    Return: row.daily_return ? parseFloat((row.daily_return * 100).toFixed(3)) : null,
    Sentiment: data.sentiment_score, // constant line for comparison
  }));

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => navigate("/autosignal")}
        className="flex items-center gap-1 text-sm text-slate-600 hover:text-slate-800 w-fit transition-colors"
      >
        &larr; Back to Sector Overview
      </button>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">{data.company}</h1>
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${colors.bg} ${colors.text} ${colors.border}`}>
              {data.signal}
            </span>
          </div>
          <p className="text-slate-600 text-sm mt-1">{data.ticker} · {data.report_date}</p>
        </div>
        <div className="flex items-end flex-col gap-1">
          <span className="text-xs text-slate-600">Current Price</span>
          <span className="text-3xl font-bold text-slate-900">
            Rs. {data.close?.toFixed(2)}
          </span>
          <span className={`text-xs font-medium ${data.price_vs_ma20 < 0 ? "text-red-500" : "text-green-600"}`}>
            {(data.price_vs_ma20 * 100).toFixed(2)}% vs MA20
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          label="Sentiment"
          value={`${data.sentiment_score}/10`}
          sub="FinBERT score"
          color={data.sentiment_score >= 7 ? "text-green-600" : data.sentiment_score >= 5 ? "text-yellow-600" : "text-red-600"}
        />
        <StatCard
          label="RSI (14)"
          value={data.rsi_14?.toFixed(1)}
          sub={data.rsi_14 < 30 ? "Oversold" : data.rsi_14 > 70 ? "Overbought" : "Neutral"}
          color={data.rsi_14 < 30 ? "text-red-600" : data.rsi_14 > 70 ? "text-green-600" : "text-slate-900"}
        />
        <StatCard
          label="Profit Margin"
          value={data.profit_margin_pct != null ? `${data.profit_margin_pct}%` : "N/A"}
          sub="Net margin"
        />
        <StatCard
          label="Revenue Growth"
          value={data.revenue_growth_pct != null ? `${data.revenue_growth_pct}%` : "N/A"}
          sub="YoY"
          color={data.revenue_growth_pct < 0 ? "text-red-600" : "text-green-600"}
        />
        <StatCard
          label="Trailing PE"
          value={data.trailing_pe != null ? data.trailing_pe.toFixed(1) : "N/A"}
          sub="Price/Earnings"
        />
        <StatCard
          label="Profitability"
          value={`${data.profitability_score}/10`}
          sub="Composite score"
          color={data.profitability_score >= 7 ? "text-green-600" : data.profitability_score >= 5 ? "text-yellow-600" : "text-red-600"}
        />
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
            Market Intelligence Chart
          </h2>
          <div className="flex gap-1 bg-slate-100/90 rounded-lg p-1 border border-slate-300">
            {/* Step 2: Add sentiment mode to buttons */}
            {["price", "rsi", "return", "sentiment"].map((mode) => (
              <button
                key={mode}
                onClick={() => setChartMode(mode)}
                className={`px-3 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  chartMode === mode ? "bg-blue-600 text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#64748b", fontSize: 10 }}
              tickLine={false}
              interval={9}
            />
            {/* Step 3: Implement new chart logic with yAxisId to handle dual scaling */}
            {chartMode === "price" && (
              <>
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} domain={["auto", "auto"]} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: "11px", color: "#64748b" }} />
                <Line type="monotone" dataKey="Close" stroke="#2563eb" dot={false} strokeWidth={2} name="Price" />
                <Line type="monotone" dataKey="MA20" stroke="#f59e0b" dot={false} strokeWidth={1.5} strokeDasharray="4 4" name="MA20" />
                <Line type="monotone" dataKey="MA5" stroke="#16a34a" dot={false} strokeWidth={1} strokeDasharray="2 2" name="MA5" />
              </>
            )}
            {chartMode === "rsi" && (
              <>
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} domain={[0, 100]} />
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="RSI" stroke="#7c3aed" dot={false} strokeWidth={2} name="RSI (14)" />
              </>
            )}
            {chartMode === "return" && (
              <>
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="Return" stroke="#059669" dot={false} strokeWidth={1.5} name="Daily Return %" />
              </>
            )}
            {chartMode === "sentiment" && (
              <>
                <YAxis yAxisId="price" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} domain={["auto", "auto"]} />
                <YAxis yAxisId="sentiment" orientation="right" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} domain={[0, 10]} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: "11px", color: "#9ca3af" }} />
                <Line yAxisId="price" type="monotone" dataKey="Close" stroke="#3b82f6" dot={false} strokeWidth={2} name="Price" />
                <Line yAxisId="sentiment" type="monotone" dataKey="Sentiment" stroke="#f59e0b" dot={false} strokeWidth={2} strokeDasharray="5 5" name="AI Sentiment Score" />
              </>
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-3 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
              AI Company Report
            </h2>
            <span className="text-xs text-slate-500">{data.generated_by}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-full rounded-full h-1.5 bg-slate-200">
              <div
                className={`h-1.5 rounded-full ${SENTIMENT_BG(data.sentiment_score)}`}
                style={{ width: `${(data.sentiment_score / 10) * 100}%` }}
              />
            </div>
            <span className="text-slate-900 font-bold text-sm shrink-0">{data.sentiment_score}/10</span>
          </div>
          <div className="space-y-4">
            {formatReportText(data.report_text)}
          </div>
          <div className="mt-2 pt-3 border-t border-slate-200">
            <p className="text-xs text-slate-500">{data.reasoning}</p>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-3 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
            Recent Corporate Events
          </h2>
          <div className="flex flex-col divide-y divide-slate-200">
            {data.recent_events?.map((event, i) => (
              <div key={i} className="py-3 flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">
                    {event.broadcast_date?.slice(0, 11)}
                  </span>
                  {event.attachment_url && (
                    <a
                      href={event.attachment_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:text-blue-500"
                    >
                      PDF
                    </a>
                  )}
                </div>
                <p className="text-sm text-slate-700">{event.subject}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">
          Financial Summary
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Market Cap</span>
            <span className="text-slate-900 font-medium">
              {data.market_cap_cr ? `Rs. ${data.market_cap_cr.toLocaleString()} Cr` : "N/A"}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">EPS (Trailing)</span>
            <span className="text-slate-900 font-medium">
              {data.eps_trailing != null ? `Rs. ${data.eps_trailing}` : "N/A"}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Debt / Equity</span>
            <span className={`font-medium ${data.debt_to_equity > 1 ? "text-red-600" : "text-green-600"}`}>
              {data.debt_to_equity != null ? data.debt_to_equity.toFixed(2) : "N/A"}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Return on Equity</span>
            <span className="text-slate-900 font-medium">
              {data.roe_pct != null ? `${data.roe_pct}%` : "N/A"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

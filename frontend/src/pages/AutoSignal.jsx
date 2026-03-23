import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchSectorHeatmap,
  fetchSectorReport,
  fetchEvents,
  fetchSectorInsights,
} from "../api/autosignal";

const SIGNAL_COLORS = {
  BUY:        { bg: "bg-green-500/20", text: "text-green-400", border: "border-green-500/30" },
  NEUTRAL:    { bg: "bg-yellow-500/20", text: "text-yellow-400", border: "border-yellow-500/30" },
  RISK_ALERT: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/30" },
};

const SENTIMENT_BG = (score) => {
  if (score >= 7) return "bg-green-500";
  if (score >= 5) return "bg-yellow-500";
  return "bg-red-500";
};

const EVENT_COLORS = {
  LITIGATION:           "text-red-400 bg-red-500/10",
  INVESTOR_MEET:        "text-blue-400 bg-blue-500/10",
  EARNINGS:             "text-purple-400 bg-purple-500/10",
  EV_LAUNCH:            "text-green-400 bg-green-500/10",
  PRODUCTION_EXPANSION: "text-cyan-400 bg-cyan-500/10",
  DIVIDEND:             "text-emerald-400 bg-emerald-500/10",
  GENERAL:              "text-gray-400 bg-gray-500/10",
};

const COMPANY_SLUGS = {
  "Maruti Suzuki":       "maruti-suzuki",
  "Tata Motors":         "tata-motors",
  "Mahindra & Mahindra": "mahindra-mahindra",
  "Bajaj Auto":          "bajaj-auto",
  "Hero MotoCorp":       "hero-motocorp",
};

function SentimentCard({ company, sentiment_score, signal, rsi_14, price_vs_ma20_pct, profitability, slug }) {
  const navigate = useNavigate();
  const colors = SIGNAL_COLORS[signal] || SIGNAL_COLORS.NEUTRAL;
  return (
    <div
      onClick={() => navigate(`/autosignal/${slug}`)}
      className={`rounded-xl border p-4 ${colors.bg} ${colors.border} flex flex-col gap-2 cursor-pointer hover:opacity-80 transition-opacity`}
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold text-white text-sm">{company}</span>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${colors.bg} ${colors.text} border ${colors.border}`}>
          {signal.replace("_", " ")}
        </span>
      </div>
      <div className="flex items-end gap-2">
        <span className="text-3xl font-bold text-white">{sentiment_score}</span>
        <span className="text-gray-400 text-sm mb-1">/10</span>
      </div>
      <div className="w-full rounded-full h-1.5 bg-gray-700">
        <div
          className={`h-1.5 rounded-full ${SENTIMENT_BG(sentiment_score)}`}
          style={{ width: `${(sentiment_score / 10) * 100}%` }}
        />
      </div>
      <div className="grid grid-cols-3 gap-1 mt-1 text-xs text-gray-400">
        <div>RSI <span className="text-white font-medium">{rsi_14}</span></div>
        <div>vs MA20 <span className={price_vs_ma20_pct < 0 ? "text-red-400 font-medium" : "text-green-400 font-medium"}>
          {price_vs_ma20_pct}%
        </span></div>
        <div>Profit <span className="text-white font-medium">{profitability}/10</span></div>
      </div>
    </div>
  );
}

function EventRow({ event }) {
  const eventType = String(event?.event_type || "GENERAL");
  const eventDate = event?.event_date || event?.broadcast_date?.slice(0, 10) || "N/A";
  const colorClass = EVENT_COLORS[eventType] || EVENT_COLORS.GENERAL;

  return (
    <div className="flex items-start gap-3 py-2 border-b border-gray-800 last:border-0">
      <div className="flex flex-col items-center gap-1 min-w-[60px]">
        <span className="text-xs text-gray-500">{eventDate}</span>
      </div>
      <div className="flex flex-col gap-1 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-300">{event.company || "Unknown"}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${colorClass}`}>
            {eventType.replace(/_/g, " ")}
          </span>
        </div>
        <span className="text-xs text-gray-500 leading-relaxed">{event.subject || "No event details."}</span>
      </div>
      {event.attachment_url && (
        <a
          href={event.attachment_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-400 hover:text-blue-300 shrink-0"
        >
          PDF
        </a>
      )}
    </div>
  );
}

function SectorInsightsPanel({ insights }) {
  if (!insights || insights.error) return null;

  const OUTLOOK_COLORS = {
    BULLISH: { text: "text-green-300", bg: "bg-green-500/15", border: "border-green-500/40" },
    "CAUTIOUSLY POSITIVE": { text: "text-yellow-300", bg: "bg-yellow-500/15", border: "border-yellow-500/40" },
    NEUTRAL: { text: "text-slate-300", bg: "bg-slate-500/15", border: "border-slate-500/40" },
    BEARISH: { text: "text-red-300", bg: "bg-red-500/15", border: "border-red-500/40" },
  };

  const outlookStyle = OUTLOOK_COLORS[insights.outlook] || OUTLOOK_COLORS["NEUTRAL"];
  const dist = insights.signal_distribution || {};
  const avgSentiment = Number(insights.sector_avg_sentiment ?? 0);
  const sentimentWidth = Math.max(0, Math.min((avgSentiment / 10) * 100, 100));
  const topPerformerName = insights.best_company?.company || "N/A";
  const topPerformerScore = insights.best_company?.composite_score ?? "-";
  const watchName = insights.worst_company?.company || "N/A";
  const watchScore = insights.worst_company?.composite_score ?? "-";

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-gray-200 uppercase tracking-wider">Auto Sector Summary</h2>
          <p className="text-xs text-gray-500 mt-0.5">{insights.date}</p>
        </div>
        <span className={`text-xs font-bold px-3 py-1 rounded-full border ${outlookStyle.bg} ${outlookStyle.text} ${outlookStyle.border}`}>
          {insights.outlook}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex justify-between text-xs text-gray-400">
          <span>Sector Sentiment</span>
          <span className="font-bold text-gray-100">{avgSentiment}/10</span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2">
          <div
            className="h-2 rounded-full bg-gradient-to-r from-red-400 via-yellow-400 to-green-500"
            style={{ width: `${sentimentWidth}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500">
          <span>Low: {insights.sector_min}</span>
          <span>High: {insights.sector_max}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {[
          { key: "BUY", label: "Buy", color: "text-green-300 bg-green-500/10 border-green-500/30" },
          { key: "NEUTRAL", label: "Neutral", color: "text-yellow-300 bg-yellow-500/10 border-yellow-500/30" },
          { key: "RISK_ALERT", label: "Risk", color: "text-red-300 bg-red-500/10 border-red-500/30" },
        ].map(({ key, label, color }) => (
          <div key={key} className={`rounded-lg border p-2 text-center ${color}`}>
            <div className="text-lg font-bold">{dist[key] || 0}</div>
            <div className="text-xs font-medium">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-green-500/10 border border-green-500/30 p-3">
          <div className="text-xs text-green-300 font-medium mb-1">Top Performer</div>
          <div className="text-sm font-bold text-gray-100">{topPerformerName}</div>
          <div className="text-xs text-gray-400">Score: {topPerformerScore}/10</div>
        </div>
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3">
          <div className="text-xs text-red-300 font-medium mb-1">Watch Carefully</div>
          <div className="text-sm font-bold text-gray-100">{watchName}</div>
          <div className="text-xs text-gray-400">Score: {watchScore}/10</div>
        </div>
      </div>

      {insights.top_positive_news?.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Company News</div>
          <div className="flex flex-col gap-1.5">
            {insights.top_positive_news.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-green-500 mt-0.5 shrink-0 text-xs">+</span>
                <div>
                  <span className="text-xs font-medium text-gray-300">{item.company_tags || "Sector"} </span>
                  <span className="text-xs text-gray-400">
                    {(item.chunk_text || "No summary available").slice(0, 80)}
                    {(item.chunk_text || "").length > 80 ? "..." : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {insights.top_negative_events?.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Risk Events</div>
          <div className="flex flex-col gap-1.5">
            {insights.top_negative_events.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-red-500 mt-0.5 shrink-0 text-xs">!</span>
                <div>
                  <span className="text-xs font-medium text-gray-300">{item.company || "Unknown"} </span>
                  <span className="text-xs text-gray-400">{(item.subject || "No event details").slice(0, 80)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AutoSignal() {
  const [heatmap, setHeatmap]   = useState(null);
  const [report, setReport]     = useState(null);
  const [events, setEvents]     = useState(null);
  const [insights, setInsights] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  const refreshReport = async () => {
    try {
      const latestReport = await fetchSectorReport();
      setReport(latestReport);
    } catch (err) {
      console.error("AutoSignal report refresh error:", err);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const [heatmapResult, reportResult, eventsResult, insightsResult] = await Promise.allSettled([
          fetchSectorHeatmap(),
          fetchSectorReport(),
          fetchEvents(),
          fetchSectorInsights(),
        ]);

        if (heatmapResult.status === "fulfilled") {
          setHeatmap(heatmapResult.value);
        } else {
          console.error("AutoSignal heatmap load error:", heatmapResult.reason);
        }

        if (reportResult.status === "fulfilled") {
          setReport(reportResult.value);
        } else {
          console.error("AutoSignal report load error:", reportResult.reason);
        }

        if (eventsResult.status === "fulfilled") {
          setEvents(eventsResult.value);
        } else {
          console.error("AutoSignal events load error:", eventsResult.reason);
        }

        if (insightsResult.status === "fulfilled") {
          setInsights(insightsResult.value);
        } else {
          console.error("AutoSignal insights load error:", insightsResult.reason);
        }
      } catch (err) {
        console.error("AutoSignal load error:", err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (activeTab === "report") {
      refreshReport();
    }
  }, [activeTab]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-gray-400 text-sm">Loading AutoSignal...</span>
        </div>
      </div>
    );
  }

  const sectorAvg = report?.sector_avg_sentiment ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            AutoSignal <span className="text-blue-600">AI</span>
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Indian Auto Sector | Sentiment Intelligence | {report?.report_date}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs text-slate-500">Sector Avg Sentiment</span>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-slate-900">
              {sectorAvg}<span className="text-slate-400 text-sm">/10</span>
            </span>
            <div className={`w-3 h-3 rounded-full ${sectorAvg >= 6 ? "bg-green-400" : sectorAvg >= 4.5 ? "bg-yellow-400" : "bg-red-400"}`} />
          </div>
        </div>
      </div>

      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 w-fit">
        {["overview", "events", "report"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? "bg-blue-600 text-white"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div className="lg:col-span-1">
              <SectorInsightsPanel insights={insights} />
            </div>
            <div className="lg:col-span-3 flex flex-col gap-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
                  Sector Heatmap
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                  {heatmap?.companies?.map((co) => (
                    <SentimentCard
                      key={co.company}
                      {...co}
                      slug={COMPANY_SLUGS[co.company]}
                    />
                  ))}
                </div>
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
                  Sentiment Leaderboard
                </h2>
                <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase">
                        <th className="text-left px-4 py-3">Rank &amp; Company</th>
                        <th className="text-right px-4 py-3">Sentiment Score</th>
                        <th className="text-right px-4 py-3">Signal</th>
                        <th className="text-right px-4 py-3">Technical RSI</th>
                        <th className="text-right px-4 py-3">Price vs MA20</th>
                      </tr>
                    </thead>
                    <tbody>
                      {heatmap?.companies
                        ?.slice()
                        .sort((a, b) => b.sentiment_score - a.sentiment_score)
                        .map((co, i) => {
                          const colors = SIGNAL_COLORS[co.signal] || SIGNAL_COLORS.NEUTRAL;
                          return (
                            <tr
                              key={co.company}
                              onClick={() => {}}
                              className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors cursor-pointer"
                            >
                              <td className="px-4 py-3 font-medium text-white">
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-600 text-xs w-4">{i + 1}</span>
                                  {co.company}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <div className="w-16 bg-gray-800 rounded-full h-1">
                                    <div
                                      className={`h-1 rounded-full ${SENTIMENT_BG(co.sentiment_score)}`}
                                      style={{ width: `${(co.sentiment_score / 10) * 100}%` }}
                                    />
                                  </div>
                                  <span className="text-white font-medium">{co.sentiment_score}</span>
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${colors.bg} ${colors.text} border ${colors.border}`}>
                                  {co.signal.replace("_", " ")}
                                </span>
                              </td>
                              <td className={`px-4 py-3 text-right font-medium ${
                                co.rsi_14 < 30 ? "text-red-400" : co.rsi_14 > 70 ? "text-green-400" : "text-gray-300"
                              }`}>
                                {co.rsi_14}
                              </td>
                              <td className={`px-4 py-3 text-right font-medium ${
                                co.price_vs_ma20_pct < 0 ? "text-red-400" : "text-green-400"
                              }`}>
                                {co.price_vs_ma20_pct}%
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "events" && (
        <div>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
            Corporate Events Timeline ({events?.count ?? events?.events?.length ?? 0} events)
          </h2>
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 max-h-[600px] overflow-y-auto">
            {(events?.events || []).map((event, i) => (
              <EventRow key={i} event={event} />
            ))}
          </div>
        </div>
      )}

      {activeTab === "report" && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
              Weekly Sector Report
            </h2>
            <span className="text-xs text-gray-600">Generated by {report?.generated_by}</span>
          </div>
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap">
              {report?.report_text}
            </p>
          </div>
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <span className="text-sm font-semibold text-gray-300">Company Signals</span>
            </div>
            {report?.companies?.map((co) => {
              const colors = SIGNAL_COLORS[co.signal] || SIGNAL_COLORS.NEUTRAL;
              return (
                <div key={co.company} className="px-4 py-3 border-b border-gray-800/50 last:border-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-white">{co.company}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${colors.bg} ${colors.text} border ${colors.border}`}>
                      {co.signal.replace("_", " ")}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{co.reasoning}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import Loader from "./Loader";
import { fetchQualitySnapshot, generateQualityReports } from "../api/stocks";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

const normalizeSignal = (value) => {
  const text = String(value || "").trim().toUpperCase();
  if (text.includes("BUY")) return "BUY";
  if (text.includes("SELL")) return "SELL";
  if (text.includes("HOLD")) return "HOLD";
  return "";
};

const SignalBadge = ({ signal }) => {
  const normalized = normalizeSignal(signal);
  if (!normalized) return <span className="text-xs text-slate-400">—</span>;
  const styles =
    normalized === "BUY"
      ? "bg-emerald-100 text-emerald-700"
      : normalized === "SELL"
      ? "bg-rose-100 text-rose-600"
      : "bg-amber-100 text-amber-700";
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold ${styles}`}>{normalized}</span>;
};

export default function QualityResearchModal({ open, portfolioId, portfolioName, onClose, onGenerated }) {
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [rows, setRows] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open || !portfolioId) return;

    const loadSnapshot = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetchQualitySnapshot(portfolioId);
        const shortlist = Array.isArray(response?.shortlist) ? response.shortlist : [];
        setRows(shortlist);
        setSelectedIds(shortlist.map((item) => item.stock_id));
      } catch (err) {
        setError(err?.response?.data?.detail || "Unable to build the AI shortlist.");
        setRows([]);
        setSelectedIds([]);
      } finally {
        setLoading(false);
      }
    };

    loadSnapshot();
  }, [open, portfolioId]);

  useEffect(() => {
    if (!open) {
      setError("");
      setRows([]);
      setSelectedIds([]);
      setLoading(false);
      setGenerating(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const toggle = (stockId) => {
    setSelectedIds((current) =>
      current.includes(stockId) ? current.filter((value) => value !== stockId) : [...current, stockId]
    );
  };

  const handleGenerate = async () => {
    if (!selectedIds.length) {
      setError("Select at least one stock to generate a report.");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      const response = await generateQualityReports(portfolioId, selectedIds);
      onGenerated?.(response);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to generate quality stock reports.");
    } finally {
      setGenerating(false);
    }
  };

  if (!open || !mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[80] overflow-y-auto bg-slate-950/50 backdrop-blur-sm">
      <div className="flex min-h-full items-end justify-center p-3 sm:items-center sm:p-6">
        <div className="absolute inset-0" onClick={onClose} aria-hidden="true" />

        <div className="relative z-[81] flex max-h-[min(88vh,920px)] w-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-white/60 bg-white shadow-2xl">
          <div className="border-b border-slate-100 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 px-6 py-5 text-white">
            <button
              type="button"
              onClick={onClose}
              className="absolute right-4 top-4 rounded-full border border-white/20 px-3 py-1 text-xs font-semibold text-white/80 transition hover:bg-white/10 hover:text-white"
            >
              Close
            </button>
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-cyan-200">Research</p>
            <h2 className="mt-1 text-2xl font-bold">Quality Stocks — {portfolioName || "Portfolio"}</h2>
            <p className="mt-1 text-sm text-slate-300">LLM selected shortlist of top stocks. Select stocks to research deeper.</p>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            <div className="space-y-4">
              {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

              {(loading || generating) && (
                <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50">
                  <Loader />
                  <p className="text-sm text-slate-500">
                    {generating ? "Generating LangGraph quality reports..." : "Building AI shortlist from portfolio data..."}
                  </p>
                </div>
              )}

              {!loading && !generating && (
                <>
                  {rows.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-12 text-center text-sm text-slate-500">
                      No eligible stocks were found for this portfolio yet.
                    </div>
                  ) : (
                    <div className="overflow-hidden rounded-2xl border border-slate-100">
                      <div className="overflow-x-auto">
                        <table className="min-w-full text-sm text-slate-700">
                          <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="px-4 py-3 text-left">Select</th>
                              <th className="px-4 py-3 text-left">Symbol</th>
                              <th className="px-4 py-3 text-left">Company</th>
                              <th className="px-4 py-3 text-right">Price</th>
                              <th className="px-4 py-3 text-right">Predicted %</th>
                              <th className="px-4 py-3 text-right">% Change</th>
                              <th className="px-4 py-3 text-center">Signal</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {rows.map((row) => {
                              const predictedPercent =
                                row.predicted_price_1d && row.current_price
                                  ? ((Number(row.predicted_price_1d) - Number(row.current_price)) / Number(row.current_price)) * 100
                                  : row.expected_change_pct;
                              return (
                                <tr key={row.stock_id} className="hover:bg-slate-50">
                                  <td className="px-4 py-3">
                                    <input
                                      type="checkbox"
                                      checked={selectedSet.has(row.stock_id)}
                                      onChange={() => toggle(row.stock_id)}
                                      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                    />
                                  </td>
                                  <td className="px-4 py-3 font-semibold text-slate-900">{row.symbol}</td>
                                  <td className="px-4 py-3 text-slate-600">{row.company_name}</td>
                                  <td className="px-4 py-3 text-right font-semibold text-slate-900">
                                    {formatMoney(row.current_price, currencyCodeFromItem(row))}
                                  </td>
                                  <td className="px-4 py-3 text-right text-indigo-700">
                                    {predictedPercent !== null && predictedPercent !== undefined ? `${Number(predictedPercent).toFixed(2)}%` : "—"}
                                  </td>
                                  <td className="px-4 py-3 text-right">
                                    <span
                                      className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold ${
                                        Number(row.expected_change_pct || 0) >= 0 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-600"
                                      }`}
                                    >
                                      {Number(row.expected_change_pct || 0) >= 0 ? "+" : ""}
                                      {Number(row.expected_change_pct || 0).toFixed(2)}%
                                    </span>
                                  </td>
                                  <td className="px-4 py-3 text-center">
                                    <SignalBadge signal={row.recommended_action} />
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-slate-500">
                      {selectedIds.length} of {rows.length} shortlist stocks selected for deeper research.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={onClose}
                        className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={handleGenerate}
                        disabled={!rows.length || !selectedIds.length}
                        className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:from-indigo-700 hover:to-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Generate Report
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

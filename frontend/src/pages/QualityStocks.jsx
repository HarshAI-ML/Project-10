import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Loader from "../components/Loader";
import StockTable from "../components/StockTable";
import {
  deleteQualityStock,
  fetchPortfolio,
  fetchQualityStocks,
  rerunQualityStockReport,
} from "../api/stocks";

export default function QualityStocks() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [portfolios, setPortfolios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [portfolioFilter, setPortfolioFilter] = useState(searchParams.get("portfolio") || "all");
  const [signalFilter, setSignalFilter] = useState("all");
  const [rerunningId, setRerunningId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const loadRows = async (nextPortfolio = portfolioFilter, nextSignal = signalFilter) => {
    setLoading(true);
    setError("");
    try {
      const [portfolioData, qualityData] = await Promise.all([
        fetchPortfolio({ lite: true }),
        fetchQualityStocks({
          portfolio: nextPortfolio !== "all" ? nextPortfolio : undefined,
          signal: nextSignal,
        }),
      ]);
      setPortfolios(Array.isArray(portfolioData) ? portfolioData : []);
      setRows(Array.isArray(qualityData) ? qualityData : []);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to load saved quality stock research.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows(portfolioFilter, signalFilter);
  }, [portfolioFilter, signalFilter]);

  useEffect(() => {
    const selectedPortfolio = searchParams.get("portfolio") || "all";
    if (selectedPortfolio !== portfolioFilter) {
      setPortfolioFilter(selectedPortfolio);
    }
  }, [searchParams, portfolioFilter]);

  const stats = useMemo(() => {
    const avgRating =
      rows.length > 0 ? (rows.reduce((sum, row) => sum + Number(row.ai_rating || 0), 0) / rows.length).toFixed(1) : "0.0";
    const buyCount = rows.filter((row) => String(row.buy_signal || row.recommended_action).toUpperCase() === "BUY").length;
    return { avgRating, buyCount };
  }, [rows]);

  const handleRerun = async (row) => {
    setRerunningId(row.quality_stock_id);
    setError("");
    try {
      const response = await rerunQualityStockReport(row.quality_stock_id);
      if (response?.quality_stock_id || response?.id) {
        navigate(`/quality-stocks/${response.quality_stock_id || response.id}/report`);
      } else {
        await loadRows(portfolioFilter, signalFilter);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to regenerate the report.");
    } finally {
      setRerunningId(null);
    }
  };

  const handleDelete = async (row) => {
    setDeletingId(row.quality_stock_id);
    setError("");
    try {
      await deleteQualityStock(row.quality_stock_id);
      await loadRows(portfolioFilter, signalFilter);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to delete the saved report.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Quality Stocks</h1>
          <p className="mt-1 text-sm text-slate-500">Permanent AI research reports saved from your portfolio shortlists.</p>
        </div>
        <div className="flex gap-3">
          <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Saved Reports</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{rows.length}</p>
          </div>
          <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Average Rating</p>
            <p className="mt-1 text-2xl font-bold text-indigo-700">{stats.avgRating}</p>
          </div>
          <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">BUY Calls</p>
            <p className="mt-1 text-2xl font-bold text-emerald-700">{stats.buyCount}</p>
          </div>
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
        <div className="flex flex-wrap items-end gap-4">
          <label className="min-w-[220px] flex-1">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">Portfolio</span>
            <select
              value={portfolioFilter}
              onChange={(event) => {
                const next = event.target.value;
                setPortfolioFilter(next);
                if (next === "all") {
                  setSearchParams({}, { replace: true });
                } else {
                  setSearchParams({ portfolio: next }, { replace: true });
                }
              }}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-indigo-400 focus:outline-none"
            >
              <option value="all">All</option>
              {portfolios.map((portfolio) => (
                <option key={portfolio.id} value={portfolio.id}>
                  {portfolio.name}
                </option>
              ))}
            </select>
          </label>

          <label className="min-w-[220px] flex-1">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">Signal</span>
            <select
              value={signalFilter}
              onChange={(event) => setSignalFilter(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 focus:border-indigo-400 focus:outline-none"
            >
              <option value="all">All</option>
              <option value="BUY">BUY</option>
              <option value="HOLD">HOLD</option>
              <option value="SELL">SELL</option>
            </select>
          </label>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader />
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-14 text-center text-sm text-slate-500 shadow-sm">
          No saved quality stock reports yet. Open a portfolio, click Research, and generate a shortlist report.
        </div>
      ) : (
        <StockTable
          stocks={rows}
          disableRowNavigation
          showDeleteAction={false}
          showAiRating
          noticeText="Saved quality stock reports reuse live stock analytics and do not duplicate descriptive stock fields."
          actionRenderer={(row) => (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => navigate(`/quality-stocks/${row.quality_stock_id}/report`)}
                className="rounded-md border border-indigo-100 bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-indigo-700 transition hover:bg-indigo-100"
              >
                View Report
              </button>
              <button
                type="button"
                onClick={() => handleRerun(row)}
                disabled={rerunningId === row.quality_stock_id}
                className="rounded-md border border-amber-100 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700 transition hover:bg-amber-100 disabled:opacity-50"
              >
                {rerunningId === row.quality_stock_id ? "Running..." : "Re-run Report"}
              </button>
              <button
                type="button"
                onClick={() => handleDelete(row)}
                disabled={deletingId === row.quality_stock_id}
                className="rounded-md border border-rose-100 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-600 transition hover:bg-rose-100 disabled:opacity-50"
              >
                {deletingId === row.quality_stock_id ? "Deleting..." : "Delete"}
              </button>
            </div>
          )}
        />
      )}
    </section>
  );
}

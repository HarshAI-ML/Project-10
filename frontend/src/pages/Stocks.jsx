import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import Loader from "../components/Loader";
import StockTable from "../components/StockTable";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";
import {
  addStockToPortfolio, fetchPortfolio, fetchStocks,
  removeStockFromPortfolio, searchLiveStocks,
} from "../api/stocks";

const ACTIVE_PORTFOLIO_KEY = "active_portfolio_id";

const CustomBarTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur text-sm">
      <p className="font-mono font-bold text-slate-900">{label}</p>
      <p className="mt-1 text-slate-500">PE Ratio: <span className="font-bold text-indigo-700">{Number(payload[0].value).toFixed(2)}</span></p>
    </div>
  );
};

export default function Stocks() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const portfolioId = searchParams.get("portfolio");

  const [portfolios, setPortfolios] = useState([]);
  const [stocks, setStocks] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [addingSymbol, setAddingSymbol] = useState("");
  const [deletingStockId, setDeletingStockId] = useState(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [error, setError] = useState("");
  const [openingClusters, setOpeningClusters] = useState(false);

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === String(portfolioId)) || null,
    [portfolios, portfolioId]
  );
  const peChartData = useMemo(
    () => stocks.map((s) => ({ symbol: s.symbol, pe_ratio: Number(s.pe_ratio || 0) })),
    [stocks]
  );
  const portfolioSymbols = useMemo(
    () => new Set(stocks.map((s) => String(s.symbol).toUpperCase())),
    [stocks]
  );

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError("");
      try {
        const [portfolioData, stockData] = await Promise.all([fetchPortfolio(), fetchStocks(portfolioId)]);
        const pArr = Array.isArray(portfolioData) ? portfolioData : [];
        const sArr = Array.isArray(stockData) ? stockData : [];
        if (!pArr.some((p) => String(p.id) === String(portfolioId))) {
          navigate("/portfolio?notice=select-portfolio", { replace: true });
          return;
        }
        sessionStorage.setItem(ACTIVE_PORTFOLIO_KEY, String(portfolioId));
        setPortfolios(pArr);
        setStocks(sArr);
      } catch {
        setError("Unable to load stocks.");
      } finally {
        setLoading(false);
      }
    };
    if (!portfolioId) {
      const active = sessionStorage.getItem(ACTIVE_PORTFOLIO_KEY);
      if (active) { navigate(`/stocks?portfolio=${active}`, { replace: true }); return; }
      navigate("/portfolio?notice=select-portfolio", { replace: true });
      return;
    }
    loadData();
  }, [navigate, portfolioId]);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!portfolioId) return;
    setTableLoading(true);
    setError("");
    setMessage("");
    try {
      setSearchResults(searchQuery.trim() ? (await searchLiveStocks(searchQuery.trim(), 20)) || [] : []);
    } catch { setError("Search request failed."); }
    finally { setTableLoading(false); }
  };

  const handleAddStock = async (symbol) => {
    if (!portfolioId || !symbol) return;
    setAddingSymbol(symbol);
    setMessage("");
    setError("");
    try {
      await addStockToPortfolio(portfolioId, String(symbol).trim().toUpperCase());
      setStocks((await fetchStocks(portfolioId)) || []);
      setMessage(`${symbol} added to portfolio.`);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to add stock.");
    } finally { setAddingSymbol(""); }
  };

  const handleDeleteStock = async (stockId, symbol) => {
    if (!stockId || !portfolioId) return;
    setDeletingStockId(stockId);
    setMessage("");
    setError("");
    try {
      await removeStockFromPortfolio(stockId);
      setStocks((await fetchStocks(portfolioId)) || []);
      setMessage(`${symbol} removed.`);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to delete stock.");
    } finally { setDeletingStockId(null); }
  };

  return (
    <section className="space-y-8">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {selectedPortfolio?.name || "Portfolio"} Stocks
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {selectedPortfolio?.description || "Manage and analyse your holdings"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={openingClusters}
            onClick={() => {
              if (!portfolioId) { navigate("/portfolio?notice=select-portfolio"); return; }
              setOpeningClusters(true);
              navigate(`/portfolio/${portfolioId}/clusters`);
            }}
            className="rounded-xl border border-violet-200 bg-violet-50 px-4 py-2 text-sm font-semibold text-violet-700 shadow-sm transition hover:bg-violet-100 disabled:opacity-50"
          >
            {openingClusters ? "Opening…" : "🔬 Clusters"}
          </button>
          <Link
            to="/portfolio"
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:bg-slate-50"
          >
            ← Portfolios
          </Link>
        </div>
      </div>

      {/* ── Alerts ── */}
      {message && (
        <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700 ring-1 ring-emerald-200">
          <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
          </svg>
          {message}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 ring-1 ring-rose-200">
          <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd"/>
          </svg>
          {error}
        </div>
      )}

      {/* ── Search ── */}
      <form
        onSubmit={handleSearch}
        className="flex items-center gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100"
      >
        <div className="relative flex-1">
          <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-4 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            placeholder="Search any stock symbol (e.g. AAPL, BTC-USD, RELIANCE.NS)…"
          />
        </div>
        <button
          type="submit"
          disabled={tableLoading}
          className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-2.5 text-sm font-bold text-white shadow transition hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50"
        >
          {tableLoading ? "…" : "Search"}
        </button>
      </form>

      {/* ── Loading ── */}
      {(loading || tableLoading) && (
        <div className="flex justify-center py-10"><Loader /></div>
      )}

      {!loading && !tableLoading && (
        <div className="space-y-8">
          {/* Search results */}
          {searchResults.length > 0 && (
            <div className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
              <div className="border-b border-slate-100 px-5 py-4">
                <h2 className="text-sm font-bold text-slate-700">
                  Search Results
                  <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700">
                    {searchResults.length}
                  </span>
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50">
                      {["Symbol", "Company", "Price", "Action"].map((h) => (
                        <th key={h} className={`px-5 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 ${h === "Action" || h === "Price" ? "text-right" : "text-left"}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {searchResults.map((result) => {
                      const symbol = String(result.symbol || "").toUpperCase();
                      const alreadyAdded = portfolioSymbols.has(symbol);
                      return (
                        <tr key={symbol} className="hover:bg-slate-50 transition">
                          <td className="px-5 py-3 font-mono text-sm font-bold text-slate-900">{result.symbol}</td>
                          <td className="px-5 py-3 text-sm text-slate-600">{result.company_name}</td>
                          <td className="px-5 py-3 text-right text-sm font-semibold text-slate-700">
                            {formatMoney(result.current_price, currencyCodeFromItem(result))}
                          </td>
                          <td className="px-5 py-3 text-right">
                            <button
                              type="button"
                              onClick={() => handleAddStock(result.symbol)}
                              disabled={alreadyAdded || addingSymbol === result.symbol}
                              className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                                alreadyAdded
                                  ? "bg-slate-100 text-slate-400 cursor-default"
                                  : addingSymbol === result.symbol
                                  ? "bg-indigo-100 text-indigo-600"
                                  : "bg-indigo-600 text-white hover:bg-indigo-700"
                              }`}
                            >
                              {alreadyAdded ? "✓ Added" : addingSymbol === result.symbol ? "Adding…" : "+ Add"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Empty state */}
          {stocks.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl bg-white py-16 text-center shadow-sm ring-1 ring-slate-100">
              <div className="mb-4 text-4xl">📭</div>
              <p className="font-semibold text-slate-700">No stocks in this portfolio yet</p>
              <p className="mt-1 text-sm text-slate-400">Search for a symbol above to add your first stock</p>
            </div>
          ) : (
            <>
              <StockTable
                stocks={stocks}
                onDeleteStock={handleDeleteStock}
                deletingStockId={deletingStockId}
              />

              {/* PE bar chart */}
              <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
                <h2 className="text-sm font-bold text-slate-700">PE Ratio Comparison</h2>
                <p className="mb-4 mt-0.5 text-xs text-slate-400">Trailing / forward PE across your holdings</p>
                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={peChartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="symbol" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                      <Tooltip content={<CustomBarTooltip />} />
                      <Bar dataKey="pe_ratio" radius={[6, 6, 0, 0]} name="PE Ratio">
                        {peChartData.map((_, i) => (
                          <Cell key={i} fill={`hsl(${240 + i * 18}, 70%, ${55 + (i % 3) * 5}%)`} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

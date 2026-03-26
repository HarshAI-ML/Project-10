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
const DEFAULT_ADV_FILTERS = {
  peMin: "",
  peMax: "",
  sentimentMin: 0,
  sentimentMax: 10,
  changeMin: "",
  changeMax: "",
  r2Min: 0,
  discountLevels: ["HIGH", "MEDIUM", "LOW", "—"],
  priceMin: "",
  priceMax: "",
  minPriceMin: "",
  minPriceMax: "",
  maxPriceMin: "",
  maxPriceMax: "",
  predictedMin: "",
  predictedMax: "",
};

const cloneDefaultAdvFilters = () => ({
  ...DEFAULT_ADV_FILTERS,
  discountLevels: [...DEFAULT_ADV_FILTERS.discountLevels],
});

const CustomBarTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur text-sm">
      <p className="font-mono font-bold text-slate-900">{label}</p>
      <p className="mt-1 text-slate-500">PE Ratio: <span className="font-bold text-indigo-700">{Number(payload[0].value).toFixed(2)}</span></p>
    </div>
  );
};

const CustomSentimentTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const value = Number(payload[0].value);
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3 shadow-xl backdrop-blur text-sm">
      <p className="font-mono font-bold text-slate-900">{label}</p>
      <p className="mt-1 text-slate-500">
        Sentiment Score: <span className="font-bold text-amber-700">{value.toFixed(2)}/10</span>
      </p>
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
  const [chartMode, setChartMode] = useState("pe");

  // Server-side factor filters
  const [trendFilter, setTrendFilter] = useState("all");
  const [signalFilter, setSignalFilter] = useState("all");
  const [discountFilter, setDiscountFilter] = useState("all");
  const [sentimentFilter, setSentimentFilter] = useState("all");
  const [geography, setGeography] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [sortCol, setSortCol] = useState('expected_change_pct');
  const [sortDir, setSortDir] = useState('desc');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advFilters, setAdvFilters] = useState(() => cloneDefaultAdvFilters());

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === String(portfolioId)) || null,
    [portfolios, portfolioId]
  );
  const peChartData = useMemo(
    () => stocks.map((s) => ({ symbol: s.symbol, pe_ratio: Number(s.pe_ratio || 0) })),
    [stocks]
  );
  const sentimentChartData = useMemo(
    () =>
      stocks
        .filter((s) => s.sentiment_score !== null && s.sentiment_score !== undefined)
        .map((s) => ({
          symbol: s.symbol,
          sentiment_score: Number(s.sentiment_score),
        })),
    [stocks]
  );
  const portfolioSymbols = useMemo(
    () => new Set(stocks.map((s) => String(s.symbol).toUpperCase())),
    [stocks]
  );
  const stockFetchOptions = useMemo(
    () => ({
      geography,
      trend: trendFilter,
      signal: signalFilter,
      discount: discountFilter,
      sentiment: sentimentFilter,
    }),
    [geography, trendFilter, signalFilter, discountFilter, sentimentFilter]
  );
  const resetAdvancedFilters = () => {
    setAdvFilters(cloneDefaultAdvFilters());
    setSignalFilter("all");
  };
  // Advanced filters stay client-side after server-side factor filtering.
  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    // 1. Geography filter
    if (geography !== 'all') {
      result = result.filter(s => s.geography === geography);
    }

    // 2. Advanced filters
    if (advFilters.peMin !== '') {
      result = result.filter(s => s.pe_ratio != null && s.pe_ratio >= Number(advFilters.peMin));
    }
    if (advFilters.peMax !== '') {
      result = result.filter(s => s.pe_ratio != null && s.pe_ratio <= Number(advFilters.peMax));
    }
    if (advFilters.priceMin !== '') {
      result = result.filter(s => s.current_price != null && s.current_price >= Number(advFilters.priceMin));
    }
    if (advFilters.priceMax !== '') {
      result = result.filter(s => s.current_price != null && s.current_price <= Number(advFilters.priceMax));
    }
    if (advFilters.minPriceMin !== '') {
      result = result.filter(s => s.min_price != null && s.min_price >= Number(advFilters.minPriceMin));
    }
    if (advFilters.minPriceMax !== '') {
      result = result.filter(s => s.min_price != null && s.min_price <= Number(advFilters.minPriceMax));
    }
    if (advFilters.maxPriceMin !== '') {
      result = result.filter(s => s.max_price != null && s.max_price >= Number(advFilters.maxPriceMin));
    }
    if (advFilters.maxPriceMax !== '') {
      result = result.filter(s => s.max_price != null && s.max_price <= Number(advFilters.maxPriceMax));
    }
    if (advFilters.predictedMin !== '') {
      result = result.filter(s => s.predicted_price_1d != null && s.predicted_price_1d >= Number(advFilters.predictedMin));
    }
    if (advFilters.predictedMax !== '') {
      result = result.filter(s => s.predicted_price_1d != null && s.predicted_price_1d <= Number(advFilters.predictedMax));
    }
    if (advFilters.sentimentMin > 0) {
      result = result.filter(s => (s.sentiment_score || 0) >= advFilters.sentimentMin);
    }
    if (advFilters.sentimentMax < 10) {
      result = result.filter(s => (s.sentiment_score || 0) <= advFilters.sentimentMax);
    }
    if (advFilters.changeMin !== '') {
      result = result.filter(s => (s.expected_change_pct || 0) >= Number(advFilters.changeMin));
    }
    if (advFilters.changeMax !== '') {
      result = result.filter(s => (s.expected_change_pct || 0) <= Number(advFilters.changeMax));
    }
    if (advFilters.r2Min > 0) {
      result = result.filter(s => (s.model_confidence_r2 || 0) >= advFilters.r2Min);
    }
    if (advFilters.discountLevels.length < 4) {
      result = result.filter(s => advFilters.discountLevels.includes(s.discount_level || '—'));
    }

    // 3. Sorting
    const signalOrder = { BUY: 3, HOLD: 2, SELL: 1, null: 0, undefined: 0 };

    result.sort((a, b) => {
      let aVal, bVal;
      switch (sortCol) {
        case 'symbol':
          aVal = a.symbol || '';
          bVal = b.symbol || '';
          break;
        case 'current_price':
          aVal = a.current_price || 0;
          bVal = b.current_price || 0;
          break;
        case 'expected_change_pct':
          aVal = a.expected_change_pct || 0;
          bVal = b.expected_change_pct || 0;
          break;
        case 'predicted_price_1d':
          aVal = a.predicted_price_1d || 0;
          bVal = b.predicted_price_1d || 0;
          break;
        case 'recommended_action':
          aVal = signalOrder[a.recommended_action] || 0;
          bVal = signalOrder[b.recommended_action] || 0;
          break;
        case 'model_confidence_r2':
          aVal = a.model_confidence_r2 ?? -1;
          bVal = b.model_confidence_r2 ?? -1;
          break;
        case 'pe_ratio':
          aVal = a.pe_ratio ?? Infinity;
          bVal = b.pe_ratio ?? Infinity;
          break;
        case 'sentiment_score':
          aVal = a.sentiment_score ?? -1;
          bVal = b.sentiment_score ?? -1;
          break;
        case 'discount_pct':
          aVal = a.discount_pct ?? -Infinity;
          bVal = b.discount_pct ?? -Infinity;
          break;
        default:
          aVal = 0;
          bVal = 0;
      }

      // Secondary sort by symbol for stability
      if (aVal === bVal) {
        const aSymbol = a.symbol || '';
        const bSymbol = b.symbol || '';
        return sortDir === 'asc' ? aSymbol.localeCompare(bSymbol) : bSymbol.localeCompare(aSymbol);
      }

      if (typeof aVal === 'string') {
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });

    return result;
  }, [stocks, geography, sortCol, sortDir, advFilters]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError("");
      try {
        const [portfolioData, stockData] = await Promise.all([
          fetchPortfolio({ lite: true }),
          fetchStocks(portfolioId, stockFetchOptions),
        ]);
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
  }, [navigate, portfolioId, stockFetchOptions]);

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
      setStocks((await fetchStocks(portfolioId, stockFetchOptions)) || []);
      setMessage(`${symbol} added to portfolio.`);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to add stock.");
    } finally { setAddingSymbol(""); }
  };

  const handleDeleteStock = async (symbol) => {
    if (!symbol || !portfolioId) return;
    setDeletingStockId(symbol);
    setMessage("");
    setError("");
    try {
      await removeStockFromPortfolio(portfolioId, symbol);
      setStocks((await fetchStocks(portfolioId, stockFetchOptions)) || []);
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

      {/* ── Filters Dropdown ── */}
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
        <button
          type="button"
          onClick={() => setShowFilters((prev) => !prev)}
          className="flex w-full items-center justify-between rounded-xl bg-slate-50 px-4 py-3 text-left transition hover:bg-slate-100"
        >
          <div>
            <p className="text-sm font-bold text-slate-800">Filters</p>
            <p className="text-xs text-slate-500">Trend, signal, discount, sentiment and geography</p>
          </div>
          <span className="text-sm font-semibold text-indigo-600">
            {showFilters ? "Hide" : "Show"}
          </span>
        </button>

        {showFilters && (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Trend:</span>
              {[
                { key: "all", label: "All" },
                { key: "gainers", label: "Gainers" },
                { key: "losers", label: "Losers" },
              ].map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTrendFilter(key)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    trendFilter === key ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Signal:</span>
              {[
                { key: "all", label: "All" },
                { key: "buy", label: "BUY Signal" },
                { key: "sell", label: "SELL Signal" },
                { key: "hold", label: "HOLD Signal" },
              ].map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSignalFilter(key)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    signalFilter === key ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Discount:</span>
              {[
                { key: "all", label: "All" },
                { key: "high_discount", label: "High Discount" },
                { key: "low_discount", label: "Low Discount" },
              ].map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setDiscountFilter(key)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    discountFilter === key ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sentiment:</span>
              {[
                { key: "all", label: "All" },
                { key: "positive_sentiment", label: "Positive Sentiment" },
                { key: "neutral_sentiment", label: "Neutral Sentiment" },
                { key: "negative_sentiment", label: "Negative Sentiment" },
              ].map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSentimentFilter(key)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    sentimentFilter === key ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Geography:</span>
              {[
                { key: 'all', label: 'All', flag: null },
                { key: 'IN', label: 'India', flag: '🇮🇳' },
                { key: 'US', label: 'US', flag: '🇺🇸' },
              ].map(({ key, label, flag }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setGeography(key)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    geography === key
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {flag && <span className="mr-1">{flag}</span>}
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Advanced Filters Toggle ── */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
      >
        <span>{showAdvanced ? '▲ Advanced Filters' : '▼ Advanced Filters'}</span>
      </button>

      {/* ── Advanced Filters Panel ── */}
      {showAdvanced && (
        <div className="space-y-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* PE Ratio */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                PE Ratio Range
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={advFilters.peMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, peMin: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={advFilters.peMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, peMax: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
              </div>
            </div>

            {/* Price */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Current Price Range
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={advFilters.priceMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, priceMin: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={advFilters.priceMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, priceMax: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
              </div>
            </div>

            {/* Min Price */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Min Price Range
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={advFilters.minPriceMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, minPriceMin: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={advFilters.minPriceMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, minPriceMax: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
              </div>
            </div>

            {/* Max Price */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Max Price Range
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={advFilters.maxPriceMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, maxPriceMin: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={advFilters.maxPriceMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, maxPriceMax: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
              </div>
            </div>

            {/* Predicted Price */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Predicted Price Range
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={advFilters.predictedMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, predictedMin: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={advFilters.predictedMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, predictedMax: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
              </div>
            </div>

            {/* Signal */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Signal
              </label>
              <div className="flex flex-wrap gap-2">
                {[
                  { key: "all", label: "All" },
                  { key: "buy", label: "BUY" },
                  { key: "sell", label: "SELL" },
                  { key: "hold", label: "HOLD" },
                ].map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSignalFilter(key)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                      signalFilter === key
                        ? "bg-indigo-600 text-white shadow-sm"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Sentiment Score */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Sentiment Score (0-10)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="range"
                  min="0"
                  max="10"
                  step="0.5"
                  value={advFilters.sentimentMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, sentimentMin: Number(e.target.value) }))}
                  className="flex-1"
                />
                <span className="w-12 text-right text-sm font-mono">{advFilters.sentimentMin.toFixed(1)}</span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <input
                  type="range"
                  min="0"
                  max="10"
                  step="0.5"
                  value={advFilters.sentimentMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, sentimentMax: Number(e.target.value) }))}
                  className="flex-1"
                />
                <span className="w-12 text-right text-sm font-mono">{advFilters.sentimentMax.toFixed(1)}</span>
              </div>
            </div>

            {/* % Change */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                % Change Range
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  placeholder="Min %"
                  value={advFilters.changeMin}
                  onChange={(e) => setAdvFilters(f => ({ ...f, changeMin: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="number"
                  placeholder="Max %"
                  value={advFilters.changeMax}
                  onChange={(e) => setAdvFilters(f => ({ ...f, changeMax: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                />
              </div>
            </div>

            {/* R² Minimum */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Min R² (Model Confidence)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={advFilters.r2Min}
                  onChange={(e) => setAdvFilters(f => ({ ...f, r2Min: Number(e.target.value) }))}
                  className="flex-1"
                />
                <span className="w-12 text-right text-sm font-mono">{advFilters.r2Min.toFixed(2)}</span>
              </div>
            </div>

            {/* Discount Level */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Discount Level
              </label>
              <div className="flex flex-wrap gap-2">
                {['HIGH', 'MEDIUM', 'LOW', '—'].map(level => (
                  <label key={level} className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={advFilters.discountLevels.includes(level)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setAdvFilters(f => ({
                            ...f,
                            discountLevels: [...f.discountLevels, level]
                          }));
                        } else {
                          setAdvFilters(f => ({
                            ...f,
                            discountLevels: f.discountLevels.filter(l => l !== level)
                          }));
                        }
                      }}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-slate-700">{level}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Clear Button */}
            <div className="flex items-end">
              <button
                type="button"
                onClick={resetAdvancedFilters}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Clear Advanced Filters
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Results Summary Bar ── */}
      <div className="flex items-center justify-between rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
        <div className="text-sm text-slate-600">
          Showing <span className="font-bold text-slate-900"> {filteredStocks.length} </span>
          of <span className="font-bold text-slate-900"> {stocks.length} </span> stocks
        </div>
        <div className="flex flex-wrap gap-2">
          {(() => {
            const tags = [];
            if (trendFilter !== "all") {
              tags.push({
                key: "trend",
                label: `Trend: ${trendFilter.charAt(0).toUpperCase()}${trendFilter.slice(1)}`,
                clear: () => setTrendFilter("all"),
              });
            }
            if (signalFilter !== "all") {
              tags.push({
                key: "signal",
                label: `Signal: ${signalFilter.toUpperCase()}`,
                clear: () => setSignalFilter("all"),
              });
            }
            if (discountFilter !== "all") {
              tags.push({
                key: "discount",
                label: "Discount: High",
                clear: () => setDiscountFilter("all"),
              });
            }
            if (sentimentFilter !== "all") {
              tags.push({
                key: "sentiment",
                label: `Sentiment: ${sentimentFilter === "positive_sentiment" ? "Positive" : "Negative"}`,
                clear: () => setSentimentFilter("all"),
              });
            }
            if (geography !== 'all') {
              tags.push({ key: 'geo', label: geography === 'IN' ? 'India' : 'US', clear: () => setGeography('all') });
            }
            if (advFilters.peMin) tags.push({ key: 'peMin', label: `PE ≥ ${advFilters.peMin}`, clear: () => setAdvFilters(f => ({ ...f, peMin: '' })) });
            if (advFilters.peMax) tags.push({ key: 'peMax', label: `PE ≤ ${advFilters.peMax}`, clear: () => setAdvFilters(f => ({ ...f, peMax: '' })) });
            if (advFilters.priceMin) tags.push({ key: 'priceMin', label: `Price ≥ ${advFilters.priceMin}`, clear: () => setAdvFilters(f => ({ ...f, priceMin: '' })) });
            if (advFilters.priceMax) tags.push({ key: 'priceMax', label: `Price ≤ ${advFilters.priceMax}`, clear: () => setAdvFilters(f => ({ ...f, priceMax: '' })) });
            if (advFilters.minPriceMin) tags.push({ key: 'minPriceMin', label: `Min Price ≥ ${advFilters.minPriceMin}`, clear: () => setAdvFilters(f => ({ ...f, minPriceMin: '' })) });
            if (advFilters.minPriceMax) tags.push({ key: 'minPriceMax', label: `Min Price ≤ ${advFilters.minPriceMax}`, clear: () => setAdvFilters(f => ({ ...f, minPriceMax: '' })) });
            if (advFilters.maxPriceMin) tags.push({ key: 'maxPriceMin', label: `Max Price ≥ ${advFilters.maxPriceMin}`, clear: () => setAdvFilters(f => ({ ...f, maxPriceMin: '' })) });
            if (advFilters.maxPriceMax) tags.push({ key: 'maxPriceMax', label: `Max Price ≤ ${advFilters.maxPriceMax}`, clear: () => setAdvFilters(f => ({ ...f, maxPriceMax: '' })) });
            if (advFilters.predictedMin) tags.push({ key: 'predictedMin', label: `Predicted ≥ ${advFilters.predictedMin}`, clear: () => setAdvFilters(f => ({ ...f, predictedMin: '' })) });
            if (advFilters.predictedMax) tags.push({ key: 'predictedMax', label: `Predicted ≤ ${advFilters.predictedMax}`, clear: () => setAdvFilters(f => ({ ...f, predictedMax: '' })) });
            if (advFilters.changeMin) tags.push({ key: 'chgMin', label: `% ≥ ${advFilters.changeMin}%`, clear: () => setAdvFilters(f => ({ ...f, changeMin: '' })) });
            if (advFilters.changeMax) tags.push({ key: 'chgMax', label: `% ≤ ${advFilters.changeMax}%`, clear: () => setAdvFilters(f => ({ ...f, changeMax: '' })) });
            if (advFilters.r2Min > 0) tags.push({ key: 'r2', label: `R² ≥ ${advFilters.r2Min.toFixed(2)}`, clear: () => setAdvFilters(f => ({ ...f, r2Min: 0 })) });
            if (advFilters.sentimentMin > 0) tags.push({ key: 'sentMin', label: `Sentiment ≥ ${advFilters.sentimentMin.toFixed(1)}`, clear: () => setAdvFilters(f => ({ ...f, sentimentMin: 0 })) });
            if (advFilters.sentimentMax < 10) tags.push({ key: 'sentMax', label: `Sentiment ≤ ${advFilters.sentimentMax.toFixed(1)}`, clear: () => setAdvFilters(f => ({ ...f, sentimentMax: 10 })) });
            if (advFilters.discountLevels.length < 4) {
              const discLabels = advFilters.discountLevels.map(d => d === '—' ? 'None' : d).join(', ');
              tags.push({ key: 'disc', label: `Discount: ${discLabels}`, clear: () => setAdvFilters(f => ({ ...f, discountLevels: ['HIGH', 'MEDIUM', 'LOW', '—'] })) });
            }
            return tags;
          })()
          .map(tag => (
            <span
              key={tag.key}
              className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-semibold text-indigo-700"
            >
              {tag.label}
              <button
                type="button"
                onClick={tag.clear}
                className="ml-1 hover:text-indigo-900"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>


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
                stocks={filteredStocks}
                onDeleteStock={handleDeleteStock}
                deletingStockId={deletingStockId}
                sortCol={sortCol}
                sortDir={sortDir}
                onSort={(col, dir) => { setSortCol(col); setSortDir(dir); }}
              />

              <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-100">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-bold text-slate-700">
                      {chartMode === "pe" ? "PE Ratio Comparison" : "Sentiment Score Comparison"}
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {chartMode === "pe"
                        ? "Trailing / forward PE across your holdings"
                        : "AI sentiment score by stock (range: 0 to 10)"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setChartMode("pe")}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        chartMode === "pe" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      PE Graph
                    </button>
                    <button
                      type="button"
                      onClick={() => setChartMode("sentiment")}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        chartMode === "sentiment" ? "bg-amber-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      Sentiment Graph
                    </button>
                  </div>
                </div>
                <div className="h-72 w-full">
                  {chartMode === "pe" ? (
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
                  ) : (
                    <>
                      {sentimentChartData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={sentimentChartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="symbol" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} domain={[0, 10]} />
                            <Tooltip content={<CustomSentimentTooltip />} />
                            <Bar dataKey="sentiment_score" radius={[6, 6, 0, 0]} name="Sentiment Score">
                              {sentimentChartData.map((row, i) => {
                                const score = Number(row.sentiment_score);
                                const fill =
                                  score >= 6.5
                                    ? "#10b981"
                                    : score >= 4.0
                                    ? "#f59e0b"
                                    : "#ef4444";
                                return <Cell key={i} fill={fill} />;
                              })}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                          No sentiment data available for this portfolio yet.
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

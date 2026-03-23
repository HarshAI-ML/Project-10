import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Loader from "../components/Loader";
import { fetchLiveStockComparison, searchLiveStocks } from "../api/stocks";
import { formatMoney } from "../utils/currency";

const RANGE_OPTIONS = [
  { key: "1Y", label: "1Y", period: "1y", interval: "1d" },
  { key: "3Y", label: "3Y", period: "3y", interval: "1wk" },
  { key: "5Y", label: "5Y", period: "5y", interval: "1wk" },
];
const FIXED_COMMODITY_OPTIONS = [
  { symbol: "GC=F", company_name: "Gold Futures" },
  { symbol: "SI=F", company_name: "Silver Futures" },
];

function formatPe(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(2);
}

function correlationStrengthLabel(value) {
  if (!Number.isFinite(value)) {
    return "Correlation unavailable";
  }
  const absValue = Math.abs(value);
  let label = "Very weak correlation";
  if (absValue >= 0.8) {
    label = "Highly correlated";
  } else if (absValue >= 0.6) {
    label = "Strongly correlated";
  } else if (absValue >= 0.4) {
    label = "Moderately correlated";
  } else if (absValue >= 0.2) {
    label = "Weakly correlated";
  }
  if (value < 0) {
    label = label.replace("correlated", "inversely correlated");
  }
  return `${label} - ${value.toFixed(3)}`;
}

function optionLabel(option) {
  return `${option.symbol} - ${option.company_name}`;
}

function mergeUniqueSuggestions(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    const key = String(row.symbol || "").toUpperCase();
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function StockSearchInput({
  label,
  value,
  onValueChange,
  selected,
  suggestions,
  searching,
  onPick,
  onFocus,
  onBlur,
  open,
}) {
  return (
    <div className="relative">
      <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-600">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={onValueChange}
        onFocus={onFocus}
        onBlur={onBlur}
        className="input"
        placeholder="Search ticker or company name"
      />
      {selected && (
        <p className="mt-1 text-xs text-emerald-700">
          Selected: {selected.symbol} - {selected.company_name}
        </p>
      )}
      {open && (searching || suggestions.length > 0) && (
        <div className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {searching && <div className="px-3 py-2 text-sm text-slate-500">Searching...</div>}
          {!searching &&
            suggestions.map((item) => (
              <button
                key={`${label}-${item.symbol}`}
                type="button"
                className="block w-full border-b border-slate-100 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                onMouseDown={() => onPick(item)}
              >
                {optionLabel(item)}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

export default function CompareStocks() {
  const [rangeKey, setRangeKey] = useState("5Y");
  const [inputA, setInputA] = useState("");
  const [inputB, setInputB] = useState("");
  const [selectedA, setSelectedA] = useState(null);
  const [selectedB, setSelectedB] = useState(null);
  const [suggestionsA, setSuggestionsA] = useState([]);
  const [suggestionsB, setSuggestionsB] = useState([]);
  const [searchingA, setSearchingA] = useState(false);
  const [searchingB, setSearchingB] = useState(false);
  const [openA, setOpenA] = useState(false);
  const [openB, setOpenB] = useState(false);

  const [compareData, setCompareData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedRange = useMemo(
    () => RANGE_OPTIONS.find((item) => item.key === rangeKey) || RANGE_OPTIONS[2],
    [rangeKey]
  );

  useEffect(() => {
    const query = inputA.trim();
    if (!query || (selectedA && optionLabel(selectedA) === inputA)) {
      setSuggestionsA([]);
      return;
    }

    const timer = setTimeout(async () => {
      setSearchingA(true);
      try {
        const rows = await searchLiveStocks(query, 8);
        setSuggestionsA(
          mergeUniqueSuggestions([
            ...FIXED_COMMODITY_OPTIONS,
            ...(Array.isArray(rows) ? rows : []),
          ])
        );
      } catch {
        setSuggestionsA(FIXED_COMMODITY_OPTIONS);
      } finally {
        setSearchingA(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [inputA, selectedA]);

  useEffect(() => {
    const query = inputB.trim();
    if (!query || (selectedB && optionLabel(selectedB) === inputB)) {
      setSuggestionsB([]);
      return;
    }

    const timer = setTimeout(async () => {
      setSearchingB(true);
      try {
        const rows = await searchLiveStocks(query, 8);
        setSuggestionsB(
          mergeUniqueSuggestions([
            ...FIXED_COMMODITY_OPTIONS,
            ...(Array.isArray(rows) ? rows : []),
          ])
        );
      } catch {
        setSuggestionsB(FIXED_COMMODITY_OPTIONS);
      } finally {
        setSearchingB(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [inputB, selectedB]);

  const canCompare =
    Boolean(selectedA?.symbol) &&
    Boolean(selectedB?.symbol) &&
    selectedA.symbol !== selectedB.symbol;

  const runComparison = async () => {
    if (!selectedA || !selectedB) {
      setError("Please select both Stock A and Stock B from search results.");
      return;
    }
    if (selectedA.symbol === selectedB.symbol) {
      setError("Please select two different stock tickers.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const data = await fetchLiveStockComparison(selectedA.symbol, selectedB.symbol, {
        period: selectedRange.period,
        interval: selectedRange.interval,
      });
      setCompareData(data);
    } catch (err) {
      setCompareData(null);
      setError(err?.response?.data?.detail || "Failed to compare stocks.");
    } finally {
      setLoading(false);
    }
  };

  const historicalData = useMemo(() => {
    if (!compareData?.historical?.length) {
      return [];
    }
    return compareData.historical.map((row) => ({
      date: row.date,
      [compareData.stock_a.symbol]: row.price_a,
      [compareData.stock_b.symbol]: row.price_b,
    }));
  }, [compareData]);

  const scatterData = useMemo(() => compareData?.scatter || [], [compareData]);

  return (
    <section className="space-y-6">
      <div className="card p-5">
        <h1 className="text-2xl font-bold text-slate-900">Compare Stocks</h1>
        <p className="mt-1 text-sm text-slate-600">
          Search and select any two stocks, then compare live data from Yahoo Finance.
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <StockSearchInput
            label="Stock A"
            value={inputA}
            onValueChange={(event) => {
              setInputA(event.target.value);
              setSelectedA(null);
              setOpenA(true);
            }}
            selected={selectedA}
            suggestions={suggestionsA}
            searching={searchingA}
            onPick={(item) => {
              setSelectedA(item);
              setInputA(optionLabel(item));
              setOpenA(false);
              setSuggestionsA([]);
            }}
            onFocus={() => setOpenA(true)}
            onBlur={() => setTimeout(() => setOpenA(false), 120)}
            open={openA}
          />

          <StockSearchInput
            label="Stock B"
            value={inputB}
            onValueChange={(event) => {
              setInputB(event.target.value);
              setSelectedB(null);
              setOpenB(true);
            }}
            selected={selectedB}
            suggestions={suggestionsB}
            searching={searchingB}
            onPick={(item) => {
              setSelectedB(item);
              setInputB(optionLabel(item));
              setOpenB(false);
              setSuggestionsB([]);
            }}
            onFocus={() => setOpenB(true)}
            onBlur={() => setTimeout(() => setOpenB(false), 120)}
            open={openB}
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => setRangeKey(option.key)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                  option.key === rangeKey ? "bg-brand-600 text-white" : "text-slate-700 hover:bg-white"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          <button type="button" onClick={runComparison} className="btn-primary" disabled={!canCompare || loading}>
            {loading ? "Comparing..." : "Run Comparison"}
          </button>
        </div>

        {!canCompare && (
          <p className="mt-2 text-xs text-slate-500">
            Select two different stocks from autocomplete suggestions to enable comparison.
          </p>
        )}
      </div>

      {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      {loading ? (
        <div className="card p-8">
          <Loader />
        </div>
      ) : (
        compareData && (
          <>
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="card p-5">
                <h2 className="text-lg font-semibold text-slate-900">{compareData.stock_a.company_name}</h2>
                <p className="mt-1 text-xs text-slate-500">{compareData.stock_a.symbol}</p>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Current Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_a.current_price, compareData.stock_a.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Min Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_a.min_price, compareData.stock_a.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Max Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_a.max_price, compareData.stock_a.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Today Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_a.today_price, compareData.stock_a.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">PE Ratio</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatPe(compareData.stock_a.pe_ratio)}</p>
                  </div>
                </div>
              </div>

              <div className="card p-5">
                <h2 className="text-lg font-semibold text-slate-900">{compareData.stock_b.company_name}</h2>
                <p className="mt-1 text-xs text-slate-500">{compareData.stock_b.symbol}</p>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Current Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_b.current_price, compareData.stock_b.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Min Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_b.min_price, compareData.stock_b.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Max Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_b.max_price, compareData.stock_b.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Today Price</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(compareData.stock_b.today_price, compareData.stock_b.currency)}</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">PE Ratio</p>
                    <p className="mt-2 text-xl font-bold text-slate-900">{formatPe(compareData.stock_b.pe_ratio)}</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="card p-5">
              <h2 className="text-lg font-semibold text-slate-900">Historical Price Comparison (Adjusted Close)</h2>
              <div className="mt-4 h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={historicalData} margin={{ top: 12, right: 16, left: 8, bottom: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 12 }} width={68} />
                    <Tooltip />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey={compareData.stock_a.symbol}
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={false}
                      name={compareData.stock_a.symbol}
                    />
                    <Line
                      type="monotone"
                      dataKey={compareData.stock_b.symbol}
                      stroke="#ea580c"
                      strokeWidth={2}
                      dot={false}
                      name={compareData.stock_b.symbol}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h2 className="text-lg font-semibold text-slate-900">Correlation Scatter Plot</h2>
                <div className="rounded-md bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                  {correlationStrengthLabel(Number(compareData.pearson_correlation))}
                </div>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                Regression equation: {compareData.regression.equation}
              </p>
              <div className="mt-4 h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={scatterData} margin={{ top: 10, right: 10, left: 4, bottom: 18 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis
                      type="number"
                      dataKey="x"
                      name={compareData.stock_a.symbol}
                      tick={{ fontSize: 11 }}
                      label={{ value: `${compareData.stock_a.symbol} Price`, position: "insideBottom", offset: -8 }}
                    />
                    <YAxis
                      type="number"
                      dataKey="y"
                      name={compareData.stock_b.symbol}
                      tick={{ fontSize: 11 }}
                      label={{ value: `${compareData.stock_b.symbol} Price`, angle: -90, position: "insideLeft" }}
                      width={74}
                    />
                    <Tooltip
                      formatter={(value, name) => [Number(value).toFixed(3), name]}
                      labelFormatter={(label, payload) => payload?.[0]?.payload?.date || label}
                    />
                    <Legend />
                    <Scatter name="Observed" data={scatterData} fill="#2563eb" />
                    <Line type="linear" dataKey="y_fit" name="Best Fit" stroke="#ef4444" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )
      )}
    </section>
  );
}

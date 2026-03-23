import { useEffect, useMemo, useRef, useState } from "react";
import {
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
import { fetchPredictionOptions, runPricePrediction } from "../api/prediction";
import { formatMoney } from "../utils/currency";

const initialForm = {
  stock_symbol: "",
  historical_period: "1y",
  model_type: "xgboost",
  prediction_frequency: "daily",
};

const SearchableDropdown = ({ value, onChange, options, disabled }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const wrapperRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filteredOptions = (options || []).filter(
    (item) =>
      item.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.company_name && item.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const selectedOption = (options || []).find((opt) => opt.symbol === value);

  return (
    <div className="relative w-full" ref={wrapperRef}>
      <button
        type="button"
        className="input w-full flex items-center justify-between text-left"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
      >
        <span className="truncate">
          {selectedOption
            ? `${selectedOption.symbol} - ${selectedOption.company_name || selectedOption.symbol}`
            : (!options || options.length === 0)
              ? "No stocks available"
              : "Select a stock"}
        </span>
        <svg
          className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute z-10 mt-1 flex max-h-60 w-full flex-col rounded-md border border-slate-200 bg-white shadow-lg">
          <div className="sticky top-0 z-20 border-b border-slate-100 bg-white p-2">
            <input
              type="text"
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Search stocks..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
          <ul className="w-full overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <li className="cursor-not-allowed px-4 py-2 text-sm text-slate-500">
                No matches found
              </li>
            ) : (
              filteredOptions.map((item) => (
                <li
                  key={item.symbol}
                  className={`cursor-pointer px-4 py-2 text-sm hover:bg-slate-100 ${value === item.symbol
                      ? "bg-blue-50 font-medium text-blue-700"
                      : "text-slate-700"
                    }`}
                  onClick={() => {
                    onChange(item.symbol);
                    setIsOpen(false);
                    setSearchTerm("");
                  }}
                >
                  {item.symbol} - {item.company_name || item.symbol}
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
};

export default function PricePrediction() {
  const [form, setForm] = useState(initialForm);
  const [options, setOptions] = useState({
    stocks: [],
    historical_periods: [],
    models: [],
    prediction_frequencies: [],
  });
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const filteredHistoricalPeriods = useMemo(() => {
    const periods = options.historical_periods || [];
    if (form.prediction_frequency !== "hourly") return periods;
    return periods.filter((item) => item.value !== "5y");
  }, [options.historical_periods, form.prediction_frequency]);

  useEffect(() => {
    if (form.prediction_frequency !== "hourly") return;
    if (form.historical_period !== "5y") return;
    const fallback = filteredHistoricalPeriods.find((item) => item.value === "2y")
      || filteredHistoricalPeriods[0];
    if (fallback) {
      setForm((prev) => ({ ...prev, historical_period: fallback.value }));
    }
  }, [form.prediction_frequency, form.historical_period, filteredHistoricalPeriods]);

  useEffect(() => {
    const loadOptions = async () => {
      setLoadingOptions(true);
      setError("");
      try {
        const data = await fetchPredictionOptions();
        setOptions(data || {});
        const firstSymbol = data?.stocks?.[0]?.symbol || "";
        setForm((prev) => ({
          ...prev,
          stock_symbol: prev.stock_symbol || firstSymbol,
        }));
      } catch {
        setError("Unable to load prediction options.");
      } finally {
        setLoadingOptions(false);
      }
    };
    loadOptions();
  }, []);

  const historicalChart = useMemo(() => {
    if (!result?.historical_dates?.length) return [];
    return result.historical_dates.map((date, idx) => ({
      date,
      historical: Number(result.historical_prices?.[idx] || 0),
    }));
  }, [result]);

  const predictionChart = useMemo(() => {
    if (!result?.actual_dates?.length) return [];
    return result.actual_dates.map((date, idx) => ({
      date,
      actual: Number(result.actual_prices?.[idx] || 0),
      predicted: Number(result.predicted_prices?.[idx] || 0),
    }));
  }, [result]);

  const forecastChart = useMemo(() => {
    if (!result?.forecast_dates?.length) return [];
    const historyTail = result?.prediction_frequency === "hourly" ? 200 : 120;
    const recent = (result.historical_dates || []).slice(-historyTail).map((date, idx, arr) => {
      const sourceIndex = (result.historical_dates || []).length - arr.length + idx;
      return {
        date,
        recent: Number(result.historical_prices?.[sourceIndex] || 0),
        forecast: null,
      };
    });
    const future = (result.forecast_dates || []).map((date, idx) => ({
      date,
      recent: null,
      forecast: Number(result.forecast_prices?.[idx] || 0),
    }));
    return [...recent, ...future];
  }, [result]);

  const forecastRows = useMemo(() => {
    if (!result?.forecast_dates?.length) return [];
    return result.forecast_dates.map((date, idx) => ({
      date,
      price: Number(result.forecast_prices?.[idx] || 0),
    }));
  }, [result]);

  const handleChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.stock_symbol) {
      setError("Please select a stock symbol.");
      return;
    }

    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const response = await runPricePrediction(form);
      setResult(response);
      if (response?.cache_hit) {
        setMessage("Showing cached prediction generated within the last 24 hours.");
      } else {
        setMessage("New prediction generated successfully.");
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const timeout = err?.code === "ECONNABORTED";
      const network = !err?.response;
      const fallback = timeout
        ? "Prediction timed out. Please try again."
        : network
          ? "Network/server error while generating prediction. Please try again."
          : "Prediction request failed. Please try again.";
      const text = detail || fallback;
      setError(text);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Price Prediction</h1>
      </div>

      <form className="card grid gap-4 p-6 md:grid-cols-2 xl:grid-cols-5" onSubmit={handleSubmit}>
        <label className="space-y-2">
          <span className="text-sm font-semibold text-slate-700">
            Stock Selector{" "}
            <span className="text-xs font-normal text-slate-500">
              (Portfolio stocks only)
            </span>
          </span>
          <SearchableDropdown
            value={form.stock_symbol}
            onChange={(val) => handleChange("stock_symbol", val)}
            options={options.stocks}
            disabled={loadingOptions || submitting}
          />
        </label>

        <label className="space-y-2">
          <span className="text-sm font-semibold text-slate-700">Historical Data Period</span>
          <select
            className="input"
            value={form.historical_period}
            disabled={loadingOptions || submitting}
            onChange={(e) => handleChange("historical_period", e.target.value)}
          >
            {filteredHistoricalPeriods.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2">
          <span className="text-sm font-semibold text-slate-700">Model Selection</span>
          <select
            className="input"
            value={form.model_type}
            disabled={loadingOptions || submitting}
            onChange={(e) => handleChange("model_type", e.target.value)}
          >
            {(options.models || []).map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2">
          <span className="text-sm font-semibold text-slate-700">Prediction Frequency</span>
          <select
            className="input"
            value={form.prediction_frequency}
            disabled={loadingOptions || submitting}
            onChange={(e) => handleChange("prediction_frequency", e.target.value)}
          >
            {(options.prediction_frequencies || []).map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-end">
          <button type="submit" className="btn-primary w-full" disabled={loadingOptions || submitting}>
            {submitting ? "Predicting..." : "Predict"}
          </button>
        </div>
      </form>

      {loadingOptions && (
        <div className="card p-6">
          <Loader />
        </div>
      )}
      {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}
      {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      {result && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-slate-900">
              {result.stock} - {result.model} ({result.prediction_frequency})
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Next forecast points: {result.forecast_prices?.length || 0}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              Last forecast value: {formatMoney(result.forecast_prices?.[(result.forecast_prices?.length || 1) - 1], "USD")}
            </p>
          </div>

          <div className="card p-6">
            <h3 className="text-base font-semibold text-slate-900">Historical Price Chart</h3>
            <div className="mt-4 h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={historicalChart} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" strokeOpacity={0.7} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="historical" stroke="#2563eb" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-base font-semibold text-slate-900">Prediction vs Actual</h3>
            <div className="mt-4 h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={predictionChart} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" strokeOpacity={0.7} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="actual" stroke="#0f766e" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="predicted" stroke="#dc2626" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-base font-semibold text-slate-900">Recent + Forecast Chart</h3>
            <div className="mt-4 h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={forecastChart} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" strokeOpacity={0.7} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="recent" name="Recent Price" stroke="#2563eb" strokeWidth={2} dot={false} />
                  <Line
                    type="monotone"
                    dataKey="forecast"
                    name={result.prediction_frequency === "hourly" ? "24-Hour Forecast" : "Forecast"}
                    stroke="#dc2626"
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    dot={false}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-base font-semibold text-slate-900">Forecast Table</h3>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Date/Time</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">Forecast Price</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {forecastRows.map((row) => (
                    <tr key={row.date}>
                      <td className="px-4 py-3 text-sm text-slate-700">{row.date}</td>
                      <td className="px-4 py-3 text-right text-sm font-semibold text-slate-900">
                        {formatMoney(row.price, "USD")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="card p-4">
              <h4 className="mb-3 text-sm font-semibold text-slate-700">Feature Importance</h4>
              {result.plots?.feature_importance ? (
                <img
                  className="w-full rounded-lg border border-slate-200"
                  src={result.plots.feature_importance}
                  alt="Feature importance"
                />
              ) : (
                <p className="text-sm text-slate-500">Not available for this model.</p>
              )}
            </div>
            <div className="card p-4">
              <h4 className="mb-3 text-sm font-semibold text-slate-700">Training Metrics</h4>
              {result.plots?.training_loss ? (
                <img
                  className="w-full rounded-lg border border-slate-200"
                  src={result.plots.training_loss}
                  alt="Training loss"
                />
              ) : (
                <p className="text-sm text-slate-500">Training chart unavailable.</p>
              )}
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-600">
                <span>MAE: {result.training_metrics?.mae ?? "-"}</span>
                <span>RMSE: {result.training_metrics?.rmse ?? "-"}</span>
                <span>R2: {result.training_metrics?.r2 ?? "-"}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

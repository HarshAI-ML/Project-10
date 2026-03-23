import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
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
import OpportunityBadge from "../components/OpportunityBadge";
import StockCard from "../components/StockCard";
import { fetchLiveStockBySymbol } from "../api/stocks";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

export default function LiveStockDetail() {
  const { symbol } = useParams();
  const location = useLocation();
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadStock = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchLiveStockBySymbol(symbol);
        setStock(data);
      } catch {
        setError("Failed to load live stock details.");
      } finally {
        setLoading(false);
      }
    };

    loadStock();
  }, [symbol]);

  const chartData = useMemo(() => {
    const graph = stock?.analytics?.graph_data;
    const dates = graph?.dates || [];
    const prices = graph?.price || [];
    const movingAvg = graph?.moving_avg || [];

    return dates.map((date, index) => ({
      date,
      price: prices[index],
      moving_avg: movingAvg[index],
    }));
  }, [stock]);

  if (loading) {
    return (
      <div className="card p-5">
        <Loader />
      </div>
    );
  }

  if (error) {
    return <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>;
  }

  if (!stock) {
    return <div className="card p-5 text-sm text-slate-500">Live stock not found.</div>;
  }

  const backPath = location.state?.from || "/stocks";
  const currencyCode = currencyCodeFromItem(stock);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Live Stock Analytics</h1>
        <Link to={backPath} className="btn-secondary">
          Back to Stocks
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <StockCard stock={{ ...stock, discount_level: stock.analytics?.discount_level }} />
        </div>

        <div className="card p-5 lg:col-span-2">
          <h2 className="text-lg font-semibold text-slate-900">Price Snapshot</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">Current Price</p>
              <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(stock.current_price, currencyCode)}</p>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">Min Price</p>
              <p className="mt-2 text-xl font-bold text-slate-900">
                {formatMoney(stock.min_price, currencyCode)}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">Max Price</p>
              <p className="mt-2 text-xl font-bold text-slate-900">
                {formatMoney(stock.max_price, currencyCode)}
              </p>
            </div>
          </div>

          <h2 className="mt-6 text-lg font-semibold text-slate-900">Analytics</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">PE Ratio</p>
              <p className="mt-2 text-xl font-bold text-slate-900">{stock.analytics?.pe_ratio ?? "-"}</p>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">Discount Level</p>
              <div className="mt-2">
                <OpportunityBadge level={stock.analytics?.discount_level} />
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">Opportunity Score</p>
              <p className="mt-2 text-xl font-bold text-brand-900">{stock.analytics?.opportunity_score ?? "-"}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="text-lg font-semibold text-slate-900">1Y Price Graph</h2>
        <div className="mt-4 h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="price" stroke="#2563eb" strokeWidth={2} dot={false} name="Price" />
              <Line
                type="monotone"
                dataKey="moving_avg"
                stroke="#16a34a"
                strokeWidth={2}
                dot={false}
                name="Moving Avg"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}


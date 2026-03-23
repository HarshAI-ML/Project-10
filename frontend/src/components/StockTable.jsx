import { useLocation, useNavigate } from "react-router-dom";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

const statusLabel = (stock) =>
  stock.prediction_status === "insufficient_data" ? "Low Data" : "—";

export default function StockTable({ stocks, onDeleteStock, deletingStockId }) {
  const navigate  = useNavigate();
  const location  = useLocation();

  const handleRowClick = (stock) => {
    if (stock.id) {
      navigate(`/stocks/${stock.id}`, { state: { from: `${location.pathname}${location.search}` } });
    } else if (stock.symbol) {
      navigate(`/stocks/${encodeURIComponent(stock.symbol)}`, { state: { from: `${location.pathname}${location.search}` } });
    }
  };

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
      {/* disclaimer */}
      <div className="flex items-center gap-2 border-b border-slate-100 bg-amber-50/60 px-5 py-2.5">
        <svg className="h-3.5 w-3.5 flex-shrink-0 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
        </svg>
        <span className="text-xs text-amber-700 font-medium">
          Predictions based on 1-year linear regression. For informational purposes only.
        </span>
      </div>

      <div className="max-h-[70vh] overflow-auto thin-scroll">
        <table className="min-w-full">
          <thead>
            <tr className="sticky top-0 z-10 bg-slate-900 text-white">
              {["Symbol", "Company", "Price", "Min", "Max", "Predicted (1D)", "% Change", "Signal", "R²", "PE", "Discount", ""].map(
                (h) => (
                  <th
                    key={h}
                    className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap ${
                      h === "" || h === "Symbol" || h === "Company" || h === "Signal" || h === "Discount"
                        ? "text-left"
                        : "text-right"
                    }`}
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-50">
            {stocks.map((stock) => {
              const ok       = stock.prediction_status === "ok";
              const currency = currencyCodeFromItem(stock);
              const changeUp = ok && Number(stock.expected_change_pct || 0) >= 0;
              const isIncrease = stock.direction_signal?.includes("Increase");
              const clickable = stock.id || stock.symbol;

              return (
                <tr
                  key={stock.id ?? stock.symbol}
                  className={`group transition-colors ${
                    clickable ? "cursor-pointer hover:bg-indigo-50/40" : "cursor-default"
                  }`}
                  onClick={() => handleRowClick(stock)}
                >
                  {/* Symbol */}
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm font-bold text-slate-900">{stock.symbol}</span>
                  </td>

                  {/* Company */}
                  <td className="max-w-[160px] px-4 py-3">
                    <span className="block truncate text-sm text-slate-600">{stock.company_name}</span>
                  </td>

                  {/* Price */}
                  <td className="px-4 py-3 text-right text-sm font-semibold text-slate-900">
                    {formatMoney(stock.current_price, currency)}
                  </td>

                  {/* Min */}
                  <td className="px-4 py-3 text-right text-sm text-slate-400">
                    {formatMoney(stock.min_price, currency)}
                  </td>

                  {/* Max */}
                  <td className="px-4 py-3 text-right text-sm text-slate-400">
                    {formatMoney(stock.max_price, currency)}
                  </td>

                  {/* Predicted */}
                  <td className="px-4 py-3 text-right">
                    <span className={`text-sm font-semibold ${ok ? "text-indigo-700" : "text-slate-400"}`}>
                      {ok ? formatMoney(stock.predicted_price_1d, currency) : statusLabel(stock)}
                    </span>
                  </td>

                  {/* % Change */}
                  <td className="px-4 py-3 text-right">
                    {ok ? (
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          changeUp
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-rose-100 text-rose-600"
                        }`}
                      >
                        {changeUp ? "+" : ""}{Number(stock.expected_change_pct || 0).toFixed(2)}%
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">{statusLabel(stock)}</span>
                    )}
                  </td>

                  {/* Signal */}
                  <td className="px-4 py-3">
                    {ok ? (
                      <span
                        className={`inline-flex items-center gap-1 text-xs font-semibold ${
                          isIncrease ? "text-emerald-600" : "text-rose-500"
                        }`}
                      >
                        {isIncrease ? "▲" : "▼"} {stock.direction_signal}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">{statusLabel(stock)}</span>
                    )}
                  </td>

                  {/* R² */}
                  <td className="px-4 py-3 text-right text-sm text-slate-500">
                    {ok ? Number(stock.model_confidence_r2 || 0).toFixed(2) : "—"}
                  </td>

                  {/* PE */}
                  <td className="px-4 py-3 text-right text-sm text-slate-500">
                    {stock.pe_ratio ?? "—"}
                  </td>

                  {/* Discount */}
                  <td className="px-4 py-3">
                    {stock.discount_level && (
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          stock.discount_level === "HIGH"
                            ? "bg-emerald-100 text-emerald-700"
                            : stock.discount_level === "MEDIUM"
                            ? "bg-amber-100 text-amber-600"
                            : "bg-rose-100 text-rose-500"
                        }`}
                      >
                        {stock.discount_level}
                      </span>
                    )}
                  </td>

                  {/* Delete */}
                  <td className="px-4 py-3 text-right">
                    {stock.id && (
                      <button
                        type="button"
                        className="rounded-lg border border-rose-100 bg-white px-2.5 py-1 text-xs font-semibold text-rose-500 opacity-0 transition group-hover:opacity-100 hover:bg-rose-50 disabled:opacity-40"
                        disabled={deletingStockId === stock.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (onDeleteStock) onDeleteStock(stock.id, stock.symbol);
                        }}
                      >
                        {deletingStockId === stock.id ? "…" : "Remove"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

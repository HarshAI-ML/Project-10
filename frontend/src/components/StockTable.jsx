import { useLocation, useNavigate } from "react-router-dom";
import { currencyCodeFromItem, formatMoney } from "../utils/currency";

const statusLabel = (stock) => (stock.prediction_status === "insufficient_data" ? "Low Data" : "—");

const normalizeAction = (value) => {
  const text = String(value || "").trim().toUpperCase();
  if (text === "BUY" || text.includes("BUY")) return "BUY";
  if (text === "SELL" || text.includes("SELL") || text.includes("REDUCE")) return "SELL";
  if (text === "HOLD" || text.includes("HOLD")) return "HOLD";
  return "";
};

const ActionBadge = ({ action }) => {
  const normalized = normalizeAction(action);
  if (!normalized) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const style =
    normalized === "BUY"
      ? "bg-emerald-100 text-emerald-700"
      : normalized === "SELL"
      ? "bg-rose-100 text-rose-600"
      : "bg-amber-100 text-amber-700";
  return <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${style}`}>{normalized}</span>;
};

const SortableHeader = ({ col, label, sortCol, sortDir, onSort, align = "left" }) => {
  const isActive = sortCol === col;
  const icon = !isActive ? " ⇅" : sortDir === "asc" ? " ↑" : " ↓";
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";

  return (
    <th
      className={`cursor-pointer select-none px-2.5 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-100/95 whitespace-nowrap hover:text-cyan-200 transition-colors ${alignClass}`}
      onClick={() => {
        if (!onSort) return;
        if (sortCol === col) {
          onSort(col, sortDir === "asc" ? "desc" : "asc");
        } else {
          onSort(col, "desc");
        }
      }}
    >
      {label}
      {icon}
    </th>
  );
};

export default function StockTable({
  stocks,
  onDeleteStock,
  deletingStockId,
  sortCol,
  sortDir,
  onSort,
  selectable = false,
  selectedSymbols = new Set(),
  onToggleSelect = null,
  disableRowNavigation = false,
  showDeleteAction = true,
  noticeText = "Predictions based on 1-year linear regression. For informational purposes only.",
}) {
  const navigate = useNavigate();
  const location = useLocation();

  const isSelected = (stock) => selectedSymbols?.has?.(String(stock.symbol || "").toUpperCase());

  const handleRowClick = (stock) => {
    if (disableRowNavigation) return;
    if (stock.id) {
      navigate(`/stocks/${stock.id}`, { state: { from: `${location.pathname}${location.search}` } });
    } else if (stock.symbol) {
      navigate(`/stocks/${encodeURIComponent(stock.symbol)}`, { state: { from: `${location.pathname}${location.search}` } });
    }
  };

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
      <div className="flex items-center gap-2 border-b border-slate-100 bg-amber-50/60 px-5 py-2.5">
        <svg className="h-3.5 w-3.5 flex-shrink-0 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
        <span className="text-xs font-medium text-amber-700">{noticeText}</span>
      </div>

      <div className="max-h-[70vh] overflow-y-auto overflow-x-hidden thin-scroll">
        <table className="w-full table-fixed text-[13px] text-slate-700 [font-variant-numeric:tabular-nums]">
          <colgroup>
            {selectable && <col className="w-[4%]" />}
            <col className="w-[10%]" />
            <col className="w-[14%]" />
            <col className="w-[8%]" />
            <col className="w-[7%]" />
            <col className="w-[7%]" />
            <col className="w-[8%]" />
            <col className="w-[6%]" />
            <col className="w-[6%]" />
            <col className="w-[5%]" />
            <col className="w-[6%]" />
            <col className="w-[8%]" />
            <col className="w-[9%]" />
            <col className="w-[6%]" />
          </colgroup>
          <thead>
            <tr className="sticky top-0 z-10 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white shadow-sm">
              {selectable && <th className="whitespace-nowrap px-2.5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide">Select</th>}
              <SortableHeader col="symbol" label="Symbol" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="left" />
              <th className="whitespace-nowrap px-2.5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide">Company</th>
              <SortableHeader col="current_price" label="Price" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="right" />
              <th className="whitespace-nowrap px-2.5 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide">Min</th>
              <th className="whitespace-nowrap px-2.5 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide">Max</th>
              <SortableHeader col="predicted_price_1d" label="Predicted" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="right" />
              <SortableHeader col="expected_change_pct" label="% Change" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="right" />
              <SortableHeader col="recommended_action" label="Signal" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="center" />
              <SortableHeader col="model_confidence_r2" label="R²" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="right" />
              <SortableHeader col="pe_ratio" label="PE" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="right" />
              <SortableHeader col="discount_pct" label="Discount %" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="center" />
              <SortableHeader col="sentiment_score" label="Sentiment" sortCol={sortCol} sortDir={sortDir} onSort={onSort} align="center" />
              {showDeleteAction && <th className="whitespace-nowrap px-2.5 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide">Action</th>}
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-100">
            {stocks.map((stock) => {
              const ok =
                stock.prediction_status === "ok" ||
                stock.prediction_status === "ready" ||
                (stock.predicted_price_1d !== null && stock.predicted_price_1d !== undefined);
              const currency = currencyCodeFromItem(stock);
              const changeUp = ok && Number(stock.expected_change_pct || 0) >= 0;
              const clickable = (stock.id || stock.symbol) && !disableRowNavigation;

              return (
                <tr
                  key={stock.id ?? stock.symbol}
                  className={`group transition-colors ${
                    clickable ? "cursor-pointer odd:bg-white even:bg-slate-50/55 hover:bg-indigo-50/65" : "cursor-default"
                  }`}
                  onClick={() => handleRowClick(stock)}
                >
                  {selectable && (
                    <td className="px-2.5 py-2.5">
                      <input
                        type="checkbox"
                        checked={isSelected(stock)}
                        onChange={() => onToggleSelect?.(stock)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500"
                      />
                    </td>
                  )}

                  <td className="px-2.5 py-2.5">
                    <span className="block truncate text-[13px] font-semibold tracking-tight text-slate-900">{stock.symbol}</span>
                  </td>

                  <td className="px-2.5 py-2.5">
                    <span className="block truncate text-[12px] text-slate-600">{stock.company_name}</span>
                  </td>

                  <td className="px-2.5 py-2.5 text-right text-[13px] font-semibold text-slate-900 truncate">
                    {formatMoney(stock.current_price, currency)}
                  </td>

                  <td className="px-2.5 py-2.5 text-right text-[12px] text-slate-500 truncate">
                    {formatMoney(stock.min_price, currency)}
                  </td>

                  <td className="px-2.5 py-2.5 text-right text-[12px] text-slate-500 truncate">
                    {formatMoney(stock.max_price, currency)}
                  </td>

                  <td className="px-2.5 py-2.5 text-right">
                    <span className={`block truncate text-[13px] font-semibold ${ok ? "text-indigo-700" : "text-slate-400"}`}>
                      {ok ? formatMoney(stock.predicted_price_1d, currency) : statusLabel(stock)}
                    </span>
                  </td>

                  <td className="px-2.5 py-2.5 text-right">
                    {ok ? (
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${
                          changeUp ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-600"
                        }`}
                      >
                        {changeUp ? "+" : ""}
                        {Number(stock.expected_change_pct || 0).toFixed(2)}%
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">{statusLabel(stock)}</span>
                    )}
                  </td>

                  <td className="px-2.5 py-2.5 text-center">
                    {normalizeAction(stock.recommended_action) ? (
                      <ActionBadge action={stock.recommended_action} />
                    ) : ok && stock.direction_signal ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600">{stock.direction_signal}</span>
                    ) : (
                      <span className="text-xs text-slate-400">{statusLabel(stock)}</span>
                    )}
                  </td>

                  <td className="px-2.5 py-2.5 text-right text-[12px] text-slate-600">
                    {ok ? Number(stock.model_confidence_r2 || 0).toFixed(2) : "—"}
                  </td>

                  <td className="px-2.5 py-2.5 text-right text-[12px] text-slate-600 truncate">{stock.pe_ratio ?? "—"}</td>

                  <td className="px-2.5 py-2.5 text-center">
                    {stock.discount_pct !== null && stock.discount_pct !== undefined ? (
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${
                          Number(stock.discount_pct) >= 20
                            ? "bg-emerald-100 text-emerald-700"
                            : Number(stock.discount_pct) >= 10
                            ? "bg-amber-100 text-amber-700"
                            : "bg-rose-100 text-rose-600"
                        }`}
                      >
                        {Number(stock.discount_pct) >= 0 ? "+" : ""}
                        {Number(stock.discount_pct).toFixed(2)}%
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>

                  <td className="px-2.5 py-2.5 text-center">
                    {stock.sentiment_score !== null && stock.sentiment_score !== undefined ? (
                      <span
                        className={`inline-block max-w-full truncate rounded-full px-2 py-0.5 text-[11px] font-bold ${
                          Number(stock.sentiment_score) >= 6.5
                            ? "bg-emerald-100 text-emerald-700"
                            : Number(stock.sentiment_score) >= 4.0
                            ? "bg-amber-100 text-amber-700"
                            : "bg-rose-100 text-rose-600"
                        }`}
                      >
                        {Number(stock.sentiment_score).toFixed(2)} ({stock.sentiment_label || "Neutral"})
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>

                  {showDeleteAction && (
                    <td className="px-2.5 py-2.5 text-right whitespace-nowrap">
                      {stock.symbol && (
                        <button
                          type="button"
                          className="rounded-md border border-rose-100 bg-white px-2 py-1 text-[11px] font-semibold text-rose-500 opacity-100 transition md:opacity-0 md:group-hover:opacity-100 hover:bg-rose-50 disabled:opacity-40"
                          disabled={deletingStockId === stock.symbol}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (onDeleteStock) onDeleteStock(stock.symbol);
                          }}
                        >
                          {deletingStockId === stock.symbol ? "…" : "Remove"}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

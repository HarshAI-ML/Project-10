const SYMBOL_BY_CURRENCY = {
  INR: "Rs",
  USD: "$",
};

export function inferCurrencyCode(symbol, fallback = "USD") {
  const value = String(symbol || "").toUpperCase();
  if (value.endsWith(".NS") || value.endsWith(".BO")) {
    return "INR";
  }
  return fallback;
}

export function currencyCodeFromItem(item, fallback = "USD") {
  const reported = String(item?.currency || "").toUpperCase();
  if (reported) {
    return reported;
  }
  return inferCurrencyCode(item?.symbol, fallback);
}

export function formatMoney(value, currencyCode = "USD") {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  const symbol = SYMBOL_BY_CURRENCY[currencyCode] || `${currencyCode} `;
  return `${symbol} ${Number(value).toFixed(2)}`;
}

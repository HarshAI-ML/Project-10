import api from "./axios";

export const fetchPortfolio = async () => {
  const { data } = await api.get("portfolio/");
  return data;
};

export const createPortfolio = async (payload) => {
  const { data } = await api.post("portfolio/", payload);
  return data;
};

export const addStockToPortfolio = async (portfolioId, symbol) => {
  const { data } = await api.post(`portfolio/${portfolioId}/add-stock/`, { symbol });
  return data;
};

export const removeStockFromPortfolio = async (portfolioId, symbol) => {
  const queryParams = new URLSearchParams({
    symbol: String(symbol || "").toUpperCase(),
  });
  await api.delete(`portfolio/${portfolioId}/remove-stock/?${queryParams.toString()}`);
};

export const fetchStocks = async (portfolioId = null, options = {}) => {
  if (portfolioId) {
    const queryParams = new URLSearchParams({
      portfolio: String(portfolioId),
    });
    if (options.sort_by) queryParams.set("sort_by", String(options.sort_by));
    if (options.sort_order) queryParams.set("sort_order", String(options.sort_order));
    if (options.diff_sign) queryParams.set("diff_sign", String(options.diff_sign));
    if (options.diff_min !== undefined && options.diff_min !== null && options.diff_min !== "") {
      queryParams.set("diff_min", String(options.diff_min));
    }
    if (options.diff_max !== undefined && options.diff_max !== null && options.diff_max !== "") {
      queryParams.set("diff_max", String(options.diff_max));
    }
    if (options.diff_pct_min !== undefined && options.diff_pct_min !== null && options.diff_pct_min !== "") {
      queryParams.set("diff_pct_min", String(options.diff_pct_min));
    }
    if (options.diff_pct_max !== undefined && options.diff_pct_max !== null && options.diff_pct_max !== "") {
      queryParams.set("diff_pct_max", String(options.diff_pct_max));
    }

    const { data } = await api.get(`portfolio-stocks/?${queryParams.toString()}`);
    const rows = Array.isArray(data) ? data : [];
    return rows.map((item) => ({
      id: item.id,
      symbol: item.symbol || item.ticker,
      company_name: item.company_name,
      sector: item.sector,
      geography: item.geography,
      current_price: item.current_price,
      min_price: item.min_price,
      max_price: item.max_price,
      predicted_price_1d: item.predicted_price_1d,
      price_diff: item.price_diff,
      expected_change_pct: item.expected_change_pct,
      direction_signal: item.direction_signal,
      model_confidence_r2: item.model_confidence_r2,
      recommended_action: item.recommended_action,
      sentiment_score: item.sentiment_score,
      sentiment_label: item.sentiment_label,
      sentiment_source: item.sentiment_source,
      prediction_status:
        item.prediction_status ||
        (item.predicted_price_1d !== null && item.predicted_price_1d !== undefined
          ? "ready"
          : "insufficient_data"),
      pe_ratio: item.pe_ratio,
      discount_level: item.discount_level,
      rsi_14: item.rsi_14,
      ma_20: item.ma_20,
      macd: item.macd,
    }));
  }
  const { data } = await api.get("stocks/");
  return Array.isArray(data) ? data : [];
};

export const searchLiveStocks = async (query, limit = 10) => {
  const queryParams = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  const { data } = await api.get(`stocks/live-search/?${queryParams.toString()}`);
  return data;
};

export const fetchLiveStockBySymbol = async (symbol, options = {}) => {
  const queryParams = new URLSearchParams({ symbol });
  if (options.period) {
    queryParams.set("period", options.period);
  }
  if (options.interval) {
    queryParams.set("interval", options.interval);
  }
  const { data } = await api.get(`stocks/live-detail/?${queryParams.toString()}`);
  return data;
};

export const fetchLiveStockComparison = async (symbolA, symbolB, options = {}) => {
  const queryParams = new URLSearchParams({
    symbol_a: symbolA,
    symbol_b: symbolB,
  });
  if (options.period) {
    queryParams.set("period", options.period);
  }
  if (options.interval) {
    queryParams.set("interval", options.interval);
  }
  const { data } = await api.get(`stocks/live-compare/?${queryParams.toString()}`);
  return data;
};

export const fetchStockById = async (id) => {
  const { data } = await api.get(`stocks/${id}/`);
  return data;
};

export const fetchPortfolioClusters = async (portfolioId, nClusters = 3) => {
  const queryParams = new URLSearchParams({
    n_clusters: String(nClusters),
  });
  const { data } = await api.get(`portfolio/${portfolioId}/clusters/?${queryParams.toString()}`, {
    timeout: 120000,
  });
  return data;
};

export const fetchGlobalClusters = async (nClusters = 3) => {
  const queryParams = new URLSearchParams({
    n_clusters: String(nClusters),
  });
  const { data } = await api.get(`stocks/clusters/?${queryParams.toString()}`, {
    timeout: 120000,
  });
  return data;
};

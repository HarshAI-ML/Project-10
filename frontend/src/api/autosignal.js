import api from "./axios";

const AUTOSIGNAL_TIMEOUT_MS = 60000;

export const fetchSectorHeatmap = async () => {
  const { data } = await api.get("autosignal/heatmap/", { timeout: AUTOSIGNAL_TIMEOUT_MS });
  return data;
};

export const fetchCompanySentiment = async (company = null, granularity = "daily") => {
  const params = new URLSearchParams({ granularity });
  if (company) params.set("company", company);
  const { data } = await api.get(`autosignal/sentiment/?${params.toString()}`);
  return data;
};

export const fetchSectorReport = async () => {
  const { data } = await api.get("autosignal/report/", { timeout: AUTOSIGNAL_TIMEOUT_MS });
  return data;
};

export const fetchEvents = async (company = null) => {
  const params = company ? `?company=${encodeURIComponent(company)}` : "";
  const { data } = await api.get(`autosignal/events/${params}`, { timeout: AUTOSIGNAL_TIMEOUT_MS });
  return data;
};
export const fetchCompanyDetail = async (slug) => {
  const { data } = await api.get(`autosignal/company/${slug}/`, {
    timeout: AUTOSIGNAL_TIMEOUT_MS,
  });
  return data;
};

export const fetchSectorInsights = async () => {
  const { data } = await api.get("autosignal/insights/", { timeout: AUTOSIGNAL_TIMEOUT_MS });
  return data;
};

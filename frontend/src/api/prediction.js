import api from "./axios";

export const fetchPredictionOptions = async () => {
  const { data } = await api.get("prediction/");
  return data;
};

export const runPricePrediction = async (payload) => {
  const { data } = await api.post("prediction/run/", payload, {
    timeout: 600000,
  });
  return data;
};

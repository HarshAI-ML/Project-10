import api from "./axios";

export const sendChatMessage = async (payload) => {
  const { data } = await api.post("chat/", payload, { timeout: 30000 });
  return data;
};


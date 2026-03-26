import api from "./axios";

export const sendChatMessage = async (payload) => {
  const { data } = await api.post("chat/", payload, { timeout: 30000 });
  return data;
};

const getChatEndpoint = () => new URL("chat/", api.defaults.baseURL).toString();

const getAuthHeaders = () => {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Token ${token}` } : {};
};

export const sendChatMessageStream = async (payload, { onDelta, onMeta, signal } = {}) => {
  const response = await fetch(getChatEndpoint(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    const error = new Error(errorText || `Chat request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    return { mode: "generic", suggestions: [] };
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let meta = { mode: "generic", suggestions: [] };

  const flushLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed);
    if (event.type === "meta" && event.payload) {
      meta = {
        mode: event.payload.mode || meta.mode,
        suggestions: Array.isArray(event.payload.suggestions) ? event.payload.suggestions : meta.suggestions,
      };
      onMeta?.(meta);
      return;
    }
    if (event.type === "delta" && typeof event.delta === "string") {
      onDelta?.(event.delta);
      return;
    }
    if (event.type === "done" && event.payload) {
      meta = {
        mode: event.payload.mode || meta.mode,
        suggestions: Array.isArray(event.payload.suggestions) ? event.payload.suggestions : meta.suggestions,
      };
      onMeta?.(meta);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    lines.forEach(flushLine);
  }

  if (buffer.trim()) {
    flushLine(buffer);
  }

  return meta;
};


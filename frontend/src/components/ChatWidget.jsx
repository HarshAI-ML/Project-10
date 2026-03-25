import { useEffect, useMemo, useState } from "react";
import { sendChatMessage } from "../api/chat";
import { useAuth } from "../context/AuthContext";

const buildWelcomeMessage = (isAuthenticated) => ({
  role: "assistant",
  content: isAuthenticated
    ? "Hi, I can answer using your portfolio context. Ask me anything."
    : "Hi, I am AUTO INVEST assistant. Ask me general market questions.",
});

const createSessionId = () => `s_${Math.random().toString(36).slice(2, 10)}`;

export default function ChatWidget() {
  const { isAuthenticated, user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState(() => [buildWelcomeMessage(isAuthenticated)]);

  const identityKey = useMemo(() => (isAuthenticated ? `user:${user?.username || "unknown"}` : "guest"), [
    isAuthenticated,
    user?.username,
  ]);

  const [sessionId, setSessionId] = useState(() => {
    const key = `chat_session_id:${identityKey}`;
    const existing = localStorage.getItem(key);
    if (existing) return existing;
    const next = createSessionId();
    localStorage.setItem(key, next);
    return next;
  });

  useEffect(() => {
    // Account changed (or guest/auth mode changed): start a fresh session + clear old in-memory chat.
    setMessages([buildWelcomeMessage(isAuthenticated)]);
    setInput("");
    const key = `chat_session_id:${identityKey}`;
    const existing = localStorage.getItem(key);
    if (existing) {
      setSessionId(existing);
      return;
    }
    const next = createSessionId();
    localStorage.setItem(key, next);
    setSessionId(next);
  }, [identityKey, isAuthenticated]);

  const onSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const nextMessages = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);
    try {
      const data = await sendChatMessage({
        message: text,
        history: nextMessages.slice(-10),
        session_id: sessionId,
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data?.reply || "No response generated." },
      ]);
    } catch (err) {
      const detail =
        err?.response?.data?.reply ||
        err?.response?.data?.detail ||
        (err?.message === "Network Error"
          ? "Chat service is unreachable. Please ensure backend is running on http://127.0.0.1:8000."
          : "Sorry, I could not answer right now. Please try again.");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: detail },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-5 right-5 z-50">
      {isOpen && (
        <div className="mb-3 flex h-[460px] w-[350px] max-w-[92vw] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-900 px-4 py-3 text-white">
            <div>
              <p className="text-sm font-bold">AUTO INVEST Chat</p>
              <p className="text-[11px] text-slate-300">{isAuthenticated ? "Personalized mode" : "Generic mode"}</p>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="rounded-md px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
            >
              Close
            </button>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-3">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
                    m.role === "user" ? "bg-indigo-600 text-white" : "bg-white text-slate-700 border border-slate-200"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-500">
                  Thinking...
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-slate-200 bg-white p-3">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSend();
                }}
                placeholder="Type a message..."
                className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
              />
              <button
                onClick={onSend}
                disabled={loading || !input.trim()}
                className="rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}

      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-xl transition hover:scale-105"
        aria-label="Open chatbot"
      >
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
        </svg>
      </button>
    </div>
  );
}

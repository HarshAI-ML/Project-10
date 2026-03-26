import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { sendChatMessage, sendChatMessageStream } from "../api/chat";
import { fetchPortfolio, fetchStocks } from "../api/stocks";
import { useAuth } from "../context/AuthContext";

const ACTIVE_PORTFOLIO_KEY = "active_portfolio_id";

const buildWelcomeMessage = (isAuthenticated, isPortfolioScoped) => ({
  role: "assistant",
  content:
    isAuthenticated && isPortfolioScoped
      ? "Hi, I can answer using your portfolio context. Ask me anything."
      : "Hi, I am AUTO INVEST assistant. Ask me general market questions.",
});

const createSessionId = () => `s_${Math.random().toString(36).slice(2, 10)}`;

const createMessageId = () => `m_${Math.random().toString(36).slice(2, 10)}`;

const getDefaultSuggestions = (isAuthenticated, isPortfolioScoped) =>
  isAuthenticated && isPortfolioScoped
    ? [
        "Which stock in my portfolio has the highest expected upside?",
        "Which holding has the best buy signal right now?",
        "Which stock has the lowest P/E ratio in my portfolio?",
        "What are the riskiest holdings in my current portfolio?",
        "Show me the strongest stock by sentiment in my portfolio.",
        "What is my portfolio missing for better balance?",
      ]
    : [
        "What is a simple way to start investing?",
        "How do I reduce risk in a stock portfolio?",
        "What is the difference between price and value?",
        "Which sectors usually look safer in uncertain markets?",
        "How do I read a buy, hold, or sell signal?",
        "What should I check before buying a stock?",
      ];

const normalizeAssistantContent = (text) => {
  const raw = String(text || "").replace(/\r\n/g, "\n");
  if (!raw.includes("|")) return raw;

  // Heuristic fix for model replies where markdown table rows arrive flattened into one line.
  let normalized = raw.replace(/:\s+\|/g, ":\n|");
  normalized = normalized.replace(/\|\s+\|/g, "|\n|");
  normalized = normalized.replace(/\s\|\s\|/g, "\n|");
  normalized = normalized.replace(/\|\s{2,}\|/g, "|\n|");
  return normalized;
};

const markdownToPlainText = (value) => {
  let text = normalizeAssistantContent(String(value || ""));
  text = text.replace(/\r\n/g, "\n");
  text = text.replace(/```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g, "$1");
  text = text.replace(/`([^`]+)`/g, "$1");
  text = text.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)");
  text = text.replace(/^#{1,6}\s+/gm, "");
  text = text.replace(/^>\s?/gm, "");
  text = text.replace(/^\s*[-*+]\s+/gm, "• ");
  text = text.replace(/^\s*\d+\.\s+/gm, (match) => match.replace(/^\s*/, ""));
  text = text.replace(/\*\*(.*?)\*\*/g, "$1");
  text = text.replace(/__(.*?)__/g, "$1");
  text = text.replace(/\*(.*?)\*/g, "$1");
  text = text.replace(/_(.*?)_/g, "$1");
  text = text.replace(/\n{3,}/g, "\n\n").trim();
  return text;
};

export default function ChatWidget() {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isPortfolioScopedRoute =
    location.pathname.startsWith("/portfolio") ||
    location.pathname.startsWith("/stocks") ||
    location.pathname.startsWith("/compare") ||
    location.pathname.startsWith("/clusters");
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState(() => getDefaultSuggestions(isAuthenticated, isPortfolioScopedRoute));
  const [messages, setMessages] = useState(() => [
    { id: createMessageId(), ...buildWelcomeMessage(isAuthenticated, isPortfolioScopedRoute) },
  ]);
  const [activePortfolio, setActivePortfolio] = useState({ id: null, name: "", stocks: [] });
  const rawActivePortfolioId = isPortfolioScopedRoute ? sessionStorage.getItem(ACTIVE_PORTFOLIO_KEY) || "" : "";
  const parsedActivePortfolioId = Number.parseInt(rawActivePortfolioId, 10);
  const scopedPortfolioId = Number.isFinite(parsedActivePortfolioId) ? parsedActivePortfolioId : null;

  const identityKey = useMemo(() => (isAuthenticated ? `user:${user?.username || "unknown"}` : "guest"), [
    isAuthenticated,
    user?.username,
  ]);
  const sessionScopeKey = scopedPortfolioId ? `portfolio:${scopedPortfolioId}` : "general";
  const sessionStorageKey = `chat_session_id:${identityKey}:${sessionScopeKey}`;

  const [sessionId, setSessionId] = useState(() => {
    const existing = localStorage.getItem(sessionStorageKey);
    if (existing) return existing;
    const next = createSessionId();
    localStorage.setItem(sessionStorageKey, next);
    return next;
  });

  const showSuggestions = messages.length <= 1 && !input.trim() && !loading;

  useEffect(() => {
    const loadPortfolioContext = async () => {
      if (!isAuthenticated || !scopedPortfolioId) {
        setActivePortfolio({ id: null, name: "", stocks: [] });
        return;
      }

      try {
        const [portfolioData, stockData] = await Promise.all([
          fetchPortfolio(),
          fetchStocks(scopedPortfolioId),
        ]);
        const portfolios = Array.isArray(portfolioData) ? portfolioData : [];
        const selectedPortfolio = portfolios.find((p) => String(p.id) === String(scopedPortfolioId)) || null;
        setActivePortfolio({
          id: selectedPortfolio?.id || scopedPortfolioId,
          name: selectedPortfolio?.name || "Active portfolio",
          stocks: Array.isArray(stockData) ? stockData : [],
        });
      } catch {
        setActivePortfolio({ id: scopedPortfolioId, name: "Active portfolio", stocks: [] });
      }
    };

    loadPortfolioContext();
  }, [isAuthenticated, scopedPortfolioId, location.pathname, location.search]);

  const findMentionedStock = (content) => {
    const text = String(content || "").toLowerCase();
    if (!text || !Array.isArray(activePortfolio.stocks) || activePortfolio.stocks.length === 0) return null;

    return activePortfolio.stocks.find((stock) => {
      const symbol = String(stock.symbol || stock.ticker || "").toLowerCase();
      const companyName = String(stock.company_name || stock.name || "").toLowerCase();
      if (companyName && text.includes(companyName)) return true;
      if (!symbol) return false;
      const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const symbolPattern = new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, "i");
      return symbolPattern.test(text);
    }) || null;
  };

  const headerTitle = isAuthenticated && scopedPortfolioId ? "Portfolio AI" : "AUTO INVEST Chat";
  const headerContext = isAuthenticated && scopedPortfolioId
    ? (activePortfolio?.name ? `${activePortfolio.name} active` : "No active portfolio selected")
    : "General market mode";
  const headerContextTone = isAuthenticated && scopedPortfolioId && activePortfolio?.name ? "text-emerald-600" : "text-slate-500";
  const visibleSuggestions = suggestions.slice(0, 4);
  const panelClass = isExpanded
    ? "mb-3 flex h-[min(78vh,760px)] w-[min(460px,calc(100vw-1.5rem))] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
    : "mb-3 flex h-[72vh] max-h-[72vh] w-[360px] max-w-[90vw] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl";

  useEffect(() => {
    // Account or portfolio scope changed: start a fresh session + clear old in-memory chat.
    setMessages([{ id: createMessageId(), ...buildWelcomeMessage(isAuthenticated, !!scopedPortfolioId) }]);
    setInput("");
    setSuggestions(getDefaultSuggestions(isAuthenticated, !!scopedPortfolioId));
    const existing = localStorage.getItem(sessionStorageKey);
    if (existing) {
      setSessionId(existing);
      return;
    }
    const next = createSessionId();
    localStorage.setItem(sessionStorageKey, next);
    setSessionId(next);
  }, [identityKey, isAuthenticated, scopedPortfolioId, sessionStorageKey]);

  const onSend = async (overrideText) => {
    const text = String(overrideText ?? input).trim();
    if (!text || loading) return;

    const userMessageId = createMessageId();
    const assistantMessageId = createMessageId();
    const nextMessages = [...messages, { id: userMessageId, role: "user", content: text }];
    const sendPayload = {
      message: text,
      history: nextMessages.slice(-10).map(({ role, content }) => ({ role, content })),
      session_id: sessionId,
      portfolio_id: isPortfolioScopedRoute && Number.isFinite(Number.parseInt(sessionStorage.getItem(ACTIVE_PORTFOLIO_KEY) || "", 10))
        ? Number.parseInt(sessionStorage.getItem(ACTIVE_PORTFOLIO_KEY) || "", 10)
        : null,
    };

    setMessages([
      ...nextMessages,
      { id: assistantMessageId, role: "assistant", content: "", streaming: true },
    ]);
    setInput("");
    setLoading(true);

    const updateAssistantContent = (updater) => {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== assistantMessageId) return msg;
          const nextContent = typeof updater === "function" ? updater(msg.content || "") : updater;
          return { ...msg, content: nextContent };
        })
      );
    };

    const finalizeAssistant = (content) => {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId ? { ...msg, content: content ?? msg.content ?? "", streaming: false } : msg
        )
      );
    };

    try {
      const data = await sendChatMessageStream(sendPayload, {
        onMeta: (meta) => {
          if (Array.isArray(meta?.suggestions) && meta.suggestions.length > 0) {
            setSuggestions(meta.suggestions.slice(0, 8));
          }
        },
        onDelta: (delta) => {
          updateAssistantContent((prevContent) => `${prevContent}${delta}`);
        },
      });
      if (Array.isArray(data?.suggestions) && data.suggestions.length > 0) {
        setSuggestions(data.suggestions.slice(0, 8));
      }
      finalizeAssistant();
    } catch (streamErr) {
      try {
        const data = await sendChatMessage(sendPayload);
        if (Array.isArray(data?.suggestions) && data.suggestions.length > 0) {
          setSuggestions(data.suggestions.slice(0, 8));
        }
        finalizeAssistant(data?.reply || "No response generated.");
      } catch (err) {
        const detail =
          err?.response?.data?.reply ||
          err?.response?.data?.detail ||
          err?.message ||
          (streamErr?.message === "Network Error" || err?.message === "Network Error"
            ? "Chat service is unreachable. Please ensure backend is running on http://127.0.0.1:8000."
            : "Sorry, I could not answer right now. Please try again.");
        finalizeAssistant(detail);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-5 right-5 z-50">
      {isOpen && (
        <div className={panelClass}>
          <div className="flex items-start justify-between border-b border-slate-200 bg-white px-4 py-3">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-100 text-sm font-extrabold text-violet-700 ring-1 ring-violet-200">
                AI
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-slate-900">{headerTitle}</p>
                <div className={`mt-0.5 flex items-center gap-1.5 text-[11px] ${headerContextTone}`}>
                  {isAuthenticated ? (
                    <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                  ) : null}
                  <span className="truncate">{headerContext}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setIsExpanded((prev) => !prev)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                aria-label={isExpanded ? "Minimize chat" : "Expand chat"}
                title={isExpanded ? "Minimize" : "Expand"}
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  {isExpanded ? (
                    <>
                      <path d="M8 3H3v5" />
                      <path d="M16 3h5v5" />
                      <path d="M21 16v5h-5" />
                      <path d="M3 16v5h5" />
                      <path d="M8 8L3 3" />
                    </>
                  ) : (
                    <>
                      <path d="M4 10V4h6" />
                      <path d="M20 14v6h-6" />
                      <path d="M14 4h6v6" />
                      <path d="M4 20v-6h6" />
                    </>
                  )}
                </svg>
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                aria-label="Close chat"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-slate-50 px-3 py-3">
            {messages.map((m, i) => {
              const normalizedContent = m.role === "assistant" ? markdownToPlainText(m.content) : m.content;
              const mentionedStock = m.role === "assistant" ? findMentionedStock(normalizedContent) : null;

              return (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`flex max-w-[85%] ${m.role === "user" ? "justify-end" : "items-start gap-2"}`}>
                    {m.role === "assistant" && (
                      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-100 text-[10px] font-bold text-violet-700 ring-1 ring-violet-200">
                        AI
                      </div>
                    )}
                    <div
                      className={`rounded-2xl px-3.5 py-2.5 text-sm shadow-sm ${
                        m.role === "user"
                          ? "bg-violet-600 text-white"
                          : "border border-slate-200 bg-white text-slate-800"
                      }`}
                    >
                      <div className={m.role === "assistant" ? "whitespace-pre-wrap break-words leading-relaxed" : ""}>
                        {normalizedContent}
                      </div>
                      {m.role === "assistant" && mentionedStock?.id && (
                        <button
                          type="button"
                          onClick={() => navigate(`/stocks/${mentionedStock.id}`)}
                          className="mt-2 inline-flex items-center text-xs font-semibold text-violet-600 hover:text-violet-700"
                        >
                          View stock →
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {loading && (
              <div className="flex justify-start">
                <div className="ml-9 rounded-2xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-500 shadow-sm">
                  Thinking...
                </div>
              </div>
            )}
          </div>

          {showSuggestions && suggestions.length > 0 && (
            <div className="bg-white px-3 pb-2 pt-1">
              <div className="flex flex-wrap gap-1.5">
                {visibleSuggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => onSend(suggestion)}
                    disabled={loading}
                    className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-left text-[11px] font-medium leading-snug text-slate-700 transition hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 disabled:opacity-50"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="border-t border-slate-200 bg-white p-3">
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSend();
                }}
                placeholder="Ask about your portfolio..."
                className="flex-1 rounded-full border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-violet-400 focus:bg-white focus:ring-2 focus:ring-violet-100"
              />
              <button
                onClick={onSend}
                disabled={loading || !input.trim()}
                className="flex h-11 w-11 items-center justify-center rounded-full bg-violet-600 text-white shadow-sm transition hover:bg-violet-700 disabled:opacity-50"
                aria-label="Send message"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 12h14" />
                  <path d="M13 6l6 6-6 6" />
                </svg>
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

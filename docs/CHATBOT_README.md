# Chatbot README

This document explains how the backend chatbot works in this project.

## Location

- Service logic: `backend/api/chatbot_service.py`
- API endpoint: `POST /api/chat/`
- API view: `backend/api/views.py` (`ChatbotAPIView`)
- Request serializer: `backend/api/serializers.py` (`ChatMessageSerializer`)

## What It Does

The chatbot supports two modes:

- `generic` mode for guest users
- `personalized` mode for authenticated users (uses portfolio and stock data)

It combines:

- Rule-based quantitative answers for ranking-style questions
- LLM responses (Groq / OpenRouter)
- Optional LangGraph routing orchestration

## Request Contract

`POST /api/chat/`

Request JSON:

```json
{
  "message": "Which stock has highest PE in my portfolio?",
  "history": [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello"}
  ],
  "session_id": "optional-session-id"
}
```

Response JSON:

```json
{
  "reply": "In your selected scope, TICKER (...) has the highest trailing P/E ...",
  "mode": "personalized"
}
```

## End-to-End Flow

1. `ChatbotAPIView` validates payload using `ChatMessageSerializer`.
2. `generate_chat_response(...)` receives user + message + history.
3. History is normalized (`_normalize_history`) and truncated for safety.
4. If user is authenticated, chatbot first tries `_answer_quant_query(...)` for direct numeric/ranking answers.
5. If not solved directly:
   - If LangGraph is available, it routes:
     - guest -> general prompt path
     - auth -> builds user context JSON then personalized prompt path
   - If LangGraph is unavailable, fallback prompt path is used.
6. Provider selection (`_call_chat_model`):
   - `CHAT_PROVIDER=groq` -> Groq
   - `CHAT_PROVIDER=openrouter` -> OpenRouter
   - `CHAT_PROVIDER=auto` -> Groq first, OpenRouter fallback
7. Reply is returned as `{ reply, mode }`.

## Personalized Context (Authenticated)

For logged-in users, `_build_user_context_payload(...)` gathers live account context from DB/services:

- portfolios (`Portfolio`)
- stocks in portfolios (`PortfolioStock`)
- forecasts (`get_latest_forecasts_bulk`)
- signals (`get_latest_signals_bulk`)
- sentiment (`get_stocks_sentiment_bulk`)
- fundamentals (`get_fundamentals_bulk`)
- latest prices (`get_latest_price`)

This is compacted into JSON and injected into the system prompt.

## Quantitative Query Shortcut

Before using LLM for authenticated users, `_answer_quant_query(...)` handles many metric questions directly, e.g.:

- highest/lowest current price
- highest/lowest trailing PE
- highest expected change %
- predicted price comparisons
- simple geography/sector/portfolio filters inferred from query text

This improves speed, consistency, and reduces hallucination risk.

## LLM Providers and Env Variables

### Common

- `CHAT_PROVIDER` = `auto` | `groq` | `openrouter`

### Groq

- `GROQ_API_KEY`
- Model used in code: `llama-3.1-8b-instant`

### OpenRouter

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (default in code: `openai/gpt-3.5-turbo`)
- `OPENROUTER_APP_NAME` (optional title/header)

## Sequence Diagram

```mermaid
sequenceDiagram
    participant U as User/Frontend
    participant API as /api/chat/
    participant S as chatbot_service.py
    participant DB as Portfolio+Analytics Data
    participant LLM as Groq/OpenRouter

    U->>API: POST message + history
    API->>S: generate_chat_response(user, message, history)
    S->>S: normalize_history()

    alt Authenticated user
        S->>S: _answer_quant_query()
        alt Quant answer found
            S-->>API: reply (personalized)
        else Need LLM
            S->>DB: build user context payload
            S->>LLM: chat completion (system prompt + context + history)
            LLM-->>S: reply
            S-->>API: reply (personalized)
        end
    else Guest user
        S->>LLM: chat completion (generic prompt + history)
        LLM-->>S: reply
        S-->>API: reply (generic)
    end

    API-->>U: { reply, mode }
```

## Notes

- Current chatbot is primarily **service/context-grounded**.
- Vector DB retrieval is not yet wired in this chatbot flow file.
- If provider keys are missing, chatbot returns configuration/helpful fallback messages.

## Quick Test

```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token <YOUR_TOKEN>" \
  -d '{"message":"Which stock has highest PE in my portfolio?","history":[]}'
```

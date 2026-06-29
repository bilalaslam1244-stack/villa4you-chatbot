# Villa4You WhatsApp Chatbot

Level 3 lead-qualification chatbot for Villa4You's luxury group villa rentals.

## Current capability
- ✅ Conversation engine: 6 villas, 3 Malaysian locations, 20–50+ pax logic
- ✅ Lead scoring: tracks name, guests, dates, location, villa interest
- ✅ FAQ coverage: pricing, pools, ballrooms, prayer rooms, cancellation, pets, smoking
- ✅ WhatsApp hand-off: fires at 75+ lead score
- ✅ Webhook endpoint: POST /webhook/whatsapp (Meta Cloud API-ready)
- ✅ Local simulator: `python bot/main.py chat`
- ✅ OpenRouter / OpenAI-compatible LLM hook (graceful fallback if no key)

## Quick start

```bash
cd ~/projects/villa4you-chatbot

# install
pip install -r requirements.txt

# run server
python bot/main.py

# local test
python bot/main.py chat
```

Server starts on http://localhost:8000

## Env vars (optional)
- `LLM_API_URL` — default OpenRouter
- `LLM_API_KEY` — any OpenAI-compatible key
- `LLM_MODEL` — default `openai/gpt-4o-mini`
- `WA_PHONE_NUMBER_ID` + `ACCESS_TOKEN` — turns on real WhatsApp sending

## Next steps
1. Add OpenRouter key → free-text Q&A + villa recommendations
2. Meta setup → production WhatsApp number + webhook
3. Embed live chat widget on villa4you.my

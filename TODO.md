# TODO

## LLM Provider — replace OpenRouter free tier

**Problem**: OpenRouter free tier caps at 50 requests/day. That's 50 listings before the whole AI pipeline breaks for all users. Eval confirmed this is the binding constraint — the AI quality is fine.

**Options** (all work via `LLM_BASE_URL` + `LLM_API_KEY` env vars, no code changes needed):
- Anthropic API directly — reliable, pay-per-token
- Groq — fast, generous free tier for Llama models
- Ollama — self-hosted on Railway, zero per-request cost
- OpenRouter paid — add credits, get 1000 req/day per $10

**What to set in Railway env**:
```
LLM_BASE_URL=<provider base url>
LLM_API_KEY=<key>
LLM_MODEL=<model id>        # optional, auto-discovers free models if blank
VISION_MODEL=<model id>     # needs multimodal support
OPENROUTER_API_KEY=         # clear this to stop using OpenRouter
```

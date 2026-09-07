# TODO

## LLM Provider — replace OpenRouter free tier

**Problem**: OpenRouter free tier caps at 50 requests/day. That's 50 listings before the whole AI pipeline breaks for all users. Eval confirmed this is the binding constraint — the AI quality is fine.

**Wired**: `ai/config.py` prefers `LLM_*`. If `LLM_MODEL` is a paid id (no `:free`) or `LLM_BASE_URL` is not OpenRouter, free-model discovery and `:free` fallbacks are skipped so the agent does not get stuck on the 50/day sink.

**Options** (all work via `LLM_BASE_URL` + `LLM_API_KEY`):
- Anthropic API directly — reliable, pay-per-token
- Groq — fast, generous free tier for Llama models
- Ollama — self-hosted on Railway, zero per-request cost
- OpenRouter paid — add credits; set `LLM_MODEL` to a non-`:free` id

**What to set in Railway env**:
```
LLM_BASE_URL=<provider base url>
LLM_API_KEY=<key>
LLM_MODEL=<model id>        # required for paid; do not leave blank on a paid provider
VISION_MODEL=<model id>     # needs multimodal support
OPENROUTER_API_KEY=         # clear this to stop using OpenRouter
```

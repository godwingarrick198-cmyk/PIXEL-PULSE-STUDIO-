# Presenton setup for Pixel Pulse Studio

Pixel Pulse now has an optional Presenton adapter. It is **disabled by default** so the existing local PPTX/PDF renderer keeps working during testing.

Presenton is open-source (Apache-2.0), self-hostable, supports editable PPTX/PDF output, and exposes a presentation-generation API. See the official project: https://github.com/presenton/presenton

## Important $0 rule

Do not paste a paid API key into this project. For a zero-spend setup, Presenton itself must run on free/self-hosted infrastructure and its model provider must also be free/local (for example Ollama) or a currently available free-tier provider.

A Render free web service is an **experimental** option, not a guarantee: Presenton + an AI model can be too heavy for a small free instance and Render free instances sleep. If it cannot stay healthy, run Presenton on a machine you control and expose it through a secure tunnel, or keep the Pixel Pulse fallback renderer enabled.

## 1. Create the Presenton service

Use the official Presenton Docker image:

`ghcr.io/presenton/presenton:latest`

Presenton's documented container port is 80. The simplest local test is:

`docker run -it --name presenton -p 5001:80 -v "./app_data:/app_data" ghcr.io/presenton/presenton:latest`

Then open `http://localhost:5001`.

## 2. Configure a model provider

For strict $0 operation, prefer a local model through Ollama. Presenton documents Ollama support with `LLM=ollama`, `OLLAMA_URL`, and `OLLAMA_MODEL`.

If you use a free-tier cloud model instead, verify its current quota/terms first. Pixel Pulse does not require that option and should not silently incur charges.

## 3. Create a Presenton API key

In Presenton, open **Admin → API keys** and create an access key. Presenton's API expects the key as:

`Authorization: Bearer sk-presenton-...`

Do not commit this key to GitHub.

## 4. Add these Render environment variables to Pixel Pulse

`PRESENTON_ENABLED=true`

`PRESENTON_URL=https://YOUR-PRESENTON-SERVICE-URL`

`PRESENTON_API_KEY=sk-presenton-...`

Optional:

`PRESENTON_TIMEOUT_SECONDS=180`

Keep the existing Pixel Pulse variables unchanged.

## 5. Test

1. Deploy Pixel Pulse from the latest `main` commit.
2. Confirm `/api/health` returns `{"status":"ok"}`.
3. Keep `FULL_AUTO=false` and `SCHEDULER_ENABLED=false` while testing.
4. Create/use a paid test order in Telegram.
5. Complete onboarding.
6. Run `/generate PPS-ORD-...`.
7. Download both PPTX and PDF.

When Presenton is enabled and reachable, Pixel Pulse downloads the Presenton-generated files into the normal order storage. If Presenton is down or fails, Pixel Pulse automatically keeps the existing local renderer's output instead of failing the order.

## What was committed

- `app/services/presenton.py` — Presenton API client + file download.
- `app/services/presentation_orchestrator.py` — optional Presenton routing with a safe local fallback.
- `app/core/config.py` — Presenton environment settings.
- `app/api/routes.py` — `/generate` now uses the orchestrator.

No API key or paid credential was committed.

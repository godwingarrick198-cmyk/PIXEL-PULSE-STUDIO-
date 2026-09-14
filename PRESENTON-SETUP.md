# Presenton setup for Pixel Pulse Studio

Pixel Pulse Studio is now wired to use **Presenton as the presentation renderer** when Presenton is enabled. The existing local renderer remains in the repository as a safety fallback until the Presenton test is proven successful.

Presenton is open-source, self-hostable, exposes a presentation-generation API, and can export editable PPTX and PDF files. Official API endpoint: `/api/v1/ppt/presentation/generate`.

## Important $0 rule

Do not paste a paid API key into Pixel Pulse.

For the first test, use:

- Presenton self-hosted on Render Free
- Google's Gemini API through the existing free quota/key, if available
- No OpenAI/Anthropic/paid Presenton subscription

Render Free currently gives a web service 512 MB RAM and 0.1 CPU. Render explicitly describes Free services as testing/hobby infrastructure, and they sleep after inactivity. Presenton may be too heavy for that limit, so this deployment is an experiment. If it OOMs or cannot stay healthy, we will move Presenton to a larger/free alternative rather than breaking Pixel Pulse. citeturn1search1turn1search2

## 1. Create the Presenton Render service

The repository contains `presenton-render.yaml` with the test configuration.

In Render:

1. Open **New → Blueprint**.
2. Select the Pixel Pulse GitHub repository.
3. Choose the `presenton-render.yaml` blueprint.
4. Keep the Presenton service on **Free** for this test.
5. Render will ask for two secret values:
   - `GOOGLE_API_KEY` — paste your existing Gemini/Google AI API key.
   - `AUTH_PASSWORD` — create a strong password of at least 8 characters.
6. Deploy.

Presenton officially supports the `google` provider and `GOOGLE_API_KEY`. Its Docker image listens on port 80. citeturn2search0

## 2. Wait for Presenton to become Live

Render should give the service an address similar to:

`https://pixel-pulse-presenton.onrender.com`

Open that address in a browser. If the service is healthy, the Presenton interface should load.

If Render reports an out-of-memory, crash-loop, or failed health check, **stop there** and send me the Render error. Do not change Pixel Pulse yet.

## 3. Create the Presenton API key

Log in to the new Presenton instance with the admin account created during deployment.

Open the Presenton account/admin area and create an API key. The key has the form:

`sk-presenton-...`

Presenton's API requires this key in the `Authorization: Bearer ...` header. citeturn1search5turn1search8

**Never put this key in GitHub.** It goes only into Render environment variables.

## 4. Connect Pixel Pulse to Presenton

Open the existing **Pixel Pulse Studio** Render service → Environment.

Add/update these variables:

`PRESENTON_ENABLED=true`

`PRESENTON_URL=https://YOUR-PRESENTON-SERVICE.onrender.com`

`PRESENTON_API_KEY=sk-presenton-...`

`PRESENTON_TIMEOUT_SECONDS=180`

Keep every existing Pixel Pulse environment variable unchanged.

## 5. Test the real Pixel Pulse generation flow

After Pixel Pulse redeploys:

1. Confirm `/api/health` returns `{"status":"ok"}`.
2. Use the existing paid test order.
3. Run `/generate PPS-ORD-...` in Telegram.
4. Download the resulting PPTX and PDF.
5. Check the slides visually.

Pixel Pulse will send the approved onboarding/source content to Presenton, then download Presenton's PPTX/PDF into the normal Pixel Pulse order storage.

## What is already in the repository

- `app/services/presenton.py` — Presenton API client.
- `app/services/presentation_orchestrator.py` — routes generation through Presenton when configured.
- `app/core/config.py` — Presenton environment settings.
- `app/api/routes.py` — generation endpoint uses the orchestrator.
- `presenton-render.yaml` — Render Free experimental deployment definition.
- `slide_engine.js` — retained as a fallback until Presenton is proven stable.

The Presenton adapter was also corrected so it handles both absolute download URLs and relative paths returned by different Presenton deployments.

No API key or paid credential is committed.

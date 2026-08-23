# Pixel Pulse Studio

Autonomous freelance presentation & pitch-deck business backend for Garrick Godwin. It discovers and qualifies prospects, performs controlled email outreach, handles sales conversations, creates verified Flutterwave payment requests, onboards customers, generates editable PPTX + PDF deliverables, runs QC, and reports status to Telegram.

## Safety defaults

- `TEST_MODE=true` by default: no real outreach and no real charges.
- `FULL_AUTO=false` by default.
- Product Hunt is disabled unless its API access and commercial-use approval are explicitly configured.
- Global and campaign outreach limits are enforced.
- Suppression is checked before every outreach.
- Paid orders are never cancelled by emergency stop.

## Setup

1. Clone the repository.
2. Create a Python 3.12+ virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env`.
5. Add Gemini and Telegram credentials.
6. Configure SMTP for outbound email. Optional IMAP settings enable inbound reply polling.
7. Configure Flutterwave secret key/hash for real payments.
8. Keep Product Hunt disabled unless your intended commercial use is approved.
9. Start locally:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

10. Test `GET /api/health`.
11. In Telegram, use `/start`, `/hunt 100`, `/status`.
12. Run presentation generation in `TEST_MODE=true` before production.
13. Verify the Flutterwave webhook using a sandbox/test event before production.

## Telegram commands

`/start`, `/hunt 100`, `/hunt 500 7d`, `/pause`, `/resume [campaign_id]`, `/stop`, `/emergency_stop`, `/status`, `/campaigns`.

Natural-language controls also understand common commands such as `Find 500 startups over 7 days`, `Pause everything`, `Resume the campaign`, and `Stop hunting`.

## API

- `GET /api/health`
- `GET /api/status`
- `GET /api/campaigns`
- `POST /api/campaigns`
- `POST /api/campaigns/{id}/pause`
- `POST /api/campaigns/{id}/resume`
- `POST /api/campaigns/{id}/stop`
- `POST /api/campaigns/{id}/cancel`
- `GET /api/prospects`
- `GET /api/prospects/{id}`
- `POST /api/prospects/search`
- `GET /api/orders`
- `GET /api/orders/{id}`
- `POST /api/orders`
- `PUT /api/orders/{id}/onboarding`
- `POST /api/orders/{id}/files`
- `POST /api/webhooks/flutterwave`
- `GET /api/deliveries/{order_id}`

## Presentation generation

`python-pptx` creates editable slides. ReportLab creates a PDF counterpart. Supported layout vocabulary includes TITLE, AGENDA, PROBLEM, SOLUTION, PRODUCT, FEATURES, BENEFITS, MARKET, BUSINESS MODEL, TRACTION, COMPETITION, TEAM, TIMELINE, CASE STUDY, TESTIMONIAL, PRICING, CALL TO ACTION, and CONTACT.

The generator never intentionally invents customer facts. Missing facts are left as placeholders or omitted. QC checks slide count, empty slides, and overloaded text; the configured quality threshold and repair-attempt limit are enforced.

## Render

The repository includes `render.yaml`. Set the required environment variables in Render's Environment page. Do not commit `.env` or secrets. The required start command is:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Use `/api/health` as the Render health check.

## Production checklist

Before `FULL_AUTO=true` and `TEST_MODE=false`, verify Telegram, Gemini, discovery, deduplication, suppression, outreach limits, Flutterwave webhook signature + server-side transaction verification, onboarding, PPTX/PDF generation, QC, delivery, and emergency stop.

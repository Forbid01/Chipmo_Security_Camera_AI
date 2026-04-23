# PostHog observability (T2-09 / T2-10)

## Files

| File | Purpose |
|---|---|
| `onboarding-funnel.json` | Dashboard definition — signup → first_detection funnel + trend tiles. Import with `posthog-cli insights apply`. |
| `onboarding-dropoff-alert.yml` | Alert subscriptions — fires Slack on any step-to-step conversion <60% over 24h, plus a `p50(time_to_first_detection) > 15min` guard. |

## Apply to production

```bash
export POSTHOG_PERSONAL_API_KEY=...
posthog-cli insights apply observability/posthog/onboarding-funnel.json
posthog-cli alerts   apply observability/posthog/onboarding-dropoff-alert.yml
```

## Event taxonomy

Canonical event names live in two places and must stay in sync:

- Browser: `security-web/src/services/analytics.js` → `ANALYTICS_EVENTS`
- Backend: `shoplift_detector/app/services/analytics.py` → `ANALYTICS_EVENTS`

Any rename must also bump the dashboard JSON — events no longer fire
silently because the dashboard `events[]` list references them by id.

## Local dev

Set `VITE_POSTHOG_KEY` in `security-web/.env.local` to test browser
capture against a dev project. Leaving it unset keeps the tracker
in no-op mode — dev-mode `console.debug` logs show what would have
fired.

For server-side capture, set `POSTHOG_API_KEY` in the backend's
`.env`. Unset → the null recorder collects events in-memory (tests
assert against it).

// PostHog event tracker for the onboarding funnel (T2-09).
//
// Thin wrapper around window.posthog. Loads the SDK lazily once so
// the signup flow doesn't block on the analytics script, and
// degrades to no-ops when POSTHOG_KEY is not configured.

const POSTHOG_KEY = import.meta.env?.VITE_POSTHOG_KEY || null;
const POSTHOG_HOST = import.meta.env?.VITE_POSTHOG_HOST || 'https://app.posthog.com';

// Canonical event names matching the T2-09 DoD — any rename should
// also update the funnel dashboard (T2-10) so dashboards don't go
// silent.
export const ANALYTICS_EVENTS = Object.freeze({
  SIGNUP_STARTED: 'signup_started',
  SIGNUP_COMPLETED: 'signup_completed',
  EMAIL_VERIFIED: 'email_verified',
  PLAN_SELECTED: 'plan_selected',
  TRIAL_ACTIVATED: 'trial_activated',
  PAYMENT_STARTED: 'payment_started',
  PAYMENT_COMPLETED: 'payment_completed',
  INSTALLER_DOWNLOADED: 'installer_downloaded',
  AGENT_CONNECTED: 'agent_connected',
  CAMERA_DISCOVERED: 'camera_discovered',
  CAMERA_CONNECTED: 'camera_connected',
  FIRST_DETECTION: 'first_detection',
  ONBOARDING_COMPLETED: 'onboarding_completed',
});

let loadPromise = null;

function loadSnippet() {
  if (loadPromise) return loadPromise;
  if (!POSTHOG_KEY) {
    loadPromise = Promise.resolve(null);
    return loadPromise;
  }
  loadPromise = new Promise((resolve) => {
    // Stripped posthog-js snippet. The bundle replaces window.posthog
    // with the real SDK on load.
    (function (p, o) {
      p.posthog = p.posthog || [];
      const q = p.posthog;
      if (q.__loaded) {
        resolve(q);
        return;
      }
      q._i = [];
      q.init = (apiKey, config) => {
        q._i.push([apiKey, config]);
      };
      q.capture = (name, props) => {
        q.push(['capture', name, props]);
      };
      q.identify = (id, props) => {
        q.push(['identify', id, props]);
      };
      const script = o.createElement('script');
      script.async = true;
      script.src = `${POSTHOG_HOST}/static/array.js`;
      script.onload = () => resolve(p.posthog);
      script.onerror = () => resolve(null);
      o.head.appendChild(script);
      q.init(POSTHOG_KEY, { api_host: POSTHOG_HOST });
    })(window, document);
  });
  return loadPromise;
}

export async function trackEvent(name, properties = {}) {
  // Never block the UI on analytics — fire-and-forget with a
  // try/catch so a SDK bug can't break onboarding.
  try {
    const posthog = await loadSnippet();
    if (posthog && typeof posthog.capture === 'function') {
      posthog.capture(name, properties);
    } else if (import.meta.env?.DEV) {
      // Dev-mode breadcrumb so engineers see what would have fired.
      console.debug('[analytics]', name, properties);
    }
  } catch (err) {
    // Swallow — analytics must never throw into the product code.
    if (import.meta.env?.DEV) {
      console.warn('[analytics]', err);
    }
  }
}

export async function identifyUser(distinctId, properties = {}) {
  try {
    const posthog = await loadSnippet();
    if (posthog && typeof posthog.identify === 'function') {
      posthog.identify(distinctId, properties);
    }
  } catch (err) {
    if (import.meta.env?.DEV) {
      console.warn('[analytics]', err);
    }
  }
}

export const __test__ = { loadSnippet };

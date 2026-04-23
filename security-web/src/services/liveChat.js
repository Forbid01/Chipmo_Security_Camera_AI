// Live-chat widget wrapper (T2-11).
//
// Crisp is the default provider — swappable via `VITE_LIVE_CHAT`.
// When the env var is missing we no-op so dev/test builds don't
// block on a third-party script.

const WEBSITE_ID = import.meta.env?.VITE_CRISP_WEBSITE_ID || null;

let loadPromise = null;

function loadCrisp() {
  if (loadPromise) return loadPromise;
  if (!WEBSITE_ID) {
    loadPromise = Promise.resolve(null);
    return loadPromise;
  }
  loadPromise = new Promise((resolve) => {
    // Crisp's one-liner snippet — queues commands until their
    // script loads, then replaces window.$crisp with the live API.
    window.$crisp = window.$crisp || [];
    window.CRISP_WEBSITE_ID = WEBSITE_ID;
    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://client.crisp.chat/l.js';
    script.onload = () => resolve(window.$crisp);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
  });
  return loadPromise;
}

// Flag so we don't open the chat modal twice for the same idle event.
let promptedOnce = false;

export async function openChat(context = {}) {
  try {
    const $crisp = await loadCrisp();
    if (!$crisp) return;
    // Tag the conversation so support knows which onboarding step
    // the user was stuck on. Keys are Crisp-specific segment names.
    if (context.step) {
      $crisp.push(['set', 'session:segments', [[`onboarding:${context.step}`]]]);
    }
    $crisp.push(['do', 'chat:open']);
    $crisp.push(['do', 'message:send', [
      'text',
      'Туслалцаа хэрэгтэй юу? Бид энд байна 🙂',
    ]]);
  } catch {
    // Never break the product on a chat widget failure.
  }
}

export function showStuckPromptOnce(context = {}) {
  if (promptedOnce) return;
  promptedOnce = true;
  openChat(context);
}

export function __resetForTests() {
  promptedOnce = false;
  loadPromise = null;
}

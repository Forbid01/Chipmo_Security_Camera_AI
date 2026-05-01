import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, API_BASE_URL } from "../services/api";

// Shallow-diff two alert arrays by id + event_time + feedback_status + web_url.
// If identical, skip setState so React doesn't re-render any subscriber.
const listsEqual = (a, b) => {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.id !== y.id ||
      x.event_time !== y.event_time ||
      x.feedback_status !== y.feedback_status ||
      x.web_url !== y.web_url
    ) {
      return false;
    }
  }
  return true;
};

/**
 * Real-time alert hook.
 *
 * Primary path:  SSE stream at /api/v1/alerts/stream
 *   → On "alert" event, re-fetches the alert list via REST.
 *   → On disconnect / error, falls back to polling at `pollFallbackMs`.
 *
 * Fallback path: REST polling every `pollFallbackMs` ms (default 30 s).
 *   Activated when the browser/network doesn't support SSE or the
 *   server signals an error.
 *
 * Both paths are visibility-aware: paused when the tab is hidden.
 */
export const useAlerts = (pollFallbackMs = 30000) => {
  const [alerts, setAlerts] = useState([]);
  const alertsRef = useRef(alerts);
  const abortRef = useRef(null);
  const pollTimerRef = useRef(null);
  const sseRef = useRef(null);
  const sseReadyRef = useRef(false); // true once SSE fires "connected"

  useEffect(() => {
    alertsRef.current = alerts;
  }, [alerts]);

  // ── REST fetch ──────────────────────────────────────────────────────────
  const fetchAlerts = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const response = await api.get("/alerts", { signal: ctrl.signal });
      const data = response.data?.data || response.data || [];
      if (!Array.isArray(data)) return;
      if (!listsEqual(alertsRef.current, data)) {
        setAlerts(data);
      }
    } catch (err) {
      if (ctrl.signal.aborted) return;
      if (err.response?.status === 401) return;
      // Transient error — silent, SSE/polling will retry shortly.
    }
  }, []);

  // ── SSE + polling fallback ───────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    // ─ Initial load ─
    fetchAlerts();

    // ─ SSE connection ─
    // EventSource cannot set custom headers, so we pass the JWT as a query
    // param. The backend accepts it via ?token= and falls back to cookies.
    const token = localStorage.getItem("token");
    const sseUrl =
      `${API_BASE_URL}/api/v1/alerts/stream` +
      (token ? `?token=${encodeURIComponent(token)}` : "");

    let es;
    try {
      es = new EventSource(sseUrl, { withCredentials: true });
    } catch {
      // Browser doesn't support EventSource — start polling immediately.
      startPolling();
      return cleanup;
    }
    sseRef.current = es;

    es.addEventListener("connected", () => {
      if (cancelled) return;
      sseReadyRef.current = true;
      // SSE is live — kill any active polling fallback.
      stopPolling();
    });

    es.addEventListener("alert", () => {
      if (cancelled) return;
      if (document.visibilityState === "visible") fetchAlerts();
    });

    es.onerror = () => {
      if (cancelled) return;
      // EventSource auto-reconnects, but while reconnecting we still want
      // fresh data → activate polling until SSE recovers.
      if (!pollTimerRef.current) startPolling();
    };

    function startPolling() {
      if (pollTimerRef.current || cancelled) return;
      pollTimerRef.current = setInterval(() => {
        if (!cancelled && document.visibilityState === "visible") fetchAlerts();
      }, pollFallbackMs);
    }

    function stopPolling() {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    }

    // Re-fetch when tab regains focus (covers both SSE and polling paths).
    const onVisibility = () => {
      if (document.visibilityState === "visible" && !cancelled) fetchAlerts();
    };
    document.addEventListener("visibilitychange", onVisibility);

    function cleanup() {
      cancelled = true;
      sseReadyRef.current = false;
      es?.close();
      stopPolling();
      if (abortRef.current) abortRef.current.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    }

    return cleanup;
  }, [fetchAlerts, pollFallbackMs]);

  // ── Chart data (memoised) ────────────────────────────────────────────────
  const chartData = useMemo(() => {
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const counts = new Array(7).fill(0);
    for (const alert of alerts) {
      const raw = alert.event_time || alert.timestamp;
      if (!raw) continue;
      const s = typeof raw === "string" ? raw.replace(/\s+/g, "T") : raw;
      const d = new Date(s);
      if (!isNaN(d.getTime())) counts[d.getDay()]++;
    }
    return days.map((day, i) => ({ name: day, count: counts[i] }));
  }, [alerts]);

  return { alerts, chartData, fetchAlerts };
};

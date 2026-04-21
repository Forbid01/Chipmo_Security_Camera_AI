import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";

// Shallow-diff two alert arrays by id + event_time + feedback_status.
// If identical, we skip setState so React doesn't re-render any subscriber.
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

export const useAlerts = (refreshInterval = 5000) => {
  const [alerts, setAlerts] = useState([]);
  const alertsRef = useRef(alerts);
  const timerRef = useRef(null);
  const abortRef = useRef(null);
  const backoffRef = useRef(refreshInterval);

  useEffect(() => {
    alertsRef.current = alerts;
  }, [alerts]);

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
      backoffRef.current = refreshInterval;
    } catch (err) {
      if (ctrl.signal.aborted) return;
      if (err.response?.status === 401) return;
      // Exponential backoff on transient errors; caps at 60s.
      backoffRef.current = Math.min(backoffRef.current * 2, 60000);
    }
  }, [refreshInterval]);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      if (document.visibilityState !== "visible") {
        timerRef.current = setTimeout(tick, backoffRef.current);
        return;
      }
      await fetchAlerts();
      if (cancelled) return;
      timerRef.current = setTimeout(tick, backoffRef.current);
    };

    tick();

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        backoffRef.current = refreshInterval;
        if (timerRef.current) clearTimeout(timerRef.current);
        tick();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timerRef.current) clearTimeout(timerRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [fetchAlerts, refreshInterval]);

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

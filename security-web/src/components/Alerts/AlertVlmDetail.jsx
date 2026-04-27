import { useEffect, useState } from "react";
import { getAlertVlmAnnotation } from "../../services/api";

// Polls the backend for the VLM annotation of an alert.
//
// The annotation is written asynchronously by the detection pipeline, so
// freshly-created alerts may not have one yet. We poll a few times with
// a small backoff and stop — there's no point spinning forever if the
// VLM is disabled or failed.
const MAX_POLL_ATTEMPTS = 8;
const POLL_INTERVAL_MS = 2500;

function ConfidenceBar({ value }) {
  const pct = Math.round(Math.max(0, Math.min(1, value || 0)) * 100);
  const color =
    pct >= 75 ? "bg-red-500" : pct >= 50 ? "bg-orange-500" : "bg-emerald-500";
  return (
    <div className="w-full bg-gray-200 rounded-full h-2">
      <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function AlertVlmDetail({ alertId }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | unavailable

  useEffect(() => {
    if (!alertId) return;
    let cancelled = false;
    let attempt = 0;
    let timer = null;

    const poll = async () => {
      attempt += 1;
      try {
        const result = await getAlertVlmAnnotation(alertId);
        if (cancelled) return;
        if (result) {
          setData(result);
          setStatus("ready");
          return;
        }
        if (attempt >= MAX_POLL_ATTEMPTS) {
          setStatus("unavailable");
          return;
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch {
        if (cancelled) return;
        setStatus("unavailable");
      }
    };

    setStatus("loading");
    setData(null);
    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [alertId]);

  if (status === "loading") {
    return (
      <div className="text-sm text-gray-500 italic">
        VLM шалгалт хийгдэж байна…
      </div>
    );
  }

  if (status === "unavailable" || !data) {
    return (
      <div className="text-sm text-gray-400 italic">
        VLM annotation алга (идэвхгүй эсвэл хараахан бэлэн биш)
      </div>
    );
  }

  const evidence = data.reasoning?.evidence || [];

  return (
    <div className="border border-indigo-200 bg-indigo-50/50 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-indigo-700">
          VLM Verification
        </span>
        <span className="text-[11px] text-gray-500">{data.model_name}</span>
      </div>

      {data.caption && (
        <p className="text-sm text-gray-800 leading-snug">{data.caption}</p>
      )}

      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-gray-600">
          <span>Итгэл (confidence)</span>
          <span className="font-mono">
            {(Math.round((data.confidence || 0) * 100))}%
          </span>
        </div>
        <ConfidenceBar value={data.confidence} />
      </div>

      {evidence.length > 0 && (
        <ul className="text-xs text-gray-700 list-disc pl-4 space-y-0.5">
          {evidence.slice(0, 4).map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}

      {data.latency_ms != null && (
        <div className="text-[11px] text-gray-400">
          {data.latency_ms} ms
        </div>
      )}
    </div>
  );
}

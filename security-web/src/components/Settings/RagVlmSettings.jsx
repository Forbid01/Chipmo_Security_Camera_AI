/**
 * RAG + VLM tuning panel for store settings.
 *
 * Pairs two on/off toggles with two thresholds (`rag_fp_threshold`,
 * `vlm_confidence_threshold`). Pre-validates against the backend's
 * StoreSettings constraints (both thresholds in [0, 1]) so a misplaced
 * slider can't fail the PATCH after a round trip.
 *
 * Shape matches `StoreSettingsPatch` server-side:
 *   {
 *     rag_check_enabled, rag_fp_threshold,
 *     vlm_verification_enabled, vlm_confidence_threshold
 *   }
 */

import { useEffect, useState } from "react";

const DEFAULTS = {
  rag_check_enabled: true,
  rag_fp_threshold: 0.8,
  vlm_verification_enabled: true,
  vlm_confidence_threshold: 0.5,
};

function Toggle({ label, checked, onChange, disabled }) {
  return (
    <label className="flex cursor-pointer items-center gap-3">
      <input
        type="checkbox"
        checked={!!checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="h-4 w-4 accent-emerald-400"
      />
      <span className="text-sm font-medium text-slate-200">{label}</span>
    </label>
  );
}

function ThresholdSlider({ label, value, onChange, disabled, hint }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-200">{label}</span>
        <span className="font-mono text-slate-100">{pct}%</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={pct}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        disabled={disabled}
        className="mt-2 w-full accent-emerald-400"
      />
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export default function RagVlmSettings({ initialValue, onSave, saving }) {
  const [value, setValue] = useState(() => ({ ...DEFAULTS, ...(initialValue || {}) }));
  const [error, setError] = useState(null);

  useEffect(() => {
    if (initialValue) setValue((prev) => ({ ...prev, ...initialValue }));
  }, [initialValue]);

  const update = (patch) => {
    setValue((prev) => ({ ...prev, ...patch }));
    setError(null);
  };

  const handleSave = async () => {
    try {
      await onSave({
        rag_check_enabled: value.rag_check_enabled,
        rag_fp_threshold: value.rag_fp_threshold,
        vlm_verification_enabled: value.vlm_verification_enabled,
        vlm_confidence_threshold: value.vlm_confidence_threshold,
      });
    } catch (err) {
      console.warn("rag_vlm_settings_save_error", err);
      setError(err?.response?.data?.detail || "Хадгалахад алдаа гарлаа.");
    }
  };

  return (
    <div className="space-y-6 rounded-lg border border-slate-800 bg-slate-900/50 p-5">
      <div>
        <h3 className="text-base font-semibold text-slate-100">
          RAG + VLM Шалгуур
        </h3>
        <p className="mt-1 text-sm text-slate-400">
          Хуурамч анхааруулгыг RAG (текст хайлт) болон Qwen2.5-VL (зураг
          ойлгох) ашиглан шүүж байна.
        </p>
      </div>

      <div className="space-y-3 border-b border-slate-800 pb-5">
        <Toggle
          label="RAG шалгалт идэвхтэй"
          checked={value.rag_check_enabled}
          onChange={(v) => update({ rag_check_enabled: v })}
          disabled={saving}
        />
        <ThresholdSlider
          label="FP таних босго"
          value={value.rag_fp_threshold}
          onChange={(v) => update({ rag_fp_threshold: v })}
          disabled={saving || !value.rag_check_enabled}
          hint="Энэ хэмжээгээс өндөр төстэй мэдэгдсэн FP-тэй тохиолдсон alert-ийг далдална."
        />
      </div>

      <div className="space-y-3">
        <Toggle
          label="VLM шалгалт идэвхтэй (Qwen2.5-VL)"
          checked={value.vlm_verification_enabled}
          onChange={(v) => update({ vlm_verification_enabled: v })}
          disabled={saving}
        />
        <ThresholdSlider
          label="VLM итгэлийн босго"
          value={value.vlm_confidence_threshold}
          onChange={(v) => update({ vlm_confidence_threshold: v })}
          disabled={saving || !value.vlm_verification_enabled}
          hint="VLM-ийн итгэл энэ босгоос доогуур бол alert-ийг далдална."
        />
      </div>

      {error && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      )}

      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="w-full rounded-md bg-emerald-500 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-400 disabled:opacity-60"
      >
        {saving ? "Хадгалж байна…" : "Хадгалах"}
      </button>
    </div>
  );
}

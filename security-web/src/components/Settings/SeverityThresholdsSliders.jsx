/**
 * T5-10 — store alert severity threshold sliders.
 *
 * Three sliders (yellow / orange / red) over a 0-100 score scale.
 * Invariant: yellow < orange < red. The component enforces it
 * locally so the user can't drag into an invalid state; the backend
 * re-validates on PATCH so a malformed direct API call still fails.
 *
 * State shape follows the backend's `SeverityThresholdsSchema`:
 *   { yellow: number, orange: number, red: number }
 */

import { useState, useEffect, useCallback } from 'react';

const DEFAULTS = { yellow: 40, orange: 70, red: 85 };
const MIN = 0;
const MAX = 100;
const MIN_GAP = 1;

const TIERS = [
  { key: 'yellow', label: 'YELLOW (хянаж байна)', color: 'bg-amber-400' },
  { key: 'orange', label: 'ORANGE (анхаарах хэрэгтэй)', color: 'bg-orange-500' },
  { key: 'red', label: 'RED (яаралтай)', color: 'bg-rose-600' },
];

export default function SeverityThresholdsSliders({ initialValue, onSave, saving }) {
  const [value, setValue] = useState(() => ({ ...DEFAULTS, ...(initialValue || {}) }));
  const [error, setError] = useState(null);

  useEffect(() => {
    if (initialValue) setValue((prev) => ({ ...prev, ...initialValue }));
  }, [initialValue]);

  const updateTier = useCallback(
    (key, raw) => {
      const next = { ...value, [key]: Number(raw) };
      // Clamp to keep the strictly-increasing invariant. A slider drag
      // that would cross the neighbour gets pinned one unit away.
      if (key === 'yellow' && next.yellow >= next.orange) {
        next.yellow = next.orange - MIN_GAP;
      } else if (key === 'orange') {
        if (next.orange <= next.yellow) next.orange = next.yellow + MIN_GAP;
        if (next.orange >= next.red) next.orange = next.red - MIN_GAP;
      } else if (key === 'red' && next.red <= next.orange) {
        next.red = next.orange + MIN_GAP;
      }
      setValue(next);
      setError(null);
    },
    [value]
  );

  const handleSave = async () => {
    if (!(value.yellow < value.orange && value.orange < value.red)) {
      setError('Босго нь өсөх дарааллаар байх ёстой: yellow < orange < red');
      return;
    }
    try {
      await onSave(value);
    } catch (err) {
      console.warn('severity_thresholds_save_error', err);
      setError(err?.response?.data?.detail || 'Хадгалахад алдаа гарлаа.');
    }
  };

  return (
    <div className="space-y-6 rounded-lg border border-slate-800 bg-slate-900/50 p-5">
      <div>
        <h3 className="text-base font-semibold text-slate-100">
          Анхааруулгын босго (4-түвшин)
        </h3>
        <p className="mt-1 text-sm text-slate-400">
          Үйл ажиллагааны оноо энэ босгод хүрэхэд анхааруулга үүснэ. GREEN-д
          анхааруулга илгээхгүй.
        </p>
      </div>

      {TIERS.map((tier) => (
        <div key={tier.key}>
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-200">{tier.label}</span>
            <span className="font-mono text-slate-100">{value[tier.key]}</span>
          </div>
          <input
            type="range"
            min={MIN}
            max={MAX}
            step={1}
            value={value[tier.key]}
            onChange={(e) => updateTier(tier.key, e.target.value)}
            disabled={saving}
            className="mt-2 w-full accent-emerald-400"
          />
          <div className="mt-1 h-1.5 rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full ${tier.color}`}
              style={{ width: `${(value[tier.key] / MAX) * 100}%` }}
            />
          </div>
        </div>
      ))}

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
        {saving ? 'Хадгалж байна…' : 'Хадгалах'}
      </button>
    </div>
  );
}

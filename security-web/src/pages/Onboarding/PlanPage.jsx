import { useCallback, useEffect, useState } from 'react';
import { ANALYTICS_EVENTS, trackEvent } from '../../services/analytics';
import { showStuckPromptOnce } from '../../services/liveChat';
import { useIdleTimer } from '../../hooks/useIdleTimer';

// 5 minutes idle on /plan → pop the "need help?" chat prompt (T2-11).
const IDLE_PROMPT_MS = 5 * 60 * 1000;

// Money formatting for the Mongolian locale — the API returns raw ₮
// integers; display adds grouping separators.
const formatMnt = (value) =>
  `₮${Number(value || 0).toLocaleString('mn-MN')}`;

export default function PlanPage() {
  const [cameraCount, setCameraCount] = useState(5);
  const [storeCount, setStoreCount] = useState(1);
  const [location, setLocation] = useState('ub');
  const [selfSetup, setSelfSetup] = useState(false);
  const [annualPrepay, setAnnualPrepay] = useState(false);
  const [picker, setPicker] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const onIdle = useCallback(() => {
    showStuckPromptOnce({ step: 'plan' });
  }, []);
  useIdleTimer(IDLE_PROMPT_MS, onIdle);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      camera_count: String(cameraCount),
      store_count: String(storeCount),
      location,
      self_setup: String(selfSetup),
      annual_prepay: String(annualPrepay),
    });

    fetch(`/api/v1/onboarding/plan-picker?${params}`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then(setPicker)
      .catch((e) => {
        if (e?.name !== 'AbortError') {
          setError('Plan picker ачаалах боломжгүй байна.');
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [cameraCount, storeCount, location, selfSetup, annualPrepay]);

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-10">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-2xl font-semibold text-white">
          Өөрт тохирох plan сонгоорой
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Камерын тоогоо оруулахад бид {' '}
          <span className="text-emerald-400">Recommended</span> plan-г тэмдэглэнэ.
        </p>

        <section className="mt-8 grid gap-4 rounded-2xl bg-slate-800 p-6 md:grid-cols-2">
          <NumberField
            label="Хэдэн камертай вэ?"
            min={1}
            max={200}
            value={cameraCount}
            onChange={setCameraCount}
          />
          <NumberField
            label="Хэдэн салбартай вэ?"
            min={1}
            max={50}
            value={storeCount}
            onChange={setStoreCount}
          />
          <RadioGroup
            label="Байршил"
            value={location}
            options={[
              { value: 'ub', label: 'Улаанбаатар' },
              { value: 'remote', label: 'Орон нутаг' },
              { value: 'self', label: 'Зайнаас (zero dispatch)' },
            ]}
            onChange={setLocation}
          />
          <Toggle
            label="Өөрөө суулгана (self-setup)"
            value={selfSetup}
            onChange={setSelfSetup}
          />
          <Toggle
            label="Жилийн урьдчилгаа — 10% хямдрал"
            value={annualPrepay}
            onChange={setAnnualPrepay}
          />
        </section>

        {loading && (
          <p className="mt-6 text-center text-slate-400">Тооцоолж байна…</p>
        )}
        {error && (
          <p className="mt-6 text-center text-red-400" role="alert">
            {error}
          </p>
        )}

        {picker && (
          <section className="mt-6 grid gap-4 md:grid-cols-3">
            {picker.cards.map((card) => (
              <PlanCard
                key={card.plan}
                card={card}
                annualPrepay={annualPrepay}
                onSelect={() => {
          sessionStorage.setItem('planChoice', card.plan);
          trackEvent(ANALYTICS_EVENTS.PLAN_SELECTED, {
            plan: card.plan,
            camera_count: picker?.camera_count,
            store_count: picker?.store_count,
            annual_prepay: annualPrepay,
          });
        }}
              />
            ))}
          </section>
        )}
      </div>
    </div>
  );
}

function PlanCard({ card, annualPrepay, onSelect }) {
  const displayMonthly = annualPrepay ? card.annual_monthly : card.monthly_total;
  return (
    <div
      className={`rounded-2xl border p-6 transition ${
        card.recommended
          ? 'border-emerald-500 bg-slate-800 shadow-emerald-500/20 shadow-lg'
          : 'border-slate-700 bg-slate-800'
      }`}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white capitalize">
          {card.plan}
        </h2>
        {card.recommended && (
          <span className="rounded-full bg-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-400">
            ⭐ Санал болгосон
          </span>
        )}
      </div>

      <p className="mt-4 text-3xl font-bold text-white">
        {formatMnt(displayMonthly)}
        <span className="text-sm font-normal text-slate-400">/сар</span>
      </p>
      {annualPrepay && (
        <p className="mt-1 text-xs text-emerald-400">
          Жилийн урьдчилгаанд 10% хямдрал
        </p>
      )}
      <p className="mt-1 text-xs text-slate-400">
        Эхний сар: {formatMnt(card.first_month_total)}
      </p>

      <ul className="mt-6 space-y-2 text-sm text-slate-300">
        {card.features.map((f) => (
          <li key={f} className="flex items-start">
            <span className="mr-2 text-emerald-400">✓</span>
            {f}
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={onSelect}
        className={`mt-6 w-full rounded-lg px-4 py-2 font-semibold ${
          card.recommended
            ? 'bg-emerald-500 text-white hover:bg-emerald-400'
            : 'bg-slate-700 text-white hover:bg-slate-600'
        }`}
      >
        {card.plan === 'enterprise' ? 'Холбогдох' : 'Сонгох'}
      </button>
    </div>
  );
}

function NumberField({ label, min, max, value, onChange }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-300">{label}</span>
      <div className="mt-2 flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1"
        />
        <input
          type="number"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-20 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-center text-white"
        />
      </div>
    </label>
  );
}

function RadioGroup({ label, value, options, onChange }) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-slate-300">{label}</legend>
      <div className="mt-2 space-y-1">
        {options.map((o) => (
          <label
            key={o.value}
            className="flex items-center gap-2 text-sm text-slate-300"
          >
            <input
              type="radio"
              name={label}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-300">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

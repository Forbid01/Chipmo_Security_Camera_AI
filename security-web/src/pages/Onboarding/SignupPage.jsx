import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ANALYTICS_EVENTS, trackEvent } from '../../services/analytics';

// Mongolian mobile number shape: +976 + 8 digits starting with 6/7/8/9.
// Keep the client-side validator lax — authoritative check is the
// backend's `normalize_phone` in phone_format.py.
const PHONE_RE = /^\+?976?[\s-]?([6-9]\d)[\s-]?\d{2}[\s-]?\d{4}$|^[6-9]\d{7}$/;

export default function SignupPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: '',
    phone: '',
    store_name: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    trackEvent(ANALYTICS_EVENTS.SIGNUP_STARTED);
  }, []);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!form.email.includes('@')) {
      setError('Имэйл хаяг буруу байна.');
      return;
    }
    if (!form.store_name.trim()) {
      setError('Дэлгүүрийн нэр оруулна уу.');
      return;
    }
    if (form.phone && !PHONE_RE.test(form.phone.trim())) {
      setError('Утасны дугаар Монгол формат (+976) байх ёстой.');
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch('/api/v1/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email.trim(),
          phone: form.phone.trim() || null,
          store_name: form.store_name.trim(),
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setError(
          data?.detail?.message_mn ||
            'Бүртгэл үүсгэхэд алдаа гарлаа. Дахин оролдоно уу.'
        );
        return;
      }
      // Carry the email forward so /verify can submit it with the code.
      sessionStorage.setItem('onboardingEmail', form.email.trim());
      trackEvent(ANALYTICS_EVENTS.SIGNUP_COMPLETED, {
        has_phone: Boolean(form.phone.trim()),
      });
      navigate('/verify');
    } catch (err) {
      setError('Сүлжээний алдаа. Холболтоо шалгана уу.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <div className="w-full max-w-md rounded-2xl bg-slate-800 p-8 shadow-xl">
        <h1 className="text-2xl font-semibold text-white">
          🛡️ Sentry-д тавтай морил
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          14 хоног үнэгүй туршиж үз. Кредит карт шаардлагагүй.
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <Field
            label="Имэйл хаяг"
            type="email"
            required
            value={form.email}
            onChange={update('email')}
            placeholder="you@example.com"
            autoComplete="email"
          />
          <Field
            label="Утасны дугаар"
            type="tel"
            value={form.phone}
            onChange={update('phone')}
            placeholder="+976 8812-3456"
            autoComplete="tel"
            hint="Заавал биш — SMS мэдэгдэл авахыг хүсвэл бөглөнө үү."
          />
          <Field
            label="Дэлгүүрийн нэр"
            required
            value={form.store_name}
            onChange={update('store_name')}
            placeholder="Жишээ: Номин супермаркет"
          />

          {error && (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-emerald-500 px-4 py-2 font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
          >
            {submitting ? 'Илгээж байна…' : 'Үргэлжлүүлэх →'}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">
          Бүртгэлтэй юу?{' '}
          <a href="/login" className="text-emerald-400 hover:underline">
            Нэвтрэх
          </a>
        </p>
      </div>
    </div>
  );
}

function Field({ label, hint, ...inputProps }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-300">{label}</span>
      <input
        {...inputProps}
        className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
      />
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

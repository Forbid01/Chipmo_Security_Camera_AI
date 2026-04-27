import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ANALYTICS_EVENTS, trackEvent } from '../../services/analytics';

// Six individual inputs so the user can type / paste smoothly. Value
// assembly happens on submit.
const CODE_LENGTH = 6;

export default function VerifyPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [digits, setDigits] = useState(Array(CODE_LENGTH).fill(''));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const inputsRef = useRef([]);

  useEffect(() => {
    const stored = sessionStorage.getItem('onboardingEmail') || '';
    setEmail(stored);
  }, []);

  const onDigitChange = (i) => (e) => {
    const v = e.target.value.replace(/\D/g, '').slice(-1);
    const next = [...digits];
    next[i] = v;
    setDigits(next);
    if (v && i < CODE_LENGTH - 1) inputsRef.current[i + 1]?.focus();
  };

  const onDigitKey = (i) => (e) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) {
      inputsRef.current[i - 1]?.focus();
    }
  };

  const onPaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, CODE_LENGTH);
    if (!pasted) return;
    e.preventDefault();
    const next = Array(CODE_LENGTH).fill('');
    for (let i = 0; i < pasted.length; i += 1) next[i] = pasted[i];
    setDigits(next);
    inputsRef.current[Math.min(pasted.length, CODE_LENGTH - 1)]?.focus();
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    const code = digits.join('');
    if (code.length !== CODE_LENGTH) {
      setError(`${CODE_LENGTH} оронтой кодыг бүрэн оруулна уу.`);
      return;
    }
    if (!email) {
      setError('Имэйл хаяг олдсонгүй. Бүртгэл хуудас руу буцна уу.');
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch('/api/v1/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code }),
      });
      if (!response.ok) {
        setError('Код буруу эсвэл хугацаа нь дууссан байна.');
        return;
      }
      trackEvent(ANALYTICS_EVENTS.EMAIL_VERIFIED);
      navigate('/plan');
    } catch (err) {
      console.warn('verify_otp_network_error', err);
      setError('Сүлжээний алдаа. Дахин оролдоно уу.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <div className="w-full max-w-md rounded-2xl bg-slate-800 p-8 shadow-xl">
        <h1 className="text-2xl font-semibold text-white">
          Имэйлээ баталгаажуулна уу
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          {email
            ? `${email} рүү 6 оронтой код илгээгдлээ.`
            : 'Бүртгэл хуудаснаас имэйлээ оруулна уу.'}
        </p>

        <form className="mt-6" onSubmit={onSubmit}>
          <div className="flex justify-between gap-2" onPaste={onPaste}>
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => (inputsRef.current[i] = el)}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={d}
                onChange={onDigitChange(i)}
                onKeyDown={onDigitKey(i)}
                className="h-14 w-12 rounded-lg border border-slate-700 bg-slate-900 text-center text-2xl font-semibold text-white focus:border-emerald-500 focus:outline-none"
                aria-label={`Код ${i + 1}`}
              />
            ))}
          </div>

          {error && (
            <p className="mt-4 text-sm text-red-400" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mt-6 w-full rounded-lg bg-emerald-500 px-4 py-2 font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
          >
            {submitting ? 'Шалгаж байна…' : 'Баталгаажуулах →'}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">
          Код ирсэнгүй юу? Spam хавтсаа шалгаарай — эсвэл 15 минутын дараа
          дахин бүртгүүлээрэй.
        </p>
      </div>
    </div>
  );
}

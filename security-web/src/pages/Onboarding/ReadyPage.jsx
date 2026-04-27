import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Bell, Check, ExternalLink, MessageCircle, ShieldCheck, Video } from 'lucide-react';
import { ANALYTICS_EVENTS, trackEvent } from '../../services/analytics';
import { getCameraStatus, getVideoFeedUrlV2 } from '../../services/api';

const CHECKLIST = [
  {
    key: 'connect_cameras',
    label: 'Бусад камерууд нэмэх',
    detail: 'ONVIF scan эсвэл гараар RTSP URL-аар шинэ камер холбоно.',
    href: '/connect-cameras',
  },
  {
    key: 'telegram',
    label: 'Telegram мэдэгдлээ холбоно',
    detail: 'Анхны alert утсан дээр шууд ирэхийн тулд bot-оо идэвхжүүлнэ.',
  },
  {
    key: 'team',
    label: 'Ээлжийн ажилтнуудаа урина',
    detail: 'Manager болон хамгаалалтын баг alert-ыг нэг сувгаар авна.',
  },
];

export default function ReadyPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [cameraStatuses, setCameraStatuses] = useState({});
  const [loading, setLoading] = useState(true);
  const [streamFailed, setStreamFailed] = useState(false);

  const requestedCameraId = searchParams.get('camera_id');

  useEffect(() => {
    trackEvent(ANALYTICS_EVENTS.FIRST_DETECTION, {
      source: 'onboarding_ready_page',
    });
    trackEvent(ANALYTICS_EVENTS.ONBOARDING_COMPLETED, {
      source: 'onboarding_ready_page',
    });
  }, []);

  useEffect(() => {
    let mounted = true;
    getCameraStatus()
      .then((data) => {
        if (mounted) setCameraStatuses(data || {});
      })
      .catch(() => {
        if (mounted) setCameraStatuses({});
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const activeCamera = useMemo(() => {
    if (requestedCameraId && cameraStatuses[requestedCameraId]) {
      return { id: requestedCameraId, ...cameraStatuses[requestedCameraId] };
    }
    const entry = Object.entries(cameraStatuses).find(([, status]) => status?.online);
    if (entry) return { id: entry[0], ...entry[1] };
    const fallback = Object.entries(cameraStatuses)[0];
    return fallback ? { id: fallback[0], ...fallback[1] } : null;
  }, [cameraStatuses, requestedCameraId]);

  const streamUrl = activeCamera?.id ? getVideoFeedUrlV2(activeCamera.id) : null;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <main className="mx-auto grid min-h-screen max-w-7xl gap-8 px-4 py-8 lg:grid-cols-[1.35fr_0.85fr] lg:items-center lg:px-8">
        <section className="min-w-0">
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-semibold text-emerald-200">
              <ShieldCheck size={14} />
              Анхны detection баталгаажлаа
            </span>
            {activeCamera?.online && (
              <span className="inline-flex items-center gap-2 rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-1 text-xs font-semibold text-sky-200">
                <span className="h-2 w-2 rounded-full bg-sky-300" />
                Камер онлайн
              </span>
            )}
          </div>

          <h1 className="max-w-3xl text-4xl font-black tracking-normal text-white md:text-6xl">
            🎉 Бэлэн боллоо!
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
            Chipmo таны камерын дүрсийг хүлээн авч, анхны хөдөлгөөн илрүүллээ.
            Одоо alert workflow-оо баталгаажуулаад өдөр тутмын ашиглалтад шилжинэ.
          </p>

          <div className="mt-7 aspect-video overflow-hidden rounded-lg border border-slate-800 bg-slate-900 shadow-2xl shadow-black/30">
            {streamUrl && !streamFailed ? (
              <LivePreview
                src={streamUrl}
                cameraId={activeCamera.id}
                onError={() => setStreamFailed(true)}
              />
            ) : (
              <PreviewFallback loading={loading} />
            )}
          </div>
        </section>

        <aside className="rounded-lg border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
              <Check size={22} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Дараагийн алхам</h2>
              <p className="text-sm text-slate-400">3 минутын setup checklist</p>
            </div>
          </div>

          <ol className="mt-5 space-y-4">
            {CHECKLIST.map((item, index) => (
              <li key={item.key} className="flex gap-3">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-sm font-black text-white">
                  {index + 1}
                </span>
                <div>
                  <p className="font-semibold text-slate-100">{item.label}</p>
                  <p className="mt-1 text-sm leading-6 text-slate-400">{item.detail}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-6 grid gap-3">
            <Link
              to="/settings"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-3 text-sm font-bold text-white transition hover:bg-emerald-400"
            >
              <MessageCircle size={18} />
              Telegram холбох
              <ArrowRight size={16} />
            </Link>
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-4 py-3 text-sm font-bold text-slate-100 transition hover:border-slate-500 hover:bg-slate-800"
            >
              <Bell size={18} />
              Dashboard нээх
            </button>
            <a
              href="https://t.me/sentry_bot"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-sky-300 transition hover:text-sky-200"
            >
              Bot-г Telegram дээр нээх
              <ExternalLink size={15} />
            </a>
          </div>
        </aside>
      </main>
    </div>
  );
}

function LivePreview({ src, cameraId, onError }) {
  const imgRef = useRef(null);
  const [active, setActive] = useState(
    typeof document === 'undefined' || document.visibilityState === 'visible',
  );

  useEffect(() => {
    const img = imgRef.current;
    const handleVisibility = () => setActive(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      if (img) img.src = '';
    };
  }, []);

  return (
    <img
      ref={imgRef}
      key={cameraId}
      src={active ? src : ''}
      alt="Live camera preview"
      decoding="async"
      className="h-full w-full object-cover"
      onError={onError}
    />
  );
}

function PreviewFallback({ loading }) {
  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-hidden bg-slate-950">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.12)_1px,transparent_1px)] bg-[size:42px_42px]" />
      <div className="absolute left-6 top-6 flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/90 px-3 py-2 text-xs font-bold text-slate-200">
        <Video size={15} />
        {loading ? 'Preview шалгаж байна' : 'Live preview хүлээгдэж байна'}
      </div>
      <div className="relative h-32 w-56 rounded-lg border border-emerald-400/40 bg-emerald-400/10 shadow-2xl shadow-emerald-900/30">
        <div className="absolute left-7 top-7 h-16 w-16 rounded-full border-2 border-emerald-300/70" />
        <div className="absolute right-8 top-9 h-10 w-24 rounded border border-sky-300/70" />
        <div className="absolute bottom-5 left-6 right-6 h-2 rounded-full bg-emerald-300/70" />
      </div>
    </div>
  );
}

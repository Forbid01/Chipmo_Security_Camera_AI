import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Download,
  FileCode2,
  Loader2,
  Monitor,
  RefreshCw,
  Server,
  Terminal,
} from 'lucide-react';
import { api } from '../../services/api';

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchInstallerUrls(os) {
  const [configRes, binaryRes] = await Promise.all([
    api.post('/api/v1/installer/config'),
    api.get('/api/v1/installer/download', { params: { os } }),
  ]);
  return {
    configUrl: configRes.data.download_url,
    configExpiresAt: configRes.data.expires_at,
    previousKeyValidUntil: configRes.data.previous_api_key_valid_until,
    binaryUrl: binaryRes.data.download_url,
    binaryExpiresAt: binaryRes.data.expires_at,
  };
}

// ─── OS definitions ───────────────────────────────────────────────────────────

const OS_OPTIONS = [
  {
    id: 'linux',
    label: 'Linux',
    sublabel: 'Ubuntu · Debian · RHEL · Raspberry Pi',
    Icon: Terminal,
    binaryLabel: 'install.sh',
    steps: [
      {
        title: 'Installer татаж авах',
        code: '# 1. Installer татах\ncurl -fsSL "$INSTALLER_URL" -o install.sh\nchmod +x install.sh',
      },
      {
        title: 'Config татаж авах',
        code: '# 2. Config татах\nmkdir -p /etc/sentry-agent\ncurl -fsSL "$CONFIG_URL" -o /etc/sentry-agent/config.yaml',
      },
      {
        title: 'Суулгах',
        code: '# 3. Суулгах (root эрх шаардлагатай)\nsudo ./install.sh',
      },
      {
        title: 'Ажиллаж байгааг шалгах',
        code: 'systemctl status sentry-agent\njournalctl -u sentry-agent -f',
      },
    ],
  },
  {
    id: 'windows',
    label: 'Windows',
    sublabel: 'Windows 10 / 11 (64-bit)',
    Icon: Monitor,
    binaryLabel: 'SentryAgentSetup.exe',
    steps: [
      {
        title: 'config.yaml татаж авах',
        code: '# PowerShell (Admin)\n$configUrl = "<CONFIG_URL>"\nNew-Item -ItemType Directory -Force -Path "C:\\ProgramData\\SentryAgent"\nInvoke-WebRequest -Uri $configUrl -OutFile "C:\\ProgramData\\SentryAgent\\config.yaml"',
      },
      {
        title: 'Installer ажиллуулах',
        code: '# SentryAgentSetup.exe-г Admin эрхтэй ажиллуулна\n# Эсвэл command line:\nSentryAgentSetup.exe /CONFIGURL="<CONFIG_URL>" /VERYSILENT',
      },
      {
        title: 'Үйлчилгээ шалгах',
        code: '# Services-д "Sentry Agent" харагдана\nGet-Service -Name "SentryAgent"\n# Эсвэл:\nsc query SentryAgent',
      },
    ],
  },
];

// ─── Expiry countdown ─────────────────────────────────────────────────────────

function useCountdown(isoString) {
  const [remaining, setRemaining] = useState(null);

  useEffect(() => {
    if (!isoString) return;
    const tick = () => {
      const diff = new Date(isoString) - Date.now();
      setRemaining(diff > 0 ? diff : 0);
    };
    tick();
    const id = setInterval(tick, 10_000);
    return () => clearInterval(id);
  }, [isoString]);

  if (remaining === null) return null;
  if (remaining === 0) return 'Хугацаа дууссан';
  const h = Math.floor(remaining / 3_600_000);
  const m = Math.floor((remaining % 3_600_000) / 60_000);
  return `${h}ц ${m}м үлдсэн`;
}

// ─── Copy-to-clipboard button ─────────────────────────────────────────────────

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }, [text]);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return (
    <button
      type="button"
      onClick={handleCopy}
      title="Clipboard-д хуулах"
      className="ml-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-700 hover:text-slate-200"
    >
      {copied ? <CheckCircle2 size={13} className="text-emerald-400" /> : <Copy size={13} />}
      {copied ? 'Хуулсан' : 'Хуулах'}
    </button>
  );
}

// ─── Installation steps accordion ─────────────────────────────────────────────

function InstallSteps({ steps, configUrl, binaryUrl }) {
  const [open, setOpen] = useState(0);

  const interpolate = (code) =>
    code
      .replace(/\$INSTALLER_URL|<INSTALLER_URL>/g, binaryUrl || '<INSTALLER_URL>')
      .replace(/\$CONFIG_URL|<CONFIG_URL>/g, configUrl || '<CONFIG_URL>');

  return (
    <div className="mt-4 space-y-2">
      {steps.map((step, i) => {
        const isOpen = open === i;
        const code = interpolate(step.code);
        return (
          <div key={i} className="rounded-lg border border-slate-700 bg-slate-900">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? -1 : i)}
              className="flex w-full items-center justify-between px-4 py-3 text-left"
            >
              <span className="flex items-center gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/20 text-xs font-bold text-emerald-300">
                  {i + 1}
                </span>
                <span className="text-sm font-medium text-slate-200">{step.title}</span>
              </span>
              {isOpen ? (
                <ChevronUp size={16} className="text-slate-500" />
              ) : (
                <ChevronDown size={16} className="text-slate-500" />
              )}
            </button>
            {isOpen && (
              <div className="border-t border-slate-700 px-4 pb-4 pt-3">
                <div className="flex items-start justify-between rounded bg-slate-950 px-3 py-2">
                  <pre className="flex-1 overflow-x-auto text-xs leading-6 text-emerald-300">
                    {code}
                  </pre>
                  <CopyButton text={code} />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Download card ─────────────────────────────────────────────────────────────

function DownloadCard({ label, url, expiresAt, Icon, description }) {
  const countdown = useCountdown(expiresAt);
  const expired = countdown === 'Хугацаа дууссан';

  return (
    <div
      className={`flex items-center justify-between gap-4 rounded-lg border p-4 transition ${
        expired
          ? 'border-rose-800/50 bg-rose-950/30'
          : 'border-slate-700 bg-slate-900/60 hover:border-slate-600'
      }`}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-slate-300">
          <Icon size={20} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-100">{label}</p>
          <p className="text-xs text-slate-500">{description}</p>
          {countdown && (
            <p
              className={`mt-0.5 flex items-center gap-1 text-xs ${
                expired ? 'text-rose-400' : 'text-slate-500'
              }`}
            >
              <Clock size={11} />
              {countdown}
            </p>
          )}
        </div>
      </div>

      {url && !expired ? (
        <a
          href={url}
          download
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-bold text-white transition hover:bg-emerald-400"
        >
          <Download size={15} />
          Татах
        </a>
      ) : (
        <span className="shrink-0 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-500 cursor-not-allowed">
          {expired ? 'Дууссан' : 'Хүлээгдэж байна'}
        </span>
      )}
    </div>
  );
}

// ─── Previous key warning ─────────────────────────────────────────────────────

function PrevKeyWarning({ validUntil }) {
  const countdown = useCountdown(validUntil);
  if (!validUntil || countdown === null) return null;

  return (
    <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-700/40 bg-amber-900/20 px-4 py-3">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-400" />
      <p className="text-xs leading-5 text-amber-200">
        Өмнөх API key <strong>{countdown}</strong> хүртэл хүчинтэй. Одоо суулгасан
        агентууд энэ хугацаанд ажиллаж байна — шинэ config.yaml-г тэдэнд хугацаа
        дуусахаас өмнө тараана уу.
      </p>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function DownloadInstallerPage() {
  const navigate = useNavigate();
  const [selectedOs, setSelectedOs] = useState('linux');
  const [state, setState] = useState({
    status: 'idle',   // 'idle' | 'loading' | 'ready' | 'error'
    configUrl: null,
    configExpiresAt: null,
    binaryUrl: null,
    binaryExpiresAt: null,
    previousKeyValidUntil: null,
    errorMsg: null,
  });

  const osConfig = OS_OPTIONS.find((o) => o.id === selectedOs);

  const generate = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading', errorMsg: null }));
    try {
      const result = await fetchInstallerUrls(selectedOs);
      setState({
        status: 'ready',
        configUrl: result.configUrl,
        configExpiresAt: result.configExpiresAt,
        binaryUrl: result.binaryUrl,
        binaryExpiresAt: result.binaryExpiresAt,
        previousKeyValidUntil: result.previousKeyValidUntil,
        errorMsg: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        status: 'error',
        errorMsg:
          err?.response?.data?.detail ||
          'Installer холбоос үүсгэхэд алдаа гарлаа. Дахин оролдоно уу.',
      }));
    }
  }, [selectedOs]);

  // Reset when OS changes so old links don't show for the new OS
  const handleOsChange = useCallback((os) => {
    setSelectedOs(os);
    setState({
      status: 'idle',
      configUrl: null,
      configExpiresAt: null,
      binaryUrl: null,
      binaryExpiresAt: null,
      previousKeyValidUntil: null,
      errorMsg: null,
    });
  }, []);

  const isReady = state.status === 'ready';
  const isLoading = state.status === 'loading';

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-3xl px-4 py-10 md:py-16">

        {/* Header */}
        <div className="mb-8">
          <span className="inline-flex items-center gap-2 rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-1 text-xs font-semibold text-sky-200">
            <Server size={13} />
            Edge Agent суулгах
          </span>
          <h1 className="mt-4 text-3xl font-black tracking-tight text-white md:text-4xl">
            Agent татаж суулгах
          </h1>
          <p className="mt-3 text-base leading-7 text-slate-400">
            Sentry Agent таны сервер дээр ажиллаж, камеруудыг ONVIF scan-аар
            автоматаар илрүүлж, видео stream-г үүлд дамжуулна.
          </p>
        </div>

        {/* OS selector */}
        <div className="mb-6">
          <p className="mb-3 text-sm font-semibold text-slate-400">Үйлдлийн систем сонгох</p>
          <div className="grid grid-cols-2 gap-3">
            {OS_OPTIONS.map(({ id, label, sublabel, Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => handleOsChange(id)}
                className={`flex items-center gap-3 rounded-lg border px-4 py-4 text-left transition ${
                  selectedOs === id
                    ? 'border-emerald-500 bg-emerald-500/10 text-white'
                    : 'border-slate-700 bg-slate-900/50 text-slate-300 hover:border-slate-600 hover:bg-slate-900'
                }`}
              >
                <Icon size={22} className={selectedOs === id ? 'text-emerald-400' : 'text-slate-500'} />
                <div>
                  <p className="font-bold">{label}</p>
                  <p className="text-xs text-slate-500">{sublabel}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Generate button */}
        <button
          type="button"
          onClick={generate}
          disabled={isLoading}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-5 py-3.5 text-sm font-bold text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? (
            <>
              <Loader2 size={17} className="animate-spin" />
              Холбоос үүсгэж байна…
            </>
          ) : isReady ? (
            <>
              <RefreshCw size={17} />
              Шинэ холбоос үүсгэх (key rotate)
            </>
          ) : (
            <>
              <Download size={17} />
              Installer холбоос үүсгэх
            </>
          )}
        </button>

        {/* Error */}
        {state.status === 'error' && (
          <div className="mt-4 flex items-start gap-3 rounded-lg border border-rose-700/40 bg-rose-950/30 px-4 py-3">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-rose-400" />
            <p className="text-sm text-rose-200">{state.errorMsg}</p>
          </div>
        )}

        {/* Download cards */}
        {isReady && (
          <section className="mt-6 space-y-3">
            <p className="text-sm font-semibold text-slate-400">Татаж авах файлууд</p>

            <DownloadCard
              label={osConfig.binaryLabel}
              url={state.binaryUrl}
              expiresAt={state.binaryExpiresAt}
              Icon={Download}
              description="Installer binary — нэг удаа ажиллуулна"
            />
            <DownloadCard
              label="config.yaml"
              url={state.configUrl}
              expiresAt={state.configExpiresAt}
              Icon={FileCode2}
              description="Агентын тохиргоо + шинэ API key (нууцлалтай)"
            />

            <PrevKeyWarning validUntil={state.previousKeyValidUntil} />
          </section>
        )}

        {/* Installation steps */}
        {isReady && (
          <section className="mt-8">
            <p className="mb-1 text-sm font-semibold text-slate-400">Суулгах заавар</p>
            <p className="mb-3 text-xs text-slate-600">
              Дараах URL-уудыг команд руу хуулаад ажиллуулна уу.
            </p>
            <InstallSteps
              steps={osConfig.steps}
              configUrl={state.configUrl}
              binaryUrl={state.binaryUrl}
            />
          </section>
        )}

        {/* Info box (always visible) */}
        <div className="mt-8 rounded-lg border border-slate-800 bg-slate-900/50 px-5 py-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-200">
            <CheckCircle2 size={15} className="text-emerald-400" />
            Agent юу хийдэг вэ?
          </h3>
          <ul className="space-y-2 text-sm text-slate-400">
            <li className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
              Орон нутгийн сүлжээнд ONVIF WS-Discovery multicast илгээж камер автоматаар илрүүлнэ
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
              Илрүүлсэн камеруудыг <code className="rounded bg-slate-800 px-1 text-xs text-sky-300">api.sentry.mn</code> руу бүртгэж, үүлд харагдуулна
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
              60 секунд тутамд heartbeat явуулж, онлайн статусыг шинэчилнэ
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
              Нэг config.yaml — нэг API key — нэг tenant: олон сервер суулгах боломжтой
            </li>
          </ul>
        </div>

        {/* Navigation */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={() => navigate('/connect-cameras')}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-500 px-5 py-3 text-sm font-bold text-white transition hover:bg-emerald-400"
          >
            Камер холбох хуудас руу
            <ArrowRight size={16} />
          </button>
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-slate-700 px-5 py-3 text-sm font-bold text-slate-200 transition hover:border-slate-500 hover:bg-slate-800"
          >
            Dashboard руу буцах
          </button>
        </div>
      </div>
    </div>
  );
}

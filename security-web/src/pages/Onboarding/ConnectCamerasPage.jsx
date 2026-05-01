import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  KeyRound,
  Loader2,
  Network,
  Plus,
  Radio,
  RefreshCw,
  ShieldAlert,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { ANALYTICS_EVENTS, trackEvent } from '../../services/analytics';
import { api, API_BASE_URL } from '../../services/api';

// ─── Agent heartbeat timeout ──────────────────────────────────────────────────
// Agent sends a heartbeat every ~60 s.  If we haven't seen one for
// AGENT_TIMEOUT_MS we consider the agent offline.
const AGENT_TIMEOUT_MS = 90_000;

// ─── API helpers ──────────────────────────────────────────────────────────────

async function getManufacturers() {
  const { data } = await api.get('/api/v1/cameras/manufacturers');
  return Array.isArray(data) ? data : [];
}

async function postCameraTest({ url, manufacturerId }) {
  const { data } = await api.post('/api/v1/cameras/test', {
    url,
    manufacturer_id: manufacturerId || null,
  });
  return data;
}

async function postCameraProbe({ manufacturerId, ip, user, password, port }) {
  const { data } = await api.post('/api/v1/cameras/probe', {
    manufacturer_id: manufacturerId || 'generic',
    ip,
    user: user || 'admin',
    password: password || '',
    port: port ? parseInt(port, 10) : undefined,
  });
  return data;
}

// ─── WebSocket stream ─────────────────────────────────────────────────────────

function openStatusStream(token, onEvent) {
  const wsBase = API_BASE_URL.replace(/^http/, 'ws');
  const url = `${wsBase}/api/v1/onboarding/status?token=${encodeURIComponent(token)}`;
  let ws;
  let backoffMs = 1_000;
  let stopped = false;

  const connect = () => {
    if (stopped) return;
    ws = new WebSocket(url);
    ws.onopen  = () => { backoffMs = 1_000; };
    ws.onmessage = (evt) => {
      try { onEvent(JSON.parse(evt.data)); }
      catch (err) { console.warn('onboarding_ws_parse_error', err); }
    };
    ws.onclose = () => {
      if (stopped) return;
      const delay = Math.min(backoffMs, 30_000);
      backoffMs   = Math.min(backoffMs * 2, 30_000);
      setTimeout(connect, delay);
    };
    ws.onerror = () => {};
  };

  connect();
  return () => { stopped = true; try { ws?.close(); } catch (_) {} };
}

// ─── Agent status indicator ───────────────────────────────────────────────────
//
// state: "searching" → initial, no events yet
//        "online"    → received agent_registered or agent_heartbeat recently
//        "offline"   → heartbeat timeout or ws_error after having been online

function AgentStatusBar({ state }) {
  const configs = {
    searching: {
      icon:  <Loader2 size={14} className="animate-spin text-slate-400" />,
      label: 'Сүлжээнээс Agent хайж байна…',
      sub:   'Agent суулгасан компьютер асаалттай байгаа эсэхийг шалгана уу.',
      ring:  'border-slate-700/60 bg-slate-900/60',
      dot:   'bg-slate-500',
    },
    online: {
      icon:  <Radio size={14} className="text-emerald-400" />,
      label: 'Agent холбогдсон',
      sub:   'Сүлжээнд камер хайж байна.',
      ring:  'border-emerald-500/30 bg-emerald-500/5',
      dot:   'bg-emerald-400 animate-ping',
    },
    offline: {
      icon:  <ShieldAlert size={14} className="text-amber-400" />,
      label: 'Agent идэвхгүй байна',
      sub:   'Agent суулгасан компьютер унтарсан эсвэл сүлжээнд холбогдоогүй байна.',
      ring:  'border-amber-500/30 bg-amber-500/5',
      dot:   'bg-amber-400',
    },
  };

  const cfg = configs[state] ?? configs.searching;

  return (
    <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${cfg.ring}`}>
      <div className="relative mt-0.5 flex-shrink-0">
        {state === 'online' && (
          <span className="absolute inset-0 inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
        )}
        {cfg.icon}
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-100">{cfg.label}</p>
        <p className="text-xs text-slate-400 mt-0.5">{cfg.sub}</p>
      </div>
    </div>
  );
}

// ─── Error detail block ───────────────────────────────────────────────────────

function ErrorDetail({ result }) {
  if (!result || result.ok) return null;

  const { error_category, message, credential_hints, tried_urls } = result;

  // Category-specific header
  let Icon = AlertTriangle;
  let iconClass = 'text-rose-400';
  let title = 'Холболт амжилтгүй';

  if (error_category === 'network') {
    Icon = Network;
    iconClass = 'text-orange-400';
    title = 'Сүлжээнд хандаж чадсангүй';
  } else if (error_category === 'auth') {
    Icon = KeyRound;
    iconClass = 'text-amber-400';
    title = 'Нэвтрэлт амжилтгүй';
  }

  return (
    <div className="mt-3 rounded border border-rose-500/30 bg-rose-500/5 p-3 text-xs">
      <div className="flex items-center gap-1.5 font-semibold text-rose-200 mb-2">
        <Icon size={13} className={iconClass} />
        {title}
        {tried_urls > 0 && (
          <span className="ml-auto text-slate-500 font-normal">
            {tried_urls} URL туршсан
          </span>
        )}
      </div>

      {/* Specific guidance per category */}
      {error_category === 'network' && (
        <p className="text-slate-300 mb-2">
          IP хаяг (<code className="text-orange-300">{result._ip}</code>),
          порт эсвэл URL зам буруу байж болно.
          Камер тэжээл, Ethernet кабель холбогдсон эсэхийг шалгана уу.
        </p>
      )}
      {error_category === 'auth' && (
        <p className="text-slate-300 mb-2">
          Холболт нээгдсэн боловч stream ирсэнгүй.
          Нэвтрэх нэр / нууц үгийг шалгаад дахин туршина уу.
        </p>
      )}
      {!error_category && (
        <p className="text-slate-300 mb-2">{message}</p>
      )}

      {/* Credential hints */}
      {credential_hints && credential_hints.length > 0 && (
        <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/5 p-2">
          <p className="flex items-center gap-1 font-semibold text-amber-300 mb-1">
            <KeyRound size={11} />
            Үйлдвэрийн default нэвтрэх мэдээлэл
          </p>
          <ul className="space-y-0.5">
            {credential_hints.map((h, i) => (
              <li key={i} className="font-mono text-[11px]">
                <span className="text-amber-100">{h.username}</span>
                <span className="mx-1.5 text-slate-500">/</span>
                <span className="text-amber-100">{h.password || '(хоосон)'}</span>
                <span className="ml-2 text-slate-500">— {h.note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Success preview ──────────────────────────────────────────────────────────

function SuccessPreview({ result }) {
  if (!result?.ok || !result.thumbnail_b64) return null;
  return (
    <div className="mt-3 rounded border border-emerald-400/30 bg-emerald-400/5 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-emerald-300">
        <CheckCircle2 size={13} />
        Амжилттай холбогдлоо — {result.fps} FPS
        {result.tried_urls > 1 && (
          <span className="ml-2 font-normal text-slate-400">
            ({result.tried_urls} URL туршсан)
          </span>
        )}
      </div>
      <img
        src={`data:image/jpeg;base64,${result.thumbnail_b64}`}
        alt="Camera preview"
        className="w-full rounded border border-slate-700"
      />
      {result.url && (
        <p className="mt-2 break-all font-mono text-[10px] text-emerald-400">{result.url}</p>
      )}
    </div>
  );
}

// ─── Discovered camera row ────────────────────────────────────────────────────

function DiscoveredCameraRow({ cam, manufacturers }) {
  const [expanded, setExpanded]   = useState(false);
  const [probeUser, setProbeUser] = useState('admin');
  const [probePass, setProbePass] = useState('');
  const [probePort, setProbePort] = useState(cam.port ? String(cam.port) : '554');
  const [probeMfg,  setProbeMfg]  = useState(cam.manufacturer_id || 'generic');
  const [probing,   setProbing]   = useState(false);
  const [result,    setResult]    = useState(null);

  const handleProbe = async (e) => {
    e.preventDefault();
    setProbing(true);
    setResult(null);
    try {
      const data = await postCameraProbe({
        manufacturerId: probeMfg,
        ip: cam.ip,
        user: probeUser,
        password: probePass,
        port: probePort,
      });
      // Attach ip for the network-error message
      setResult({ ...data, _ip: cam.ip });
      if (data.ok) {
        trackEvent(ANALYTICS_EVENTS.CAMERA_CONNECTED, {
          manufacturer: probeMfg,
          fps: data.fps,
          source: 'discovery',
        });
      }
    } catch {
      setResult({ ok: false, message: 'Сервер рүү хандахад алдаа гарлаа.', _ip: cam.ip });
    } finally {
      setProbing(false);
    }
  };

  return (
    <li className="rounded-md border border-slate-800 bg-slate-900/50">
      <div className="flex items-center justify-between p-3">
        <div>
          <div className="flex items-center gap-2 font-mono text-sm text-slate-100">
            <Wifi size={14} className="text-emerald-400" />
            {cam.ip}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">
            {cam.manufacturer_display || cam.manufacturer_id || 'Үл таних'}
            {cam.model_hint ? ` · ${cam.model_hint}` : ''}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 rounded bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
        >
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          {expanded ? 'Хаах' : 'Тест хийх'}
        </button>
      </div>

      {expanded && (
        <form onSubmit={handleProbe} className="border-t border-slate-800 p-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Нэвтрэх нэр</span>
              <input
                type="text"
                value={probeUser}
                onChange={(e) => setProbeUser(e.target.value)}
                className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Нууц үг</span>
              <input
                type="password"
                autoComplete="new-password"
                value={probePass}
                onChange={(e) => setProbePass(e.target.value)}
                placeholder="(хоосон)"
                className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Үйлдвэрлэгч</span>
              <select
                value={probeMfg}
                onChange={(e) => setProbeMfg(e.target.value)}
                className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
              >
                {manufacturers.map((m) => (
                  <option key={m.id} value={m.id}>{m.display_name}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Порт</span>
              <input
                type="number"
                value={probePort}
                onChange={(e) => setProbePort(e.target.value)}
                className="mt-0.5 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={probing}
            className="flex w-full items-center justify-center gap-1.5 rounded bg-emerald-600 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-60"
          >
            {probing
              ? <Loader2 size={13} className="animate-spin" />
              : <CheckCircle2 size={13} />}
            {probing ? 'Туршиж байна…' : 'Автомат URL туршлага'}
          </button>
          <SuccessPreview result={result} />
          <ErrorDetail result={result} />
        </form>
      )}
    </li>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ConnectCamerasPage() {
  const navigate = useNavigate();

  const [discovered,   setDiscovered]   = useState([]);
  const [manufacturers, setManufacturers] = useState([]);
  const [agentState,   setAgentState]   = useState('searching'); // searching | online | offline
  const [manualUrl,    setManualUrl]    = useState('');
  const [manualVendor, setManualVendor] = useState('');
  const [testResult,   setTestResult]   = useState(null);
  const [testing,      setTesting]      = useState(false);

  const wsCleanupRef    = useRef(null);
  const agentTimerRef   = useRef(null);

  // ── Agent heartbeat timeout logic ──
  const resetAgentTimer = useCallback(() => {
    setAgentState('online');
    if (agentTimerRef.current) clearTimeout(agentTimerRef.current);
    agentTimerRef.current = setTimeout(() => {
      setAgentState('offline');
    }, AGENT_TIMEOUT_MS);
  }, []);

  // ── Load manufacturer catalog ──
  useEffect(() => {
    getManufacturers()
      .then((list) => {
        const sorted = [
          ...list.filter((m) => m.id !== 'generic'),
          ...list.filter((m) => m.id === 'generic'),
        ];
        setManufacturers(sorted);
      })
      .catch(() => {
        setManufacturers([
          { id: 'hikvision', display_name: 'Hikvision' },
          { id: 'dahua',     display_name: 'Dahua' },
          { id: 'axis',      display_name: 'Axis Communications' },
          { id: 'uniview',   display_name: 'Uniview (UNV)' },
          { id: 'tplink',    display_name: 'TP-Link / Tapo / VIGI' },
          { id: 'reolink',   display_name: 'Reolink' },
          { id: 'hanwha',    display_name: 'Hanwha / Wisenet' },
          { id: 'amcrest',   display_name: 'Amcrest' },
          { id: 'generic',   display_name: 'Generic / ONVIF' },
        ]);
      });
  }, []);

  // ── WebSocket — agent events + camera discovery ──
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return undefined;

    wsCleanupRef.current = openStatusStream(token, (event) => {
      const { type, payload } = event;

      // Track agent liveness
      if (type === 'agent_registered' || type === 'agent_heartbeat') {
        resetAgentTimer();
      }

      // New camera discovered
      if (type === 'camera_discovered' && payload?.ip) {
        setDiscovered((prev) => {
          if (prev.find((c) => c.ip === payload.ip)) return prev;
          return [...prev, payload];
        });
      }
    });

    return () => {
      if (typeof wsCleanupRef.current === 'function') wsCleanupRef.current();
      if (agentTimerRef.current) clearTimeout(agentTimerRef.current);
    };
  }, [resetAgentTimer]);

  // ── Manual RTSP test ──
  const handleManualTest = useCallback(async (e) => {
    e.preventDefault();
    if (!manualUrl.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const data = await postCameraTest({ url: manualUrl.trim(), manufacturerId: manualVendor || null });
      setTestResult(data);
      if (data.ok) {
        trackEvent(ANALYTICS_EVENTS.CAMERA_CONNECTED, {
          manufacturer: manualVendor || 'unknown',
          fps: data.fps,
        });
      }
    } catch {
      setTestResult({ ok: false, message: 'Сервер рүү хандахад алдаа гарлаа.' });
    } finally {
      setTesting(false);
    }
  }, [manualUrl, manualVendor]);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-slate-800 bg-slate-900/60 px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <h1 className="text-xl font-bold">Камерууд холбох</h1>
          <button
            type="button"
            onClick={() => navigate('/ready')}
            className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 hover:border-slate-600"
          >
            Алгасах
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[1.2fr_0.8fr]">

        {/* ── LEFT: agent status + discovered cameras ── */}
        <section className="space-y-4">

          {/* Agent state indicator */}
          <AgentStatusBar state={agentState} />

          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Camera size={18} />
              Илэрсэн камерууд
              {discovered.length > 0 && (
                <span className="ml-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-bold text-emerald-300">
                  {discovered.length}
                </span>
              )}
            </h2>
            <button
              type="button"
              onClick={() => setDiscovered([])}
              className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200"
            >
              <RefreshCw size={14} />
              Арилгах
            </button>
          </div>

          {discovered.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/40 p-10 text-center text-slate-400">
              <WifiOff size={28} className="mx-auto mb-3 text-slate-500" />
              <p className="text-sm">
                {agentState === 'offline'
                  ? 'Agent идэвхгүй — камер илэрч чадахгүй байна.'
                  : 'Agent сүлжээнд камер хайж байна…'}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Камерын тэжээл болон Ethernet кабель холбогдсон эсэхийг шалгана уу.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {discovered.map((cam) => (
                <DiscoveredCameraRow
                  key={cam.ip}
                  cam={cam}
                  manufacturers={manufacturers}
                />
              ))}
            </ul>
          )}
        </section>

        {/* ── RIGHT: manual RTSP entry ── */}
        <aside className="space-y-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Plus size={18} />
            Гараар RTSP URL нэмэх
          </h2>

          <form
            onSubmit={handleManualTest}
            className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-4"
          >
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                RTSP URL
              </span>
              <input
                type="text"
                autoComplete="off"
                spellCheck="false"
                placeholder="rtsp://admin:pass@192.168.1.50:554/..."
                value={manualUrl}
                onChange={(e) => setManualUrl(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 focus:border-emerald-400 focus:outline-none"
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Үйлдвэрлэгч (сонголт)
              </span>
              <select
                value={manualVendor}
                onChange={(e) => setManualVendor(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-emerald-400 focus:outline-none"
              >
                <option value="">— Таних</option>
                {manufacturers.map((m) => (
                  <option key={m.id} value={m.id}>{m.display_name}</option>
                ))}
              </select>
            </label>

            <button
              type="submit"
              disabled={testing || !manualUrl.trim()}
              className="flex w-full items-center justify-center gap-2 rounded bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {testing
                ? <Loader2 size={16} className="animate-spin" />
                : <CheckCircle2 size={16} />}
              {testing ? 'Туршиж байна…' : 'Холболтыг шалгах'}
            </button>
          </form>

          <SuccessPreview result={testResult} />
          <ErrorDetail result={testResult} />
        </aside>
      </main>
    </div>
  );
}

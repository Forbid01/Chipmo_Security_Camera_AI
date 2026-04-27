import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Loader2,
  Plus,
  RefreshCw,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { ANALYTICS_EVENTS, trackEvent } from '../../services/analytics';
import { api, API_BASE_URL } from '../../services/api';

// POST /api/v1/cameras/test reuses the T4-11 endpoint. We expose a
// dedicated wrapper here so the page's error-handling is centralized
// and easy to mock in component tests later.
async function postCameraTest({ url, manufacturerId }) {
  const { data } = await api.post('/api/v1/cameras/test', {
    url,
    manufacturer_id: manufacturerId || null,
  });
  return data;
}

async function fetchDiscoveredCameras() {
  // The `/api/v1/onboarding/discovered` route isn't wired yet — the
  // agent will push events via websocket. For now we return an empty
  // list so the UI boots; real discovery arrives via the websocket.
  return [];
}

function openStatusStream(token, onEvent) {
  // WebSocket URL — swap http(s) for ws(s) so the same origin works.
  const wsBase = API_BASE_URL.replace(/^http/, 'ws');
  const url = `${wsBase}/api/v1/onboarding/status?token=${encodeURIComponent(token)}`;
  let ws;
  let backoffMs = 1000;
  let stopped = false;

  const connect = () => {
    if (stopped) return;
    ws = new WebSocket(url);
    ws.onopen = () => {
      backoffMs = 1000;
    };
    ws.onmessage = (evt) => {
      try {
        onEvent(JSON.parse(evt.data));
      } catch (err) {
        // Ignore parse errors — server only emits JSON.
        console.warn('onboarding_ws_parse_error', err);
      }
    };
    ws.onclose = () => {
      if (stopped) return;
      // Exponential backoff, capped at 30 seconds.
      const delay = Math.min(backoffMs, 30_000);
      backoffMs = Math.min(backoffMs * 2, 30_000);
      setTimeout(connect, delay);
    };
    ws.onerror = () => {
      // Defer to onclose; don't close twice.
    };
  };

  connect();

  return () => {
    stopped = true;
    try {
      ws?.close();
    } catch (_err) {
      // ignore — socket may already be closed
    }
  };
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

export default function ConnectCamerasPage() {
  const navigate = useNavigate();

  const [discovered, setDiscovered] = useState([]);
  const [manualUrl, setManualUrl] = useState('');
  const [manualVendor, setManualVendor] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [testingCameraIp, setTestingCameraIp] = useState(null);
  const [bannerOk, setBannerOk] = useState(null);

  const wsCleanupRef = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return undefined;

    wsCleanupRef.current = openStatusStream(token, (event) => {
      if (event.type === 'camera_discovered' && event.payload?.ip) {
        setDiscovered((prev) => {
          if (prev.find((c) => c.ip === event.payload.ip)) return prev;
          return [...prev, event.payload];
        });
      }
    });
    return () => {
      if (typeof wsCleanupRef.current === 'function') wsCleanupRef.current();
    };
  }, []);

  // Initial fetch — keeps the grid populated even if we arrive before
  // any websocket events fire.
  useEffect(() => {
    let mounted = true;
    fetchDiscoveredCameras()
      .then((list) => {
        if (mounted) setDiscovered(list);
      })
      .catch(() => {
        // Non-fatal — the WS will still deliver new discoveries.
      });
    return () => {
      mounted = false;
    };
  }, []);

  const runTest = useCallback(
    async ({ url, manufacturerId, sourceIp }) => {
      setTesting(true);
      setTestingCameraIp(sourceIp ?? null);
      setBannerOk(null);
      setTestResult(null);
      try {
        const data = await postCameraTest({ url, manufacturerId });
        setTestResult({ ...data, triedUrl: url });
        setBannerOk(data.ok);
        if (data.ok) {
          trackEvent(ANALYTICS_EVENTS.CAMERA_CONNECTED, {
            manufacturer: manufacturerId || 'unknown',
            fps: data.fps,
          });
        }
      } catch (err) {
        setTestResult({
          ok: false,
          message: 'Сервер рүү хандах явцад алдаа гарлаа. Дахин оролдоно уу.',
        });
        setBannerOk(false);
      } finally {
        setTesting(false);
        setTestingCameraIp(null);
      }
    },
    []
  );

  const handleManualTest = (e) => {
    e.preventDefault();
    if (!manualUrl.trim()) return;
    runTest({ url: manualUrl.trim(), manufacturerId: manualVendor || null });
  };

  const hintsBlock = useMemo(() => {
    if (!testResult || testResult.ok) return null;
    const hints = testResult.credential_hints;
    if (!hints || hints.length === 0) return null;
    return (
      <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm text-amber-200">
        <div className="mb-2 flex items-center gap-2 font-semibold">
          <AlertTriangle size={16} />
          Үйлдвэрлэгчийн default нэвтрэх мэдээлэл
        </div>
        <ul className="space-y-1">
          {hints.map((h, idx) => (
            <li key={idx} className="font-mono text-xs">
              <span className="text-amber-100">{h.username}</span>
              <span className="mx-2 text-slate-400">/</span>
              <span className="text-amber-100">{h.password || '(хоосон)'}</span>
              <span className="ml-3 text-slate-400">— {h.note}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }, [testResult]);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-slate-800 bg-slate-900/60 px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <h1 className="text-xl font-bold">Камерууд холбох</h1>
          <button
            type="button"
            onClick={() => navigate('/ready')}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 hover:border-slate-600"
          >
            Алгасах
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[1.2fr_0.8fr]">
        {/* -------- LEFT: discovered list -------- */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Camera size={18} />
              Илэрсэн камерууд ({discovered.length})
            </h2>
            <button
              type="button"
              onClick={() => fetchDiscoveredCameras().then(setDiscovered)}
              className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200"
            >
              <RefreshCw size={14} />
              Дахин хайх
            </button>
          </div>

          {discovered.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/40 p-10 text-center text-slate-400">
              <WifiOff size={28} className="mx-auto mb-3 text-slate-500" />
              Агент сүлжээнд камер хайж байна. Камер тэжээл, Ethernet кабель холбогдсон эсэхийг шалгана уу.
            </div>
          ) : (
            <ul className="space-y-2">
              {discovered.map((cam) => (
                <li
                  key={cam.ip}
                  className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-900/50 p-3"
                >
                  <div>
                    <div className="flex items-center gap-2 font-mono text-sm text-slate-100">
                      <Wifi size={14} className="text-emerald-300" />
                      {cam.ip}
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      {cam.manufacturer_display || cam.manufacturer_id || 'Үл таних'}
                      {cam.model_hint ? ` · ${cam.model_hint}` : ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={testing && testingCameraIp === cam.ip}
                    onClick={() =>
                      runTest({
                        url: cam.default_rtsp_url,
                        manufacturerId: cam.manufacturer_id,
                        sourceIp: cam.ip,
                      })
                    }
                    className="inline-flex items-center gap-1 rounded-md bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-400 disabled:opacity-60"
                  >
                    {testing && testingCameraIp === cam.ip ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={14} />
                    )}
                    Тест
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* -------- RIGHT: manual RTSP + preview -------- */}
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
                placeholder="rtsp://admin:pass@192.168.1.50:554/Streaming/Channels/101"
                value={manualUrl}
                onChange={(e) => setManualUrl(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 focus:border-emerald-400 focus:outline-none"
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Үйлдвэрлэгч (сонголт)
              </span>
              <select
                value={manualVendor}
                onChange={(e) => setManualVendor(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-emerald-400 focus:outline-none"
              >
                <option value="">— Таних</option>
                <option value="hikvision">Hikvision</option>
                <option value="dahua">Dahua</option>
                <option value="axis">Axis</option>
                <option value="uniview">Uniview</option>
                <option value="tplink">TP-Link / Tapo / VIGI</option>
                <option value="generic">Generic / ONVIF</option>
              </select>
            </label>

            <button
              type="submit"
              disabled={testing || !manualUrl.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-emerald-500 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-400 disabled:opacity-60"
            >
              {testing ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
              Холболтыг шалгах
            </button>
          </form>

          {bannerOk === true && testResult?.thumbnail_b64 && (
            <div className="rounded-lg border border-emerald-400/40 bg-emerald-400/5 p-3">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-emerald-200">
                <CheckCircle2 size={16} />
                Амжилттай — {testResult.fps} FPS
              </div>
              <img
                src={`data:image/jpeg;base64,${testResult.thumbnail_b64}`}
                alt="Camera test thumbnail"
                className="w-full rounded-md border border-slate-800"
              />
            </div>
          )}

          {bannerOk === false && testResult && (
            <div className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-3 text-sm text-rose-200">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle size={16} />
                Холболт амжилтгүй
              </div>
              <p className="mt-1 text-slate-300">{testResult.message}</p>
              {hintsBlock}
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}

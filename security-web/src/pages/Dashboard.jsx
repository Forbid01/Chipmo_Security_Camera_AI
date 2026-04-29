/* eslint-disable no-unused-vars */
import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldCheck, List, Activity, Clock, Building2,
  Settings, LogOut, User, Camera, Store, Loader2,
  Menu, X, Download, Wifi, WifiOff, Bell, BellOff,
  Plus, ArrowRight, ThumbsUp, ThumbsDown, Image as ImageIcon,
  LayoutGrid, Maximize2
} from 'lucide-react';
import { submitAlertFeedback, API_BASE_URL } from '../services/api';
import { motion, AnimatePresence } from 'framer-motion';
import { useAlerts } from '../hooks/useAlerts';
import { WeeklyChart } from '../components/Analytics/WeeklyChart';
import { HourlyChart } from '../components/Analytics/HourlyChart';
import { AlertCard } from '../components/Logs/AlertCard';
import { VideoModal } from '../components/Monitoring/VideoModal';
import { getVideoFeedUrlV2, getUserProfile, getMyStores, getMyCameras, getCameraStatus } from '../services/api';

function Dashboard() {
  const navigate = useNavigate();
  const { alerts, chartData } = useAlerts(10000);
  const [activeVideo, setActiveVideo] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);
  const [selectedHour, setSelectedHour] = useState(null);
  const [stores, setStores] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [activeStore, setActiveStore] = useState(null);
  const [activeCamera, setActiveCamera] = useState(null);
  const [loadingStores, setLoadingStores] = useState(true);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [cameraStatuses, setCameraStatuses] = useState({});
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [viewMode, setViewMode] = useState('single'); // 'single' | 'grid'
  const prevAlertCount = useRef(0);
  const [userInfo, setUserInfo] = useState(() => {
    const stored = localStorage.getItem('user');
    return stored ? JSON.parse(stored) : {};
  });

  const VIDEO_FEED_URL = activeCamera ? getVideoFeedUrlV2(activeCamera) : null;

  // Load data — cancellable so unmount mid-flight doesn't leak setState.
  useEffect(() => {
    let cancelled = false;
    Promise.all([getUserProfile(), getMyStores(), getMyCameras()])
      .then(([profile, storesData, camerasData]) => {
        if (cancelled) return;
        setUserInfo(profile);
        localStorage.setItem('user', JSON.stringify(profile));
        const storesList = Array.isArray(storesData) ? storesData : [];
        const camerasList = Array.isArray(camerasData) ? camerasData : [];
        setStores(storesList);
        setCameras(camerasList);
        if (storesList.length > 0) {
          setActiveStore(storesList[0].id);
          const firstCam = camerasList.find(c => c.store_id === storesList[0].id);
          if (firstCam) setActiveCamera(firstCam.id);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoadingStores(false); });

    return () => { cancelled = true; };
  }, []);

  // Camera status polling — visibility-aware, cancellable.
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const controller = new AbortController();

    const fetchStatus = async () => {
      if (cancelled || document.visibilityState !== 'visible') return;
      try {
        const data = await getCameraStatus({ signal: controller.signal });
        if (!cancelled && data && typeof data === 'object' && !Array.isArray(data)) {
          // Only update when shape actually differs — prevents needless re-renders.
          setCameraStatuses((prev) => {
            const prevKeys = Object.keys(prev);
            const nextKeys = Object.keys(data);
            if (prevKeys.length === nextKeys.length) {
              let same = true;
              for (const k of nextKeys) {
                if ((prev[k]?.online) !== (data[k]?.online) ||
                    (prev[k]?.fps) !== (data[k]?.fps)) { same = false; break; }
              }
              if (same) return prev;
            }
            return data;
          });
        }
      } catch {
        // swallow — next tick will retry
      }
    };

    const schedule = () => {
      if (cancelled) return;
      timer = setTimeout(async () => {
        await fetchStatus();
        schedule();
      }, 30000);
    };

    fetchStatus();
    schedule();

    const onVisibility = () => {
      if (document.visibilityState === 'visible') fetchStatus();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  // Browser notification for new alerts
  useEffect(() => {
    if (!notificationsEnabled) return;
    if (prevAlertCount.current > 0 && alerts.length > prevAlertCount.current) {
      const newAlert = alerts[alerts.length - 1];
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Chipmo AI — Шинэ сэрэмжлүүлэг', {
          body: newAlert?.description || 'Сэжигтэй үйлдэл илэрлээ',
          icon: '/favicon.svg',
          tag: 'chipmo-alert',
        });
      }
    }
    prevAlertCount.current = alerts.length;
  }, [alerts, notificationsEnabled]);

  const enableNotifications = async () => {
    if (!('Notification' in window)) return;
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
      setNotificationsEnabled(true);
    }
  };

  const storeCameras = useMemo(
    () => cameras.filter(c => c.store_id === activeStore),
    [cameras, activeStore],
  );

  // Camera IDs that fired an alert in the last 5 minutes — used to pulse
  // the grid cell border red so operators spot the hot camera instantly.
  const camerasWithRecentAlerts = useMemo(() => {
    const ids = new Set();
    const cutoff = Date.now() - 5 * 60 * 1000;
    for (const alert of alerts) {
      if (!alert.camera_id || !alert.event_time) continue;
      const t = new Date(alert.event_time.replace(' ', 'T')).getTime();
      if (!isNaN(t) && t >= cutoff) ids.add(alert.camera_id);
    }
    return ids;
  }, [alerts]);

  const filteredAlerts = useMemo(() => {
    const result = [];
    for (const alert of alerts) {
      if (!alert.event_time) continue;
      const date = new Date(alert.event_time.replace(' ', 'T'));
      if (isNaN(date.getTime())) continue;
      const alertDay = date.toLocaleDateString('en-US', { weekday: 'short' });
      const alertHour = date.getHours();
      if (selectedDay && alertDay !== selectedDay) continue;
      if (selectedHour !== null && alertHour !== selectedHour) continue;
      if (activeStore && alert.store_id !== activeStore) continue;
      result.push(alert);
    }
    return result;
  }, [alerts, selectedDay, selectedHour, activeStore]);

  const reversedAlerts = useMemo(
    () => filteredAlerts.slice().reverse(),
    [filteredAlerts],
  );

  // CSV export
  const exportCSV = useCallback(() => {
    const headers = ['ID', 'Тайлбар', 'Цаг', 'Дэлгүүр', 'Оноо', 'Статус'];
    const rows = filteredAlerts.map(a => [
      a.id,
      `"${(a.description || '').replace(/"/g, '""')}"`,
      a.event_time,
      a.store_name || '',
      a.confidence_score ? Math.round(a.confidence_score) : '',
      a.feedback_status || 'unreviewed'
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chipmo_alerts_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filteredAlerts]);

  const hourlyChartData = useMemo(() => {
    const dayAlerts = selectedDay
      ? alerts.filter(a => new Date(a.event_time.replace(' ', 'T')).toLocaleDateString('en-US', { weekday: 'short' }) === selectedDay)
      : alerts;
    const hours = Array.from({ length: 24 }, (_, i) => ({ name: i, display: `${i}:00`, count: 0 }));
    dayAlerts.forEach(alert => {
      const h = new Date(alert.event_time.replace(' ', 'T')).getHours();
      if (hours[h]) hours[h].count++;
    });
    return hours;
  }, [alerts, selectedDay]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  };

  // Sidebar content (shared between desktop and mobile)
  const renderSidebarContent = () => (
    <>
      {/* LOGO */}
      <div
        className="p-6 lg:p-8 border-b border-slate-800/50 flex items-center gap-3 relative group overflow-hidden cursor-pointer"
        onClick={() => {
          const mainElement = document.querySelector('main');
          if (mainElement) mainElement.scrollTo({ top: 0, behavior: 'smooth' });
          setLeftOpen(false);
        }}
      >
        <div className="absolute inset-0 bg-red-600/5 blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
        <div className="relative">
          <div className="relative p-2.5 bg-gradient-to-br from-slate-900 to-black rounded-xl border border-red-500/30 group-hover:border-red-500/60 transition-colors shadow-2xl overflow-hidden">
            <ShieldCheck className="text-red-500 relative z-10" size={24} />
          </div>
          <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-600 rounded-full border-2 border-[#05080d] z-20" />
        </div>
        <div className="flex flex-col justify-center leading-none z-10">
          <h1 className="text-xl font-black tracking-tighter text-white uppercase flex items-center">
            CHIPMO<span className="text-red-600 ml-0.5">.AI</span>
          </h1>
          <span className="text-[7px] font-mono text-slate-500 tracking-[0.2em] uppercase mt-1 font-bold">Smart Loss Prevention</span>
        </div>
      </div>

      {/* USER INFO */}
      <div className="px-6 py-5 border-b border-slate-800/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-red-600 to-red-800 rounded-xl flex items-center justify-center text-white text-sm font-black border border-red-500/30">
            {(userInfo.full_name || userInfo.username || 'U').charAt(0).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-white truncate">
              {userInfo.full_name || userInfo.username || 'Хэрэглэгч'}
            </p>
            <p className="text-[10px] font-mono text-slate-500 truncate uppercase tracking-wider">
              {userInfo.org_name || 'Байгууллага тодорхойгүй'}
            </p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-6 space-y-8 overflow-y-auto scrollbar-hide">
        {/* Store list */}
        <div className="space-y-2">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] px-2 mb-4 font-bold">Дэлгүүрүүд</p>
          {loadingStores ? (
            <div className="flex justify-center py-4"><Loader2 size={18} className="animate-spin text-slate-600" /></div>
          ) : stores.length === 0 ? (
            <p className="text-xs text-slate-600 px-2">Дэлгүүр бүртгэлгүй</p>
          ) : (
            stores.map(store => (
              <button
                key={store.id}
                onClick={() => {
                  setActiveStore(store.id);
                  const firstCam = cameras.find(c => c.store_id === store.id);
                  setActiveCamera(firstCam ? firstCam.id : null);
                  setLeftOpen(false);
                }}
                className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-2xl transition-all duration-300 border ${
                  activeStore === store.id
                    ? 'bg-blue-500/10 border-blue-500/40 text-blue-400 shadow-[0_0_20px_rgba(59,130,246,0.1)]'
                    : 'bg-transparent border-transparent text-slate-500 hover:bg-slate-800/40 hover:text-slate-300'
                }`}
              >
                <Building2 size={18} />
                <div className="text-left min-w-0">
                  <span className="text-sm font-bold tracking-tight block truncate">{store.name}</span>
                  <span className="text-[10px] font-mono text-slate-600">{store.camera_count || 0} камер</span>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Camera list with status */}
        {storeCameras.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] px-2 mb-4 font-bold">Камерууд</p>
            {storeCameras.map(cam => {
              const isOnline = cameraStatuses[cam.id]?.online !== false;
              return (
                <button
                  key={cam.id}
                  onClick={() => { setActiveCamera(cam.id); setLeftOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all border ${
                    activeCamera === cam.id
                      ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-400'
                      : 'bg-transparent border-transparent text-slate-500 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="relative">
                    <Camera size={14} />
                    <div className={`absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full border border-[#0f172a] ${isOnline ? 'bg-emerald-500' : 'bg-slate-600'}`} />
                  </div>
                  <span className="text-xs font-bold truncate">{cam.name}</span>
                  {!isOnline && <WifiOff size={10} className="text-slate-600 ml-auto" />}
                </button>
              );
            })}
          </div>
        )}

        <div className="space-y-2">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] px-2 mb-4 font-bold">Удирдлага</p>
          {[
            { icon: Store, label: 'Дэлгүүрүүд', path: '/stores' },
            { icon: Camera, label: 'Камерууд', path: '/cameras' },
            { icon: Settings, label: 'Тохиргоо', path: '/settings' },
          ].map(item => (
            <button
              key={item.path}
              onClick={() => { navigate(item.path); setLeftOpen(false); }}
              className="w-full flex items-center gap-4 px-4 py-3 rounded-xl text-slate-500 hover:bg-slate-800/40 transition-all font-bold"
            >
              <item.icon size={18} />
              <span className="text-sm">{item.label}</span>
            </button>
          ))}

          {userInfo.role === 'super_admin' && (
            <button
              onClick={() => { navigate('/admin/control'); setLeftOpen(false); }}
              className="w-full flex items-center gap-4 px-4 py-3 rounded-xl text-red-400 border border-red-500/20 bg-red-500/5 hover:bg-red-500/10 hover:border-red-500/40 transition-all font-bold"
            >
              <ShieldCheck size={18} />
              <span className="text-sm">Админ Панел</span>
            </button>
          )}
        </div>
      </nav>

      <div className="p-6 border-t border-slate-800/50">
        <button
          onClick={handleLogout}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-red-500/20 text-red-500 text-xs font-bold uppercase tracking-widest hover:bg-red-500/10 transition-all"
        >
          <LogOut size={14} /> Гарах
        </button>
      </div>
    </>
  );

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-black text-slate-200 font-sans">

      {/* ═══════════════════════════════════════════════════════════════
          VIDEO BACKGROUND LAYER  z-0
      ═══════════════════════════════════════════════════════════════ */}
      <div className="absolute inset-0 z-0 bg-slate-950">
        {loadingStores ? (
          <div className="flex items-center justify-center w-full h-full">
            <Loader2 size={32} className="animate-spin text-slate-700" />
          </div>
        ) : stores.length > 0 ? (
          viewMode === 'single' ? (
            VIDEO_FEED_URL ? (
              <LiveStream
                src={VIDEO_FEED_URL}
                cameraId={activeCamera}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="flex flex-col items-center justify-center w-full h-full text-slate-700 gap-4">
                <Camera size={64} />
                <p className="text-xs font-mono uppercase tracking-widest">Камер сонгоно уу</p>
              </div>
            )
          ) : (
            <div className="w-full h-full">
              <CameraGrid
                cameras={storeCameras}
                activeCamera={activeCamera}
                camerasWithRecentAlerts={camerasWithRecentAlerts}
                onCameraClick={(camId) => { setActiveCamera(camId); setViewMode('single'); }}
              />
            </div>
          )
        ) : (
          <div className="absolute inset-0 opacity-[0.03]"
            style={{ backgroundImage: `radial-gradient(#475569 1px, transparent 1px)`, backgroundSize: '30px 30px' }} />
        )}
      </div>

      {/* Edge vignette — aids sidebar readability */}
      <div className="absolute inset-0 z-[1] pointer-events-none bg-gradient-to-r from-black/50 via-transparent to-black/50" />

      {/* ═══════════════════════════════════════════════════════════════
          LEFT TRIGGER ZONE  z-40  (20 px invisible hover strip)
      ═══════════════════════════════════════════════════════════════ */}
      <div
        className="fixed left-0 inset-y-0 w-5 z-40"
        onMouseEnter={() => setLeftOpen(true)}
      />

      {/* ═══════════════════════════════════════════════════════════════
          LEFT SIDEBAR — Navigation  z-50
      ═══════════════════════════════════════════════════════════════ */}
      <motion.aside
        className="fixed left-0 inset-y-0 w-72 z-50 flex flex-col
                   bg-[#0a0f1e]/85 backdrop-blur-md
                   border-r border-slate-700/40 shadow-2xl"
        initial={{ x: '-100%' }}
        animate={{ x: leftOpen ? '0%' : '-100%' }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        onMouseLeave={() => setLeftOpen(false)}
      >
        {renderSidebarContent()}
      </motion.aside>

      {/* ═══════════════════════════════════════════════════════════════
          RIGHT TRIGGER ZONE  z-40
      ═══════════════════════════════════════════════════════════════ */}
      <div
        className="fixed right-0 inset-y-0 w-5 z-40"
        onMouseEnter={() => setRightOpen(true)}
      />

      {/* ═══════════════════════════════════════════════════════════════
          RIGHT SIDEBAR — Alert Feed  z-50
      ═══════════════════════════════════════════════════════════════ */}
      <motion.aside
        className="fixed right-0 inset-y-0 w-80 z-50 flex flex-col
                   bg-[#0a0f1e]/85 backdrop-blur-md
                   border-l border-slate-700/40 shadow-2xl"
        initial={{ x: '100%' }}
        animate={{ x: rightOpen ? '0%' : '100%' }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        onMouseLeave={() => setRightOpen(false)}
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-700/40 bg-slate-900/30 flex justify-between items-center shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
              <List size={16} className="text-amber-500" />
            </div>
            <div>
              <h2 className="text-xs font-black uppercase tracking-widest text-slate-200">Сэрэмжлүүлэг</h2>
              <p className="text-[10px] text-slate-500 font-mono">Тоо: {filteredAlerts.length}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={exportCSV}
              className="p-1.5 rounded-lg border border-slate-700/50 text-slate-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all"
              title="CSV татах"
            >
              <Download size={14} />
            </button>
            {(selectedDay || selectedHour !== null) && (
              <button
                onClick={() => { setSelectedDay(null); setSelectedHour(null); }}
                className="text-[9px] uppercase font-bold text-red-400 hover:text-red-300 transition-colors"
              >
                Арилгах
              </button>
            )}
          </div>
        </div>

        {/* Alert list — scrollable */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-hide">
          <AnimatePresence mode="popLayout" initial={false}>
            {filteredAlerts.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.3 }}
                className="flex flex-col items-center justify-center py-20 text-slate-500 gap-4 font-mono text-center"
              >
                <Clock size={32} />
                <p className="tracking-widest uppercase text-[10px]">Энэ хугацаанд зөрчил илрээгүй</p>
              </motion.div>
            ) : (
              reversedAlerts.map((alert, index) => (
                <motion.div
                  key={alert.id || index}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  layout
                  onClick={() => setSelectedAlert(alert)}
                  className="cursor-pointer"
                >
                  <AlertCard alert={alert} onSelect={setActiveVideo} />
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </div>

        {/* Charts — pinned at bottom of right sidebar */}
        <div className="shrink-0 border-t border-slate-700/40 p-3 space-y-3 bg-slate-900/20">
          <WeeklyChart
            data={chartData}
            selectedDay={selectedDay}
            onBarClick={(day) => { setSelectedDay(day); setSelectedHour(null); }}
            onClearFilter={() => { setSelectedDay(null); setSelectedHour(null); }}
          />
          <HourlyChart
            data={hourlyChartData}
            selectedHour={selectedHour}
            onHourClick={(hour) => setSelectedHour(hour)}
            onClearHour={() => setSelectedHour(null)}
          />
        </div>
      </motion.aside>

      {/* ═══════════════════════════════════════════════════════════════
          TOP FLOATING CONTROLS  z-50
          Low opacity at rest → full opacity on hover
      ═══════════════════════════════════════════════════════════════ */}
      <motion.div
        className="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2"
        initial={{ opacity: 0.25 }}
        whileHover={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
      >
        {/* Active store name */}
        <div className="px-4 py-2 rounded-full bg-black/60 backdrop-blur-md border border-slate-700/40 text-xs font-black uppercase tracking-tight text-white whitespace-nowrap">
          {stores.find(s => s.id === activeStore)?.name || 'Chipmo.AI'}
        </div>

        {/* Single / Grid toggle */}
        <div className="flex items-center rounded-full border border-slate-700/40 bg-black/60 backdrop-blur-md p-0.5">
          <button
            onClick={() => setViewMode('single')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold uppercase transition-all ${
              viewMode === 'single' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Maximize2 size={11} /> Single
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold uppercase transition-all ${
              viewMode === 'grid' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <LayoutGrid size={11} /> Grid
          </button>
        </div>

        {/* Live indicator */}
        <div className="flex items-center gap-2 bg-black/60 backdrop-blur-md px-3 py-2 rounded-full border border-slate-700/40">
          <div className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">Live</span>
        </div>

        {/* Notification toggle */}
        <button
          onClick={notificationsEnabled ? () => setNotificationsEnabled(false) : enableNotifications}
          title={notificationsEnabled ? 'Мэдэгдэл идэвхтэй' : 'Мэдэгдэл идэвхжүүлэх'}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-full border backdrop-blur-md bg-black/60 transition-all text-[10px] font-bold uppercase ${
            notificationsEnabled
              ? 'border-emerald-500/40 text-emerald-400'
              : 'border-slate-700/40 text-slate-500 hover:text-slate-300'
          }`}
        >
          {notificationsEnabled ? <Bell size={12} /> : <BellOff size={12} />}
        </button>
      </motion.div>

      {/* ═══════════════════════════════════════════════════════════════
          MOBILE FALLBACK tap buttons (hidden on lg+)
      ═══════════════════════════════════════════════════════════════ */}
      <div className="fixed top-4 left-4 z-50 lg:hidden">
        <button
          onClick={() => setLeftOpen(v => !v)}
          className="p-2.5 rounded-xl bg-black/60 backdrop-blur-md border border-slate-700/40 text-white"
        >
          <Menu size={18} />
        </button>
      </div>
      <div className="fixed top-4 right-4 z-50 lg:hidden">
        <button
          onClick={() => setRightOpen(v => !v)}
          className="p-2.5 rounded-xl bg-black/60 backdrop-blur-md border border-slate-700/40 text-white"
        >
          <Bell size={18} />
        </button>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          ONBOARDING OVERLAY  z-30  (no stores yet)
      ═══════════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {!loadingStores && stores.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-30 flex flex-col items-center justify-center p-6 bg-black/75 backdrop-blur-sm"
          >
            <div className="max-w-lg w-full text-center">
              <div className="p-6 bg-blue-500/10 rounded-3xl border border-blue-500/20 mb-8 inline-block">
                <ShieldCheck size={48} className="text-blue-400" />
              </div>
              <h2 className="text-2xl font-black text-white uppercase mb-3">Тавтай морил!</h2>
              <p className="text-slate-400 text-sm mb-10 leading-relaxed">
                Chipmo AI ашиглаж эхлэхийн тулд эхлээд дэлгүүрээ бүртгэж, дараа нь камераа холбоно уу.
              </p>
              <div className="space-y-4">
                <button onClick={() => navigate('/stores')} className="w-full flex items-center justify-between px-6 py-4 rounded-2xl bg-blue-600/10 border border-blue-500/30 text-blue-400 hover:bg-blue-600/20 transition-all group">
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-xl bg-blue-500/20"><Store size={20} /></div>
                    <div className="text-left">
                      <p className="text-sm font-bold text-white">1. Дэлгүүр нэмэх</p>
                      <p className="text-[10px] text-slate-500">Салбарын нэр, хаяг оруулах</p>
                    </div>
                  </div>
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
                <button onClick={() => navigate('/cameras')} className="w-full flex items-center justify-between px-6 py-4 rounded-2xl bg-slate-800/30 border border-slate-700/30 text-slate-400 hover:bg-slate-800/50 transition-all group">
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-xl bg-slate-700/30"><Camera size={20} /></div>
                    <div className="text-left">
                      <p className="text-sm font-bold text-white">2. Камер холбох</p>
                      <p className="text-[10px] text-slate-500">IP камерын URL оруулах</p>
                    </div>
                  </div>
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
                <button onClick={() => navigate('/settings')} className="w-full flex items-center justify-between px-6 py-4 rounded-2xl bg-slate-800/30 border border-slate-700/30 text-slate-400 hover:bg-slate-800/50 transition-all group">
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-xl bg-slate-700/30"><Bell size={20} /></div>
                    <div className="text-left">
                      <p className="text-sm font-bold text-white">3. Telegram мэдэгдэл</p>
                      <p className="text-[10px] text-slate-500">Chat ID оруулж мэдэгдэл авах</p>
                    </div>
                  </div>
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <VideoModal videoUrl={activeVideo} onClose={() => setActiveVideo(null)} />
      <AlertDetailModal alert={selectedAlert} onClose={() => setSelectedAlert(null)} onPlayVideo={setActiveVideo} />
    </div>
  );
}

// Visibility-aware MJPEG stream. Closes the connection when the tab is hidden
// or the component is off-screen; rAF-scheduled resume avoids a render spike.
const LiveStream = React.memo(function LiveStream({ src, cameraId, onLoad, className }) {
  const imgRef = useRef(null);
  const [active, setActive] = useState(
    typeof document === 'undefined' || document.visibilityState === 'visible',
  );

  useEffect(() => {
    let rafId = null;
    const img = imgRef.current;

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(() => setActive(true));
      } else {
        setActive(false);
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      if (rafId) cancelAnimationFrame(rafId);
      if (img) img.src = '';
    };
  }, []);

  // IntersectionObserver — pause when scrolled off-screen on mobile.
  useEffect(() => {
    const node = imgRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return;
    const obs = new IntersectionObserver(
      ([entry]) => setActive(entry.isIntersecting && document.visibilityState === 'visible'),
      { threshold: 0.1 },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, []);

  return (
    <img
      ref={imgRef}
      key={cameraId}
      src={active ? src : ''}
      alt="AI Feed"
      decoding="async"
      loading="lazy"
      onLoad={onLoad}
      className={className ?? 'w-full h-full object-contain'}
    />
  );
});

// ─── Grid helpers ────────────────────────────────────────────────────────────

function getGridClass(count) {
  if (count <= 1) return 'grid-cols-1';
  if (count <= 2) return 'grid-cols-2';
  if (count <= 4) return 'grid-cols-2';
  if (count <= 6) return 'grid-cols-3';
  if (count <= 8) return 'grid-cols-4';
  if (count <= 9) return 'grid-cols-3';
  return 'grid-cols-4';
}

// Single cell in the grid — manages its own loading state.
function GridCameraCell({ cam, isActive, hasAlert, onClick }) {
  const [loaded, setLoaded] = useState(false);
  const src = getVideoFeedUrlV2(cam.id);

  // If the MJPEG stream hasn't fired onLoad within 6s, stop showing the spinner
  // so a dead camera doesn't show a permanent loader.
  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 6000);
    return () => clearTimeout(t);
  }, [cam.id]);

  return (
    <div
      onClick={onClick}
      title={`${cam.name} — дарж томруулах`}
      className={`
        relative cursor-pointer rounded-xl overflow-hidden bg-slate-950 aspect-video
        border-2 transition-all duration-300 group
        ${hasAlert
          ? 'border-red-500 shadow-[0_0_12px_rgba(239,68,68,0.5)]'
          : isActive
            ? 'border-blue-500/70'
            : 'border-slate-800 hover:border-slate-600'
        }
      `}
    >
      {/* Loading overlay — fades out on first frame */}
      {!loaded && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-slate-950/90">
          <Loader2 size={18} className="animate-spin text-slate-500" />
          <span className="text-[9px] font-mono text-slate-600 uppercase tracking-widest">Холбогдож байна...</span>
        </div>
      )}

      {/* Alert pulse ring */}
      {hasAlert && (
        <div className="absolute inset-0 z-20 rounded-xl border-2 border-red-500 animate-pulse pointer-events-none" />
      )}

      <LiveStream
        src={src}
        cameraId={cam.id}
        onLoad={() => setLoaded(true)}
        className="w-full h-full object-contain"
      />

      {/* Name + alert badge overlay */}
      <div className="absolute bottom-0 left-0 right-0 z-10 px-2 py-1.5 bg-gradient-to-t from-black/80 to-transparent">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold text-white truncate">{cam.name}</p>
          {hasAlert && (
            <span className="text-[8px] font-black text-red-400 uppercase animate-pulse">● Alert</span>
          )}
        </div>
      </div>

      {/* Hover enlarge hint */}
      <div className="absolute top-2 right-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="p-1 rounded-md bg-black/60">
          <Maximize2 size={10} className="text-white" />
        </div>
      </div>
    </div>
  );
}

// Multi-camera grid for the current store.
function CameraGrid({ cameras, activeCamera, camerasWithRecentAlerts, onCameraClick }) {
  if (cameras.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-600 gap-3">
        <Camera size={36} />
        <p className="text-xs font-mono uppercase tracking-widest">Энэ дэлгүүрт камер бүртгэлгүй</p>
      </div>
    );
  }

  return (
    <div className={`grid ${getGridClass(cameras.length)} gap-1 p-2`}>
      {cameras.map(cam => (
        <GridCameraCell
          key={cam.id}
          cam={cam}
          isActive={cam.id === activeCamera}
          hasAlert={camerasWithRecentAlerts.has(cam.id)}
          onClick={() => onCameraClick(cam.id)}
        />
      ))}
    </div>
  );
}

// Alert Detail Modal
function AlertDetailModal({ alert, onClose, onPlayVideo }) {
  const [feedbackStatus, setFeedbackStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (alert) setFeedbackStatus(alert.feedback_status || 'unreviewed');
  }, [alert]);

  if (!alert) return null;

  const handleFeedback = async (type) => {
    if (loading || feedbackStatus !== 'unreviewed') return;
    setLoading(true);
    try {
      await submitAlertFeedback(alert.id, type);
      setFeedbackStatus(type);
    } catch (error){
      console.error('Feedback error:', error);
    } finally { setLoading(false); }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
          className="relative w-full max-w-2xl bg-[#0f172a] rounded-3xl border border-slate-700/50 overflow-hidden shadow-2xl"
        >
          {/* Close */}
          <button onClick={onClose} className="absolute top-4 right-4 p-2 bg-black/50 hover:bg-red-500 rounded-full z-10 transition-colors text-white">
            <X size={20} />
          </button>

          {/* Image */}
          {alert.web_url ? (
            <div className="w-full aspect-video bg-black">
              <img src={alert.web_url} alt="Alert" className="w-full h-full object-contain" />
            </div>
          ) : (
            <div className="w-full aspect-video bg-slate-950 flex items-center justify-center">
              <ImageIcon size={48} className="text-slate-700" />
            </div>
          )}

          {/* Info */}
          <div className="p-6 space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-black text-white uppercase">
                  Сэрэмжлүүлэг #{alert.id}
                </h3>
                <p className="text-sm text-slate-400 mt-1">{alert.description || 'Сэжигтэй үйлдэл илэрлээ'}</p>
              </div>
              {alert.confidence_score && (
                <div className="text-right">
                  <p className="text-2xl font-black text-red-500">{Math.round(alert.confidence_score)}</p>
                  <p className="text-[10px] text-slate-500 uppercase font-mono">Оноо</p>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-3 text-[10px] font-mono uppercase text-slate-500">
              <span className="px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50">{alert.event_time}</span>
              {alert.store_name && <span className="px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50">{alert.store_name}</span>}
              {alert.camera_name && <span className="px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50">{alert.camera_name}</span>}
            </div>

            {/* Feedback */}
            <div className="flex items-center gap-3 pt-2">
              {feedbackStatus === 'unreviewed' ? (
                <>
                  <button
                    onClick={() => handleFeedback('true_positive')}
                    disabled={loading}
                    className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-emerald-500/30 text-emerald-400 text-xs font-bold uppercase hover:bg-emerald-500/10 transition-all disabled:opacity-50"
                  >
                    <ThumbsUp size={14} /> Зөв сэрэмжлүүлэг
                  </button>
                  <button
                    onClick={() => handleFeedback('false_positive')}
                    disabled={loading}
                    className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-yellow-500/30 text-yellow-400 text-xs font-bold uppercase hover:bg-yellow-500/10 transition-all disabled:opacity-50"
                  >
                    <ThumbsDown size={14} /> Буруу сэрэмжлүүлэг
                  </button>
                </>
              ) : (
                <div className={`w-full py-3 rounded-xl text-center text-xs font-bold uppercase ${
                  feedbackStatus === 'true_positive'
                    ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
                    : 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-400'
                }`}>
                  {feedbackStatus === 'true_positive' ? 'Зөв сэрэмжлүүлэг гэж тэмдэглэсэн' : 'Буруу сэрэмжлүүлэг гэж тэмдэглэсэн'}
                </div>
              )}
            </div>

            {/* Video button */}
            {alert.video_url && (
              <button
                onClick={() => { onPlayVideo(alert.video_url); onClose(); }}
                className="w-full py-3 rounded-xl bg-red-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-red-500 transition-all flex items-center justify-center gap-2"
              >
                <Activity size={14} /> Бичлэг үзэх
              </button>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

export default Dashboard;

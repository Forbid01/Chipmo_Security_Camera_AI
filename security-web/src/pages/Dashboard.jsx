/* eslint-disable no-unused-vars */
import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldCheck, List, Activity, Clock, Building2,
  Settings, LogOut, User, Camera, Store, Loader2,
  Menu, X, Download, Wifi, WifiOff, Bell, BellOff,
  Plus, ArrowRight, ThumbsUp, ThumbsDown, Image as ImageIcon
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
  const { alerts, chartData } = useAlerts(3000);
  const [activeVideo, setActiveVideo] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);
  const [selectedHour, setSelectedHour] = useState(null);
  const [stores, setStores] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [activeStore, setActiveStore] = useState(null);
  const [activeCamera, setActiveCamera] = useState(null);
  const [loadingStores, setLoadingStores] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [cameraStatuses, setCameraStatuses] = useState({});
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const prevAlertCount = useRef(0);
  const [userInfo, setUserInfo] = useState(() => {
    const stored = localStorage.getItem('user');
    return stored ? JSON.parse(stored) : {};
  });

  const VIDEO_FEED_URL = activeCamera ? getVideoFeedUrlV2(activeCamera) : null;

  // Load data
  useEffect(() => {
    Promise.all([getUserProfile(), getMyStores(), getMyCameras()])
      .then(([profile, storesData, camerasData]) => {
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
      .finally(() => setLoadingStores(false));
  }, []);

  // Camera status polling
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await getCameraStatus();
        if (data && typeof data === 'object') {
          setCameraStatuses(data);
        }
      } catch {}
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
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

  const storeCameras = cameras.filter(c => c.store_id === activeStore);

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
  }, []);

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

  const filteredAlerts = useMemo(() => {
    return alerts.filter(alert => {
      const date = new Date(alert.event_time.replace(' ', 'T'));
      const alertDay = date.toLocaleDateString('en-US', { weekday: 'short' });
      const alertHour = date.getHours();
      const matchesDay = selectedDay ? alertDay === selectedDay : true;
      const matchesHour = selectedHour !== null ? alertHour === selectedHour : true;
      const matchesStore = activeStore ? (alert.store_id === activeStore) : true;
      return matchesDay && matchesHour && matchesStore;
    });
  }, [alerts, selectedDay, selectedHour, activeStore]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  };

  // Sidebar content (shared between desktop and mobile)
  const SidebarContent = () => (
    <>
      {/* LOGO */}
      <div
        className="p-6 lg:p-8 border-b border-slate-800/50 flex items-center gap-3 relative group overflow-hidden cursor-pointer"
        onClick={() => {
          const mainElement = document.querySelector('main');
          if (mainElement) mainElement.scrollTo({ top: 0, behavior: 'smooth' });
          setSidebarOpen(false);
        }}
      >
        <div className="absolute inset-0 bg-red-600/5 blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
        <div className="relative">
          <div className="relative p-2.5 bg-gradient-to-br from-slate-900 to-black rounded-xl border border-red-500/30 group-hover:border-red-500/60 transition-all duration-500 shadow-2xl overflow-hidden">
            <ShieldCheck className="text-red-500 group-hover:rotate-[15deg] transition-transform duration-500 relative z-10" size={24} />
            <motion.div
              animate={{ y: [-20, 40] }}
              transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
              className="absolute left-0 w-full h-[1px] bg-red-400/40 shadow-[0_0_8px_red] z-0"
            />
          </div>
          <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-600 rounded-full border-2 border-[#05080d] z-20">
            <div className="absolute inset-0 bg-red-500 rounded-full animate-ping" />
          </div>
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
                  setSidebarOpen(false);
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
                  onClick={() => { setActiveCamera(cam.id); setSidebarOpen(false); }}
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
              onClick={() => { navigate(item.path); setSidebarOpen(false); }}
              className="w-full flex items-center gap-4 px-4 py-3 rounded-xl text-slate-500 hover:bg-slate-800/40 transition-all font-bold"
            >
              <item.icon size={18} />
              <span className="text-sm">{item.label}</span>
            </button>
          ))}
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
    <div className="flex h-screen w-screen bg-[#05080d] text-slate-200 overflow-hidden font-sans relative">
      {/* BACKGROUND */}
      <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none"
           style={{ backgroundImage: `radial-gradient(#475569 1px, transparent 1px)`, backgroundSize: '30px 30px' }} />

      {/* MOBILE OVERLAY */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60] lg:hidden"
          />
        )}
      </AnimatePresence>

      {/* SIDEBAR — hidden on mobile, slide-in when open */}
      <aside className={`
        fixed lg:relative inset-y-0 left-0 z-[70]
        w-72 bg-[#0f172a]/95 lg:bg-[#0f172a]/40 backdrop-blur-3xl border-r border-slate-800/50
        flex flex-col
        transform transition-transform duration-300 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Mobile close button */}
        <button
          onClick={() => setSidebarOpen(false)}
          className="lg:hidden absolute top-4 right-4 p-2 rounded-lg text-slate-400 hover:text-white z-10"
        >
          <X size={20} />
        </button>
        <SidebarContent />
      </aside>

      {/* MAIN CONTENT */}
      <main className="flex-1 overflow-y-auto relative z-10 p-4 md:p-6 lg:p-10 scrollbar-hide">
        {/* Mobile top bar */}
        <div className="flex items-center justify-between mb-4 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2.5 rounded-xl border border-slate-800 hover:bg-slate-800/50 transition-all"
          >
            <Menu size={20} />
          </button>
          <h1 className="text-lg font-black tracking-tighter text-white uppercase">
            CHIPMO<span className="text-red-600">.AI</span>
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={notificationsEnabled ? () => setNotificationsEnabled(false) : enableNotifications}
              className={`p-2 rounded-lg border transition-all ${notificationsEnabled ? 'border-emerald-500/40 text-emerald-400' : 'border-slate-800 text-slate-500'}`}
              title={notificationsEnabled ? 'Мэдэгдэл идэвхтэй' : 'Мэдэгдэл идэвхжүүлэх'}
            >
              {notificationsEnabled ? <Bell size={16} /> : <BellOff size={16} />}
            </button>
          </div>
        </div>

        <div className="max-w-[1600px] mx-auto w-full">
          {/* Onboarding empty state */}
          {!loadingStores && stores.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center py-20 max-w-lg mx-auto text-center"
            >
              <div className="p-6 bg-blue-500/10 rounded-3xl border border-blue-500/20 mb-8">
                <ShieldCheck size={48} className="text-blue-400" />
              </div>
              <h2 className="text-2xl font-black text-white uppercase mb-3">Тавтай морил!</h2>
              <p className="text-slate-400 text-sm mb-10 leading-relaxed">
                Chipmo AI ашиглаж эхлэхийн тулд эхлээд дэлгүүрээ бүртгэж, дараа нь камераа холбоно уу.
              </p>
              <div className="space-y-4 w-full">
                <button
                  onClick={() => navigate('/stores')}
                  className="w-full flex items-center justify-between px-6 py-4 rounded-2xl bg-blue-600/10 border border-blue-500/30 text-blue-400 hover:bg-blue-600/20 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-xl bg-blue-500/20"><Store size={20} /></div>
                    <div className="text-left">
                      <p className="text-sm font-bold text-white">1. Дэлгүүр нэмэх</p>
                      <p className="text-[10px] text-slate-500">Салбарын нэр, хаяг оруулах</p>
                    </div>
                  </div>
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
                <button
                  onClick={() => navigate('/cameras')}
                  className="w-full flex items-center justify-between px-6 py-4 rounded-2xl bg-slate-800/30 border border-slate-700/30 text-slate-400 hover:bg-slate-800/50 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-xl bg-slate-700/30"><Camera size={20} /></div>
                    <div className="text-left">
                      <p className="text-sm font-bold text-white">2. Камер холбох</p>
                      <p className="text-[10px] text-slate-500">IP камерын URL оруулах</p>
                    </div>
                  </div>
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
                <button
                  onClick={() => navigate('/settings')}
                  className="w-full flex items-center justify-between px-6 py-4 rounded-2xl bg-slate-800/30 border border-slate-700/30 text-slate-400 hover:bg-slate-800/50 transition-all group"
                >
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
            </motion.div>
          ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
            {/* Left: Video & Analytics */}
            <div className="lg:col-span-8 space-y-6 lg:space-y-8">
              <div className="flex justify-between items-end px-2">
                <div>
                  <h2 className="text-2xl lg:text-3xl font-black text-white uppercase tracking-tight italic">
                    {stores.find(s => s.id === activeStore)?.name || 'Дэлгүүр сонгоно уу'}
                  </h2>
                  <p className="text-xs font-mono text-blue-500/80 uppercase tracking-widest mt-1">
                    {storeCameras.find(c => c.id === activeCamera)?.name || 'Камер сонгогдоогүй'}
                  </p>
                </div>
                <div className="hidden md:flex items-center gap-3">
                  {/* Notification toggle (desktop) */}
                  <button
                    onClick={notificationsEnabled ? () => setNotificationsEnabled(false) : enableNotifications}
                    className={`flex items-center gap-2 px-3 py-2 rounded-full border transition-all text-[10px] font-bold uppercase ${
                      notificationsEnabled
                        ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/5'
                        : 'border-slate-800 text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {notificationsEnabled ? <Bell size={12} /> : <BellOff size={12} />}
                    {notificationsEnabled ? 'Мэдэгдэл ON' : 'Мэдэгдэл'}
                  </button>
                  <div className="flex items-center gap-2 bg-slate-900/50 px-4 py-2 rounded-full border border-slate-800">
                    <div className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">Систем идэвхтэй</span>
                  </div>
                </div>
              </div>

              {/* LIVE FEED */}
              <div className="bg-[#0f172a]/60 backdrop-blur-xl rounded-2xl lg:rounded-[3rem] border border-slate-800/50 overflow-hidden shadow-2xl relative ring-1 ring-white/5 bg-black">
                <div className="p-3 lg:p-5 bg-slate-900/40 border-b border-slate-800/50 flex justify-between items-center font-mono">
                  <span className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-blue-400">
                    <Activity size={14} className="animate-pulse" /> {storeCameras.find(c => c.id === activeCamera)?.name || 'Камер'}
                  </span>
                  <span className="bg-red-600 text-[9px] px-3 py-1 rounded-full text-white font-bold animate-pulse uppercase">Live</span>
                </div>
                <div className="w-full relative aspect-video flex items-center justify-center bg-slate-950">
                  {VIDEO_FEED_URL ? (
                    <img key={activeCamera} src={VIDEO_FEED_URL} className="w-full h-full object-contain" alt="AI Feed" />
                  ) : (
                    <div className="flex flex-col items-center gap-4 text-slate-600">
                      <Camera size={48} />
                      <p className="text-xs font-mono uppercase tracking-widest">Камер сонгоно уу</p>
                    </div>
                  )}
                </div>
              </div>

              {/* CHARTS */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 lg:gap-6">
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
            </div>

            {/* Right: Logs */}
            <div className="lg:col-span-4">
              <div className="bg-[#0f172a]/60 backdrop-blur-xl rounded-2xl lg:rounded-[2.5rem] border border-slate-800/50 flex flex-col h-[500px] lg:h-[calc(100vh-140px)] shadow-2xl overflow-hidden ring-1 ring-white/5">
                <div className="p-5 lg:p-8 border-b border-slate-800 bg-slate-900/40 flex justify-between items-center">
                  <div className="flex items-center gap-3">
                    <List size={20} className="text-amber-500" />
                    <div>
                      <h2 className="text-xs font-black uppercase tracking-widest text-slate-200">Сэрэмжлүүлэг</h2>
                      <p className="text-[10px] text-slate-500 font-mono">Тоо: {filteredAlerts.length}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* CSV Export */}
                    <button
                      onClick={exportCSV}
                      className="p-1.5 rounded-lg border border-slate-800 text-slate-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all"
                      title="CSV татах"
                    >
                      <Download size={14} />
                    </button>
                    {(selectedDay || selectedHour !== null) && (
                      <button onClick={() => { setSelectedDay(null); setSelectedHour(null); }}
                              className="text-[9px] uppercase font-bold text-red-400 hover:text-red-300 transition-colors">
                        Арилгах
                      </button>
                    )}
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-4 scrollbar-hide">
                  <AnimatePresence mode="popLayout" initial={false}>
                    {filteredAlerts.length === 0 ? (
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} className="flex flex-col items-center justify-center py-20 text-slate-500 gap-4 font-mono text-center">
                        <Clock size={32} />
                        <p className="tracking-widest uppercase text-[10px]">Энэ хугацаанд зөрчил илрээгүй</p>
                      </motion.div>
                    ) : (
                      [...filteredAlerts].reverse().map((alert, index) => (
                        <motion.div key={alert.id || index} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} layout
                          onClick={() => setSelectedAlert(alert)}
                          className="cursor-pointer"
                        >
                          <AlertCard alert={alert} onSelect={setActiveVideo} />
                        </motion.div>
                      ))
                    )}
                  </AnimatePresence>
                </div>
              </div>
            </div>
          </div>
          )}
        </div>
      </main>

      <VideoModal videoUrl={activeVideo} onClose={() => setActiveVideo(null)} />
      <AlertDetailModal alert={selectedAlert} onClose={() => setSelectedAlert(null)} onPlayVideo={setActiveVideo} />
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
    } catch {} finally { setLoading(false); }
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

/* eslint-disable no-unused-vars */
import React, { useState, useMemo } from 'react';
import { 
  ShieldCheck, List, Activity, Clock, Building2, 
  Settings, LogOut, LayoutDashboard, ShieldAlert 
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAlerts } from '../hooks/useAlerts';
import { WeeklyChart } from '../components/Analytics/WeeklyChart';
import { HourlyChart } from '../components/Analytics/HourlyChart';
import { AlertCard } from '../components/Logs/AlertCard';
import { VideoModal } from '../components/Monitoring/VideoModal';
import { API_BASE_URL } from '../services/api';

function Dashboard() {
  // --- STATE & DATA ---
  const { alerts, chartData } = useAlerts(3000);
  const [activeVideo, setActiveVideo] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);
  const [selectedHour, setSelectedHour] = useState(null);
  const [activeCamera, setActiveCamera] = useState('mac'); 
  const VIDEO_FEED_URL = `${API_BASE_URL}/video_feed/${activeCamera}`;


  // --- LOGIC: HOURLY CHART DATA ---
  const hourlyChartData = useMemo(() => {
    const dayAlerts = selectedDay 
      ? alerts.filter(a => new Date(a.event_time.replace(' ', 'T')).toLocaleDateString('en-US', { weekday: 'short' }) === selectedDay)
      : alerts;

    const hours = Array.from({ length: 24 }, (_, i) => ({ 
        name: i, 
        display: `${i}:00`, 
        count: 0 
    }));

    dayAlerts.forEach(alert => {
      const h = new Date(alert.event_time.replace(' ', 'T')).getHours();
      if (hours[h]) hours[h].count++;
    });
    return hours;
  }, [alerts, selectedDay]);

  // --- LOGIC: FILTERED ALERTS ---
  const filteredAlerts = useMemo(() => {
    return alerts.filter(alert => {
      const date = new Date(alert.event_time.replace(' ', 'T'));
      const alertDay = date.toLocaleDateString('en-US', { weekday: 'short' });
      const alertHour = date.getHours();

      const matchesDay = selectedDay ? alertDay === selectedDay : true;
      const matchesHour = selectedHour !== null ? alertHour === selectedHour : true;

      return matchesDay && matchesHour;
    });
  }, [alerts, selectedDay, selectedHour]);

  const handleLogout = () => {
      localStorage.removeItem('token');
      window.location.href = '/login';
  };

  return (
    <div className="flex h-screen w-screen bg-[#05080d] text-slate-200 overflow-hidden font-sans relative">
      {/* BACKGROUND GRID EFFECT */}
      <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none" 
           style={{ backgroundImage: `radial-gradient(#475569 1px, transparent 1px)`, backgroundSize: '30px 30px' }} />

      {/* --- SIDEBAR --- */}
      <motion.aside 
        initial={{ x: -100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="w-72 bg-[#0f172a]/40 backdrop-blur-3xl border-r border-slate-800/50 flex flex-col z-50 relative"
      >
        {/* LOGO SECTION - SCROLL TO TOP LOGIC */}
        <div 
          className="p-8 border-b border-slate-800/50 flex items-center gap-3 relative group overflow-hidden cursor-pointer"
          onClick={() => {
            const mainElement = document.querySelector('main');
            if (mainElement) {
              mainElement.scrollTo({ top: 0, behavior: 'smooth' });
            }
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
            <h1 className="text-xl font-black tracking-tighter text-white uppercase italic flex items-center">
              SECURITY<span className="text-red-600 ml-0.5">.AI</span>
            </h1>
            <span className="text-[7px] font-mono text-slate-500 tracking-[0.2em] uppercase mt-1 font-bold">Neural Node V11.0</span>
          </div>
        </div>

        <nav className="flex-1 p-6 space-y-8">
          <div className="space-y-2">
            <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] px-2 mb-4 font-bold">Monitoring</p>
            
            <button 
                onClick={() => setActiveCamera('mac')}
                className={`w-full flex items-center gap-4 px-4 py-4 rounded-2xl transition-all duration-300 border ${
                    activeCamera === 'mac' 
                    ? 'bg-blue-500/10 border-blue-500/40 text-blue-400 shadow-[0_0_20px_rgba(59,130,246,0.1)]' 
                    : 'bg-transparent border-transparent text-slate-500 hover:bg-slate-800/40 hover:text-slate-300'
                }`}
            >
              <Building2 size={20} />
              <span className="text-sm font-bold tracking-tight">Салбар 1</span>
            </button>

            <button 
                onClick={() => setActiveCamera('phone')}
                className={`w-full flex items-center gap-4 px-4 py-4 rounded-2xl transition-all duration-300 border ${
                    activeCamera === 'phone' 
                    ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.1)]' 
                    : 'bg-transparent border-transparent text-slate-500 hover:bg-slate-800/40 hover:text-slate-300'
                }`}
            >
              <Building2 size={20} />
              <span className="text-sm font-bold tracking-tight">Салбар 2</span>
            </button>

            <button 
                onClick={() => setActiveCamera('axis')}
                className={`w-full flex items-center gap-4 px-4 py-4 rounded-2xl transition-all duration-300 border ${
                    activeCamera === 'axis' 
                    ? 'bg-purple-500/10 border-purple-500/40 text-purple-400 shadow-[0_0_20px_rgba(168,85,247,0.1)]' 
                    : 'bg-transparent border-transparent text-slate-500 hover:bg-slate-800/40 hover:text-slate-300'
                }`}
            >
              <Building2 size={20} />
              <span className="text-sm font-bold tracking-tight">Салбар 3</span>
            </button>
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] px-2 mb-4 font-bold">System Control</p>
            <button className="w-full flex items-center gap-4 px-4 py-3 rounded-xl text-slate-500 hover:bg-slate-800/40 transition-all font-bold">
              <Settings size={18} />
              <span className="text-sm">Settings</span>
            </button>
          </div>
        </nav>

        <div className="p-6 border-t border-slate-800/50">
          <button 
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-red-500/20 text-red-500 text-xs font-bold uppercase tracking-widest hover:bg-red-500/10 transition-all"
          >
            <LogOut size={14} /> Logout
          </button>
        </div>
      </motion.aside>

      {/* --- MAIN CONTENT --- */}
      <main className="flex-1 overflow-y-auto relative z-10 p-6 md:p-10 scrollbar-hide">
        <div className="max-w-[1600px] mx-auto w-full">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            
            {/* Left: Video & Analytics */}
            <div className="lg:col-span-8 space-y-8">
              <div className="flex justify-between items-end px-2">
                <div>
                  <h2 className="text-3xl font-black text-white uppercase tracking-tight italic">
                    {activeCamera === 'mac' ? 'Main Facility' : activeCamera === 'phone' ? 'Remote Storage' : 'Axis Camera'}
                  </h2>
                  <p className="text-xs font-mono text-blue-500/80 uppercase tracking-widest mt-1">
                    AI Neural Engine // Node_{activeCamera.toUpperCase()}
                  </p>
                </div>
                <div className="flex items-center gap-2 bg-slate-900/50 px-4 py-2 rounded-full border border-slate-800">
                    <div className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">System Online</span>
                </div>
              </div>

              {/* LIVE FEED */}
              <div className="bg-[#0f172a]/60 backdrop-blur-xl rounded-[3rem] border border-slate-800/50 overflow-hidden shadow-2xl relative ring-1 ring-white/5 bg-black">
                <div className="p-5 bg-slate-900/40 border-b border-slate-800/50 flex justify-between items-center font-mono">
                   <span className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-blue-400">
                      <Activity size={14} className="animate-pulse" /> Source: {activeCamera.toUpperCase()}_NODE
                   </span>
                   <span className="bg-red-600 text-[9px] px-3 py-1 rounded-full text-white font-bold animate-pulse uppercase">Live View</span>
                </div>
                <div className="w-full relative aspect-video flex items-center justify-center bg-slate-950">
                  <img 
                    key={activeCamera}
                    src={VIDEO_FEED_URL} 
                    className="w-full h-full object-contain" 
                    alt="AI Feed" 
                  />
                </div>
              </div>

              {/* CHARTS */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
              <div className="bg-[#0f172a]/60 backdrop-blur-xl rounded-[2.5rem] border border-slate-800/50 flex flex-col h-[calc(100vh-140px)] shadow-2xl overflow-hidden ring-1 ring-white/5">
                <div className="p-8 border-b border-slate-800 bg-slate-900/40 flex justify-between items-center">
                  <div className="flex items-center gap-3">
                    <List size={20} className="text-amber-500" />
                    <div>
                        <h2 className="text-xs font-black uppercase tracking-widest text-slate-200">Alert Logs</h2>
                        <p className="text-[10px] text-slate-500 font-mono">Count: {filteredAlerts.length}</p>
                    </div>
                  </div>
                  { (selectedDay || selectedHour !== null) && (
                    <button onClick={() => { setSelectedDay(null); setSelectedHour(null); }} 
                            className="text-[9px] uppercase font-bold text-red-400 hover:text-red-300 transition-colors">
                      Reset
                    </button>
                  )}
                </div>
                
                <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-hide">
                   <AnimatePresence mode="popLayout" initial={false}>
                      {filteredAlerts.length === 0 ? (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} className="flex flex-col items-center justify-center py-20 text-slate-500 gap-4 font-mono text-center">
                          <Clock size={32} />
                          <p className="tracking-widest uppercase text-[10px]">No logs detected in this period</p>
                        </motion.div>
                      ) : (
                        [...filteredAlerts].reverse().map((alert, index) => (
                          <motion.div key={alert.id || index} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} layout>
                            <AlertCard alert={alert} onSelect={setActiveVideo} />
                          </motion.div>
                        ))
                      )}
                   </AnimatePresence>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      <VideoModal videoUrl={activeVideo} onClose={() => setActiveVideo(null)} />
    </div>
  );
}

export default Dashboard;
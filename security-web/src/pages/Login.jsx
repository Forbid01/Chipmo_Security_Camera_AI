/* eslint-disable no-unused-vars */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api'; 
import { Lock, Mail, Loader2, ShieldCheck } from 'lucide-react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { damping: 30, stiffness: 200 };
  const smoothX = useSpring(mouseX, springConfig);
  const smoothY = useSpring(mouseY, springConfig);

  const glowX = useTransform(smoothX, [-500, 500], [-50, 50]);
  const glowY = useTransform(smoothY, [-500, 500], [-50, 50]);

  const handleMouseMove = (e) => {
    const { clientX, clientY } = e;
    const { innerWidth, innerHeight } = window;
    mouseX.set(clientX - innerWidth / 2);
    mouseY.set(clientY - innerHeight / 2);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const params = new URLSearchParams();
      params.append('username', email);
      params.append('password', password);

      const response = await api.post('/token', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      if (response.data.access_token) {
        localStorage.setItem('token', response.data.access_token);
        
        // 2. ХЭРЭГЛЭГЧИЙН МЭДЭЭЛЛИЙГ (ROLE-ТОЙ НЬ) ХАДГАЛАХ
        // FastAPI чинь токентой хамт хэрэглэгчийн мэдээллийг буцаадаг байх ёстой
        if (response.data.user) {
          localStorage.setItem('user', JSON.stringify(response.data.user));
        }

        setTimeout(() => {
          // 3. Хэрэв super_admin бол админ хуудас руу, үгүй бол dashboard руу
          if (response.data.user?.role === 'super_admin') {
            navigate('/admin/control');
          } else {
            navigate('/dashboard');
          }
          window.location.reload(); 
        }, 100);
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || "ACCESS DENIED: SYSTEM BREACH PREVENTED";
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      onMouseMove={handleMouseMove}
      className="min-h-screen flex items-center justify-center bg-[#05070a] p-6 font-sans antialiased overflow-hidden relative"
    >
      {/* 1. Background Effects Layer */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        {/* Grid Pattern */}
        <div 
          className="absolute inset-0 opacity-[0.15]" 
          style={{ 
            backgroundImage: `radial-gradient(#1e293b 1.3px, transparent 1.3px)`, 
            backgroundSize: '38px 38px' 
          }} 
        />
        
        {/* Animated Glows - Хулгана дагадаг хэсэг */}
        <motion.div 
          style={{ x: glowX, y: glowY }}
          className="absolute top-1/4 left-1/4 w-[520px] h-[600px] bg-red-700/20 rounded-full blur-[120px]"
        />
        <motion.div 
          style={{ x: useTransform(glowX, (v) => -v), y: useTransform(glowY, (v) => -v) }}
          className="absolute bottom-1/4 right-1/4 w-[520px] h-[600px] bg-blue-700/20 rounded-full blur-[120px]"
        />
      </div>

      {/* 2. Form Layer */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-[420px] z-10"
      >
        <form 
          onSubmit={handleLogin} 
          className="bg-[#0f172a]/70 backdrop-blur-2xl p-10 rounded-[2.5rem] border border-slate-800/50 shadow-[0_0_80px_-15px_rgba(0,0,0,0.6)] relative overflow-hidden"
        >
          {/* Scanline Animation */}
          <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-red-500/40 to-transparent animate-pulse" />
          <div className="text-center mb-10 group cursor-default">
  {/* LOGO AREA */}
  <div className="relative inline-flex mb-6">
    {/* Background Glow */}
    <div className="absolute inset-0 bg-red-500/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
    
    <div className="relative">
      {/* Icon Container */}
      <div className="relative p-4 bg-gradient-to-br from-slate-900 to-black rounded-2xl border border-red-500/30 group-hover:border-red-500/60 transition-all duration-500 shadow-2xl overflow-hidden">
        <ShieldCheck 
          className="text-red-500 group-hover:scale-110 group-hover:rotate-[10deg] transition-transform duration-500 relative z-10" 
          size={32} 
        />
        
        {/* Animated Scanner Line */}
        <motion.div 
          animate={{ y: [-40, 60] }} 
          transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }} 
          className="absolute left-0 w-full h-[1.5px] bg-red-400/50 shadow-[0_0_12px_red] z-0" 
        />
      </div>

      {/* Online/Blinking Status Point */}
      <div className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-red-600 rounded-full border-[3px] border-[#0f172a] z-20 shadow-lg">
        <div className="absolute inset-0 bg-red-400 rounded-full animate-ping opacity-75" />
      </div>
    </div>
  </div>

  {/* TEXT AREA */}
  <div className="flex flex-col items-center leading-none">
    <h1 className="text-3xl font-black tracking-tighter text-white uppercase italic flex items-center">
      SECURITY<span className="text-red-600 ml-1">.AI</span>
    </h1>
    <div className="flex items-center gap-2 mt-3">
      <div className="h-[1px] w-4 bg-slate-800" />
      <span className="text-[9px] font-mono text-slate-500 tracking-[0.4em] uppercase font-bold">
        Access Control V11.0
      </span>
      <div className="h-[1px] w-4 bg-slate-800" />
    </div>
  </div>
</div>

          {error && (
            <motion.div 
              initial={{ x: -10 }} 
              animate={{ x: 0 }}
              className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-500 text-[10px] font-mono text-center uppercase tracking-wider"
            >
              {error}
            </motion.div>
          )}

          <div className="space-y-4">
            <div className="group relative">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-600 group-focus-within:text-red-500/70 transition-colors" size={18} />
              <input 
                type="email" 
                required
                placeholder="Email Address" 
                className="w-full bg-slate-950/60 border border-slate-800 p-4 pl-12 rounded-2xl text-white text-sm focus:outline-none focus:border-red-500/40 focus:ring-4 focus:ring-red-500/5 transition-all placeholder:text-slate-700"
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="group relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-600 group-focus-within:text-red-500/70 transition-colors" size={18} />
              <input 
                type="password" 
                required
                placeholder="Password" 
                className="w-full bg-slate-950/60 border border-slate-800 p-4 pl-12 rounded-2xl text-white text-sm focus:outline-none focus:border-red-500/40 focus:ring-4 focus:ring-red-500/5 transition-all placeholder:text-slate-700"
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="flex justify-end mt-2 px-1">
              <button
                type="button"
                onClick={() => navigate('/forgot-password')}
                className="text-[10px] font-mono uppercase tracking-widest text-slate-500 hover:text-red-500 transition-colors"
              >
                Forgot Password?
              </button>
            </div>
          </div>

          <button 
            disabled={loading}
            className="w-full bg-red-600 mt-8 py-4 rounded-2xl font-black text-white uppercase tracking-[0.2em] text-xs hover:bg-red-500 active:scale-[0.97] transition-all duration-300 shadow-xl shadow-red-900/30 disabled:opacity-50 flex items-center justify-center gap-3"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : "Login"}
          </button>

          <div className="flex flex-col items-center justify-center mt-10">
            <div className="flex items-center gap-3 bg-slate-950/80 px-5 py-2.5 rounded-full border border-slate-800/80 hover:border-slate-700 transition-colors cursor-default">
              <span className="text-slate-500 text-[10px] uppercase tracking-widest font-bold">New User?</span>
              <button
                type="button"
                onClick={() => navigate('/register')}
                className="text-red-500 hover:text-red-400 font-black text-[10px] uppercase tracking-[0.15em] transition-all"
              >
                Create Account
              </button>
            </div>
          </div>

          <p className="text-center mt-8 text-[9px] text-slate-700 font-mono uppercase tracking-[0.4em] opacity-40">
            System Identity: SEC-CAM-MAC-V1
          </p>
        </form>
      </motion.div>
    </div>
  );
}
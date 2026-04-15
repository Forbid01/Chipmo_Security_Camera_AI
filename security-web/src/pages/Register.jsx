/* eslint-disable no-unused-vars */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api'; 
import { Lock, Mail, User, Phone, Loader2, ArrowLeft, UserPlus, Building2 } from 'lucide-react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';

export default function Register() {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    phone_number: '',
    password: '',
    full_name: '',
    org_name: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { damping: 30, stiffness: 200 };
  const smoothX = useSpring(mouseX, springConfig);
  const smoothY = useSpring(mouseY, springConfig);

  const glowX = useTransform(smoothX, [-500, 500], [-60, 60]);
  const glowY = useTransform(smoothY, [-500, 500], [-60, 60]);

  const handleMouseMove = (e) => {
    const { clientX, clientY } = e;
    const { innerWidth, innerHeight } = window;
    mouseX.set(clientX - innerWidth / 2);
    mouseY.set(clientY - innerHeight / 2);
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await api.post('/register', formData);
      if (response.data.user_id || response.data.message) {
        alert("Бүртгэл амжилттай! Одоо нэвтэрнэ үү.");
        navigate('/login');
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      let errorMsg = "REGISTRATION FAILED: VALIDATION ERROR";
      if (typeof detail === 'string') {
        errorMsg = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMsg = detail.map(d => d.msg || d.message || '').filter(Boolean).join('; ');
      }
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
      {/* 1. Ultra-Clear Background Layer */}
      <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
        {/* Grid Pattern */}
        <div 
          className="absolute inset-0 opacity-[0.2]" 
          style={{ 
            backgroundImage: `radial-gradient(#475569 1.5px, transparent 1.5px)`, 
            backgroundSize: '40px 40px' 
          }} 
        />
        
        {/* Blue Glow - Цэнхэр өнгө нь Бүртгүүлэх хэсэгт илүү зохимжтой */}
        <motion.div 
          style={{ x: glowX, y: glowY }}
          className="absolute top-[-10%] right-[-10%] w-[600px] h-[600px] bg-blue-500/30 rounded-full blur-[80px] mix-blend-screen animate-pulse"
        />

        {/* Indigo/Slate Glow */}
        <motion.div 
          style={{ x: useTransform(glowX, (v) => -v), y: useTransform(glowY, (v) => -v) }}
          className="absolute bottom-[-10%] left-[-10%] w-[600px] h-[600px] bg-indigo-500/20 rounded-full blur-[90px] mix-blend-screen"
        />
      </div>

      {/* 2. Register Form Layer */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-[440px] z-10"
      >
        <form 
          onSubmit={handleRegister} 
          className="bg-[#0f172a]/70 backdrop-blur-2xl p-10 rounded-[2.5rem] border border-slate-800/50 shadow-[0_0_80px_-15px_rgba(0,0,0,0.6)] relative overflow-hidden"
        >
          {/* Top Scan Line (Blue) */}
          <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-blue-500/40 to-transparent animate-pulse" />
          
          <button 
            type="button"
            onClick={() => navigate('/login')}
            className="absolute top-8 left-8 text-slate-500 hover:text-white transition-all hover:-translate-x-1"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="text-center mb-8 group cursor-default">
  {/* LOGO AREA - BLUE VERSION */}
  <div className="relative inline-flex mb-6">
    {/* Background Blue Glow */}
    <div className="absolute inset-0 bg-blue-500/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
    
    <div className="relative">
      {/* Icon Container */}
      <div className="relative p-4 bg-gradient-to-br from-slate-900 to-black rounded-2xl border border-blue-500/30 group-hover:border-blue-500/60 transition-all duration-500 shadow-2xl overflow-hidden">
        <UserPlus 
          className="text-blue-500 group-hover:scale-110 group-hover:rotate-[-5deg] transition-transform duration-500 relative z-10" 
          size={32} 
        />
        
        {/* Animated Scanner Line (Blue) */}
        <motion.div 
          animate={{ y: [-40, 60] }} 
          transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }} 
          className="absolute left-0 w-full h-[1.5px] bg-blue-400/50 shadow-[0_0_12px_#3b82f6] z-0" 
        />
      </div>

      {/* Online/Active Status Point (Cyan/Blue) */}
      <div className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-blue-600 rounded-full border-[3px] border-[#0f172a] z-20 shadow-lg">
        <div className="absolute inset-0 bg-cyan-400 rounded-full animate-ping opacity-75" />
      </div>
    </div>
  </div>

  {/* TEXT AREA */}
  <div className="flex flex-col items-center leading-none">
    <h1 className="text-3xl font-black tracking-tighter text-white uppercase italic flex items-center">
      CREATE<span className="text-blue-600 ml-1">ACCOUNT</span>
    </h1>
    <div className="flex items-center gap-2 mt-3">
      <div className="h-[1px] w-4 bg-slate-800" />
      <span className="text-[9px] font-mono text-slate-500 tracking-[0.4em] uppercase font-bold">
        Identity Protocol V11.0
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

          <div className="space-y-3">
            {[
              { name: 'full_name', placeholder: 'Бүтэн нэр', icon: User, type: 'text' },
              { name: 'username', placeholder: 'Хэрэглэгчийн нэр', icon: User, type: 'text', required: true },
              { name: 'email', placeholder: 'Имэйл хаяг', icon: Mail, type: 'email', required: true },
              { name: 'phone_number', placeholder: 'Утасны дугаар', icon: Phone, type: 'text' },
              { name: 'org_name', placeholder: 'Байгууллагын нэр', icon: Building2, type: 'text', required: true },
              { name: 'password', placeholder: 'Нууц үг', icon: Lock, type: 'password', required: true },
            ].map((field) => (
              <div key={field.name} className="group relative">
                <field.icon className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-600 group-focus-within:text-blue-500/70 transition-colors" size={16} />
                <input 
                  name={field.name}
                  type={field.type}
                  required={field.required}
                  placeholder={field.placeholder} 
                  className="w-full bg-slate-950/60 border border-slate-800 p-3.5 pl-11 rounded-2xl text-white text-sm focus:outline-none focus:border-blue-500/40 focus:ring-4 focus:ring-blue-500/5 transition-all placeholder:text-slate-700"
                  onChange={handleChange}
                />
              </div>
            ))}
          </div>

          <button 
            disabled={loading}
            className="w-full bg-blue-600 mt-8 py-4 rounded-2xl font-black text-white uppercase tracking-[0.2em] text-xs hover:bg-blue-500 active:scale-[0.97] transition-all duration-300 shadow-xl shadow-blue-900/30 disabled:opacity-50 flex items-center justify-center gap-3"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : "Бүртгүүлэх"}
          </button>

          <div className="flex flex-col items-center justify-center mt-8">
            <div className="flex items-center gap-3 bg-slate-950/80 px-5 py-2.5 rounded-full border border-slate-800/80 hover:border-slate-700 transition-colors cursor-default">
              <span className="text-slate-500 text-[10px] uppercase tracking-widest font-bold">
                Бүртгэлтэй юу?
              </span>
              <button
                type="button"
                onClick={() => navigate('/login')}
                className="text-blue-500 hover:text-blue-400 font-black text-[10px] uppercase tracking-[0.15em] transition-all hover:translate-x-0.5"
              >
                Нэвтрэх
              </button>
            </div>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
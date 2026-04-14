/* eslint-disable no-unused-vars */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { forgotPassword, verifyCode, resetPassword } from '../services/api'; 
import { Lock, Mail, Loader2, ShieldCheck, ArrowLeft, KeyRound } from 'lucide-react';
import { motion } from 'framer-motion';

export default function ForgotPassword() {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  // 1. Имэйл илгээх
  const handleSendEmail = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await forgotPassword(email);
      setStep(2);
    } catch (err) {
      setError(err.detail || "Имэйл илгээхэд алдаа гарлаа.");
    } finally {
      setLoading(false);
    }
  };

  // 2. Код баталгаажуулах
  const handleVerifyCode = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await verifyCode(email, code);
      setStep(3);
    } catch (err) {
      setError(err.detail || "Код буруу эсвэл хугацаа нь дууссан байна.");
    } finally {
      setLoading(false);
    }
  };

  // 3. Шинэ нууц үг хадгалах
  const handleReset = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await resetPassword(email, code, newPassword);
      alert("Нууц үг амжилттай шинэчлэгдлээ!");
      navigate('/login');
    } catch (err) {
      setError(err.detail || "Нууц үг шинэчлэхэд алдаа гарлаа.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070a] p-6 font-sans antialiased overflow-hidden relative">
      {/* Background Effects (Login-той ижил) */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 opacity-[0.15]" style={{ backgroundImage: `radial-gradient(#1e293b 1.3px, transparent 1.3px)`, backgroundSize: '38px 38px' }} />
        <div className="absolute top-1/4 left-1/4 w-[520px] h-[600px] bg-blue-700/10 rounded-full blur-[120px]" />
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-[420px] z-10">
        <div className="bg-[#0f172a]/70 backdrop-blur-2xl p-10 rounded-[2.5rem] border border-slate-800/50 shadow-2xl relative">
          
          <button onClick={() => navigate('/login')} className="absolute top-8 left-8 text-slate-500 hover:text-white transition-colors">
            <ArrowLeft size={20} />
          </button>

          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 mb-6">
               <KeyRound className="text-red-500" size={28} />
            </div>
            <h2 className="text-2xl font-black text-white italic uppercase tracking-tighter">
              {step === 1 ? "Нууц үг сэргээх" : step === 2 ? "Код баталгаажуулах" : "Шинэ нууц үг"}
            </h2>
          </div>

          {error && (
            <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-500 text-[10px] font-mono text-center uppercase">
              {error}
            </div>
          )}

          {/* АЛХАМ 1: ИМЭЙЛ ОРУУЛАХ */}
          {step === 1 && (
            <form onSubmit={handleSendEmail} className="space-y-4">
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-600" size={18} />
                <input 
                  type="email" required placeholder="Бүртгэлтэй имэйл хаяг" 
                  className="w-full bg-slate-950/60 border border-slate-800 p-4 pl-12 rounded-2xl text-white text-sm focus:border-red-500/40 outline-none transition-all"
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <button disabled={loading} className="w-full bg-red-600 py-4 rounded-2xl font-black text-white uppercase tracking-widest text-xs hover:bg-red-500 transition-all flex items-center justify-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={18} /> : "Код авах"}
              </button>
            </form>
          )}

          {/* АЛХАМ 2: КОД ОРУУЛАХ */}
          {step === 2 && (
            <form onSubmit={handleVerifyCode} className="space-y-4">
              <div className="relative">
                <ShieldCheck className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-600" size={18} />
                <input 
                  type="text" required placeholder="6 оронтой код" maxLength={6}
                  className="w-full bg-slate-950/60 border border-slate-800 p-4 pl-12 rounded-2xl text-white text-sm focus:border-red-500/40 outline-none transition-all tracking-[0.5em] font-bold"
                  onChange={(e) => setCode(e.target.value)}
                />
              </div>
              <button disabled={loading} className="w-full bg-red-600 py-4 rounded-2xl font-black text-white uppercase tracking-widest text-xs hover:bg-red-500 transition-all flex items-center justify-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={18} /> : "Баталгаажуулах"}
              </button>
            </form>
          )}

          {/* АЛХАМ 3: ШИНЭ НУУЦ ҮГ ОРУУЛАХ */}
          {step === 3 && (
            <form onSubmit={handleReset} className="space-y-4">
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-600" size={18} />
                <input 
                  type="password" required placeholder="Шинэ нууц үг" 
                  className="w-full bg-slate-950/60 border border-slate-800 p-4 pl-12 rounded-2xl text-white text-sm focus:border-red-500/40 outline-none transition-all"
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <button disabled={loading} className="w-full bg-red-600 py-4 rounded-2xl font-black text-white uppercase tracking-widest text-xs hover:bg-red-500 transition-all flex items-center justify-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={18} /> : "Нууц үг шинэчлэх"}
              </button>
            </form>
          )}

        </div>
      </motion.div>
    </div>
  );
}
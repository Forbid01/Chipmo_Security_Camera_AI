import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, User, Building2, Mail, Shield, Save } from 'lucide-react';
import { motion } from 'framer-motion';
import { getUserProfile } from '../services/api';

function Settings() {
  const navigate = useNavigate();
  const [userInfo, setUserInfo] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getUserProfile()
      .then(data => {
        setUserInfo(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 font-sans relative">
      {/* BACKGROUND GRID */}
      <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none"
           style={{ backgroundImage: `radial-gradient(#475569 1px, transparent 1px)`, backgroundSize: '30px 30px' }} />

      <div className="relative z-10 max-w-2xl mx-auto px-6 py-10">
        {/* HEADER */}
        <div className="flex items-center gap-4 mb-10">
          <button
            onClick={() => navigate('/dashboard')}
            className="p-2.5 rounded-xl border border-slate-800 hover:bg-slate-800/50 transition-all"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-2xl font-black uppercase tracking-tight text-white">Settings</h1>
            <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mt-0.5">Account & Profile</p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* PROFILE CARD */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-[#0f172a]/60 backdrop-blur-xl rounded-3xl border border-slate-800/50 overflow-hidden"
            >
              <div className="p-6 border-b border-slate-800/50 bg-slate-900/40">
                <h2 className="text-xs font-black uppercase tracking-widest text-slate-300 flex items-center gap-2">
                  <User size={14} className="text-blue-400" /> Profile
                </h2>
              </div>
              <div className="p-6 space-y-5">
                <InfoRow icon={<User size={16} />} label="Хэрэглэгчийн нэр" value={userInfo.username} />
                <InfoRow icon={<User size={16} />} label="Бүтэн нэр" value={userInfo.full_name || '---'} />
                <InfoRow icon={<Mail size={16} />} label="Имэйл" value={userInfo.email} />
              </div>
            </motion.div>

            {/* ORG CARD */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="bg-[#0f172a]/60 backdrop-blur-xl rounded-3xl border border-slate-800/50 overflow-hidden"
            >
              <div className="p-6 border-b border-slate-800/50 bg-slate-900/40">
                <h2 className="text-xs font-black uppercase tracking-widest text-slate-300 flex items-center gap-2">
                  <Building2 size={14} className="text-emerald-400" /> Organization
                </h2>
              </div>
              <div className="p-6 space-y-5">
                <InfoRow icon={<Building2 size={16} />} label="Байгууллагын нэр" value={userInfo.org_name || 'Тодорхойгүй'} />
                <InfoRow icon={<Shield size={16} />} label="Эрх" value={userInfo.role === 'super_admin' ? 'Super Admin' : 'User'} />
              </div>
            </motion.div>

            {/* ACTIONS */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="flex gap-4"
            >
              <button
                onClick={() => {
                  localStorage.removeItem('token');
                  localStorage.removeItem('user');
                  navigate('/login');
                }}
                className="flex-1 py-3.5 rounded-2xl border border-red-500/30 text-red-400 text-xs font-bold uppercase tracking-widest hover:bg-red-500/10 transition-all"
              >
                Logout
              </button>
              <button
                onClick={() => navigate('/forgot-password')}
                className="flex-1 py-3.5 rounded-2xl border border-slate-700 text-slate-400 text-xs font-bold uppercase tracking-widest hover:bg-slate-800/50 transition-all"
              >
                Change Password
              </button>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  );
}

function InfoRow({ icon, label, value }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-slate-500">
        {icon}
        <span className="text-xs font-bold uppercase tracking-wider">{label}</span>
      </div>
      <span className="text-sm font-mono text-white">{value || '---'}</span>
    </div>
  );
}

export default Settings;

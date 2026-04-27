/* eslint-disable no-unused-vars */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, User, Building2, Mail, Shield, Send,
  MessageCircle, Store, Check, X, Loader2, Trash2, Brain
} from 'lucide-react';
import { motion } from 'framer-motion';
import {
  getUserProfile, getMyStores, testTelegram, removeTelegram,
  getStoreSettings, patchStoreSettings,
} from '../services/api';
import RagVlmSettings from '../components/Settings/RagVlmSettings';

function Settings() {
  const navigate = useNavigate();
  const [userInfo, setUserInfo] = useState({});
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);

  // Telegram state
  const [telegramInputs, setTelegramInputs] = useState({});
  const [testingStore, setTestingStore] = useState(null);
  const [testResult, setTestResult] = useState({});

  // RAG / VLM per-store settings. We lazy-load when the user expands a
  // store row to avoid N parallel /settings calls on mount for tenants
  // with many stores.
  const [aiSettings, setAiSettings] = useState({}); // { storeId: settings }
  const [aiSavingStore, setAiSavingStore] = useState(null);
  const [expandedAiStore, setExpandedAiStore] = useState(null);

  const loadAiSettings = async (storeId) => {
    if (aiSettings[storeId]) return;
    try {
      const s = await getStoreSettings(storeId);
      setAiSettings(prev => ({ ...prev, [storeId]: s }));
    } catch (err) {
      console.warn('store_settings_load_error', err);
    }
  };

  const handleSaveAiSettings = async (storeId, patch) => {
    setAiSavingStore(storeId);
    try {
      const updated = await patchStoreSettings(storeId, patch);
      setAiSettings(prev => ({ ...prev, [storeId]: updated }));
    } finally {
      setAiSavingStore(null);
    }
  };

  useEffect(() => {
    Promise.all([getUserProfile(), getMyStores()])
      .then(([profile, storesData]) => {
        setUserInfo(profile);
        const storesList = Array.isArray(storesData) ? storesData : [];
        setStores(storesList);
        // Initialize inputs with existing chat_ids
        const inputs = {};
        storesList.forEach(s => {
          inputs[s.id] = s.telegram_chat_id || '';
        });
        setTelegramInputs(inputs);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleTestTelegram = async (storeId) => {
    const chatId = telegramInputs[storeId]?.trim();
    if (!chatId) return;

    setTestingStore(storeId);
    setTestResult({});
    try {
      await testTelegram(storeId, chatId);
      setTestResult({ [storeId]: 'success' });
      // Update store in list
      setStores(prev => prev.map(s =>
        s.id === storeId ? { ...s, telegram_chat_id: chatId } : s
      ));
    } catch (err) {
      setTestResult({ [storeId]: err.response?.data?.detail || 'Алдаа гарлаа' });
    } finally {
      setTestingStore(null);
    }
  };

  const handleRemoveTelegram = async (storeId) => {
    try {
      await removeTelegram(storeId);
      setTelegramInputs(prev => ({ ...prev, [storeId]: '' }));
      setStores(prev => prev.map(s =>
        s.id === storeId ? { ...s, telegram_chat_id: null } : s
      ));
      setTestResult({ [storeId]: 'removed' });
    } catch (err) {
      alert(err.response?.data?.detail || 'Алдаа');
    }
  };

  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 font-sans relative">
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
            <h1 className="text-2xl font-black uppercase tracking-tight text-white">Тохиргоо</h1>
            <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mt-0.5">Профайл & Мэдэгдэл</p>
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
                  <User size={14} className="text-blue-400" /> Профайл
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
                  <Building2 size={14} className="text-emerald-400" /> Байгууллага
                </h2>
              </div>
              <div className="p-6 space-y-5">
                <InfoRow icon={<Building2 size={16} />} label="Байгууллагын нэр" value={userInfo.org_name || 'Тодорхойгүй'} />
                <InfoRow icon={<Shield size={16} />} label="Эрх" value={userInfo.role === 'super_admin' ? 'Super Admin' : 'User'} />
              </div>
            </motion.div>

            {/* TELEGRAM CARD */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="bg-[#0f172a]/60 backdrop-blur-xl rounded-3xl border border-slate-800/50 overflow-hidden"
            >
              <div className="p-6 border-b border-slate-800/50 bg-slate-900/40">
                <h2 className="text-xs font-black uppercase tracking-widest text-slate-300 flex items-center gap-2">
                  <MessageCircle size={14} className="text-sky-400" /> Telegram мэдэгдэл
                </h2>
              </div>
              <div className="p-6 space-y-5">
                <div className="bg-sky-500/5 border border-sky-500/20 rounded-xl p-4">
                  <p className="text-xs text-sky-300/80 leading-relaxed">
                    Сэжигтэй үйлдэл илэрмэгц таны Telegram руу зурагтай мэдэгдэл шууд ирнэ.
                  </p>
                  <p className="text-[10px] text-slate-500 mt-2">
                    Хэрхэн Chat ID олох: <span className="text-sky-400">@userinfobot</span> руу Telegram дээр бичвэл таны Chat ID-г хэлнэ.
                    Групп чатны хувьд ботыг группт нэмээд <span className="text-sky-400">@raw_data_bot</span> ашиглана.
                  </p>
                </div>

                {stores.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-4">
                    Дэлгүүр бүртгэлгүй байна
                  </p>
                ) : (
                  <div className="space-y-4">
                    {stores.map(store => (
                      <div key={store.id} className="p-4 rounded-xl border border-slate-800/50 bg-slate-900/30 space-y-3">
                        <div className="flex items-center gap-2">
                          <Store size={14} className="text-slate-500" />
                          <span className="text-sm font-bold text-white">{store.name}</span>
                          {store.telegram_chat_id && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-bold uppercase">
                              Холбогдсон
                            </span>
                          )}
                        </div>

                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={telegramInputs[store.id] || ''}
                            onChange={(e) => setTelegramInputs(prev => ({ ...prev, [store.id]: e.target.value }))}
                            placeholder="Telegram Chat ID оруулах..."
                            className="flex-1 px-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm font-mono focus:border-sky-500 focus:outline-none transition-colors"
                          />
                          <button
                            onClick={() => handleTestTelegram(store.id)}
                            disabled={testingStore === store.id || !telegramInputs[store.id]?.trim()}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 text-white text-xs font-bold uppercase hover:bg-sky-500 transition-all disabled:opacity-40"
                          >
                            {testingStore === store.id ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Send size={14} />
                            )}
                            Тест
                          </button>
                          {store.telegram_chat_id && (
                            <button
                              onClick={() => handleRemoveTelegram(store.id)}
                              className="p-2.5 rounded-xl border border-slate-700/50 text-slate-500 hover:text-red-400 hover:border-red-500/30 transition-all"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>

                        {/* Result message */}
                        {testResult[store.id] === 'success' && (
                          <p className="text-xs text-emerald-400 flex items-center gap-1">
                            <Check size={12} /> Telegram руу мэдэгдэл амжилттай илгээгдлээ!
                          </p>
                        )}
                        {testResult[store.id] === 'removed' && (
                          <p className="text-xs text-slate-400 flex items-center gap-1">
                            <X size={12} /> Telegram мэдэгдэл унтраагдлаа
                          </p>
                        )}
                        {testResult[store.id] && testResult[store.id] !== 'success' && testResult[store.id] !== 'removed' && (
                          <p className="text-xs text-red-400 flex items-center gap-1">
                            <X size={12} /> {testResult[store.id]}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>

            {/* AI (RAG + VLM) per-store settings */}
            {stores.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.18 }}
                className="bg-[#0f172a]/60 backdrop-blur-xl rounded-3xl border border-slate-800/50 overflow-hidden"
              >
                <div className="p-6 border-b border-slate-800/50 bg-slate-900/40">
                  <h2 className="text-xs font-black uppercase tracking-widest text-slate-300 flex items-center gap-2">
                    <Brain size={14} className="text-indigo-400" /> AI шалгуур (RAG + VLM)
                  </h2>
                </div>
                <div className="p-6 space-y-4">
                  <p className="text-xs text-slate-400">
                    Хуурамч анхааруулгыг RAG (мэдэгдсэн FP-н текст хайлт) болон Qwen2.5-VL
                    (зураг ойлгох model) ашиглан шүүж байна. Тус бүр дэлгүүр өөрийн босготой.
                  </p>
                  {stores.map(store => {
                    const expanded = expandedAiStore === store.id;
                    const cfg = aiSettings[store.id];
                    return (
                      <div key={store.id} className="rounded-xl border border-slate-800/50 bg-slate-900/30">
                        <button
                          type="button"
                          onClick={() => {
                            const next = expanded ? null : store.id;
                            setExpandedAiStore(next);
                            if (next) loadAiSettings(next);
                          }}
                          className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-800/30 transition-colors"
                        >
                          <span className="flex items-center gap-2 text-sm font-bold text-white">
                            <Store size={14} className="text-slate-500" />
                            {store.name}
                          </span>
                          <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                            {expanded ? 'Хаах' : 'Засах'}
                          </span>
                        </button>
                        {expanded && (
                          <div className="px-4 pb-4">
                            {!cfg ? (
                              <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
                                <Loader2 size={14} className="animate-spin mr-2" /> Ачаалж байна…
                              </div>
                            ) : (
                              <RagVlmSettings
                                initialValue={cfg}
                                saving={aiSavingStore === store.id}
                                onSave={(patch) => handleSaveAiSettings(store.id, patch)}
                              />
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}

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
                Гарах
              </button>
              <button
                onClick={() => navigate('/forgot-password')}
                className="flex-1 py-3.5 rounded-2xl border border-slate-700 text-slate-400 text-xs font-bold uppercase tracking-widest hover:bg-slate-800/50 transition-all"
              >
                Нууц үг солих
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

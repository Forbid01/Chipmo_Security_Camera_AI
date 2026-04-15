/* eslint-disable no-unused-vars */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Store, Plus, Trash2, Edit3, Check, X,
  Loader2, MapPin, MessageCircle
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getMyStores, createStore, updateStore, deleteStore } from '../services/api';

function MyStores() {
  const navigate = useNavigate();
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const [form, setForm] = useState({ name: '', address: '' });

  const loadData = async () => {
    try {
      const data = await getMyStores();
      setStores(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Load error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const resetForm = () => {
    setForm({ name: '', address: '' });
    setShowForm(false);
    setEditingId(null);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        await updateStore(editingId, form);
      } else {
        await createStore(form);
      }
      resetForm();
      await loadData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Алдаа гарлаа');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (store) => {
    setForm({ name: store.name, address: store.address || '' });
    setEditingId(store.id);
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    try {
      await deleteStore(id);
      setDeleteConfirm(null);
      await loadData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Устгахад алдаа гарлаа');
    }
  };

  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 font-sans relative">
      <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none"
           style={{ backgroundImage: `radial-gradient(#475569 1px, transparent 1px)`, backgroundSize: '30px 30px' }} />

      <div className="relative z-10 max-w-3xl mx-auto px-6 py-10">
        {/* HEADER */}
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-2.5 rounded-xl border border-slate-800 hover:bg-slate-800/50 transition-all"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-2xl font-black uppercase tracking-tight text-white">Дэлгүүрүүд</h1>
              <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mt-0.5">Салбар удирдлага</p>
            </div>
          </div>
          <button
            onClick={() => { resetForm(); setShowForm(true); }}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-bold uppercase hover:bg-blue-500 transition-all"
          >
            <Plus size={14} /> Нэмэх
          </button>
        </div>

        {/* ADD/EDIT FORM */}
        <AnimatePresence>
          {showForm && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-8 overflow-hidden"
            >
              <div className="bg-[#0f172a]/60 backdrop-blur-xl rounded-2xl border border-slate-800/50 p-6 space-y-4">
                <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">
                  {editingId ? 'Дэлгүүр засах' : 'Шинэ дэлгүүр нэмэх'}
                </h3>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Дэлгүүрийн нэр *"
                  className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm focus:border-blue-500 focus:outline-none transition-colors"
                />
                <input
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                  placeholder="Хаяг (заавал биш)"
                  className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm focus:border-blue-500 focus:outline-none transition-colors"
                />
                <div className="flex gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving || !form.name.trim()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold uppercase hover:bg-emerald-500 transition-all disabled:opacity-40"
                  >
                    {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                    Хадгалах
                  </button>
                  <button
                    onClick={resetForm}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl border border-slate-700 text-slate-400 text-xs font-bold uppercase hover:bg-slate-800/50 transition-all"
                  >
                    <X size={14} /> Болих
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* STORES LIST */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : stores.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-600 gap-4">
            <Store size={48} />
            <p className="text-sm font-mono uppercase tracking-widest">Дэлгүүр бүртгэлгүй байна</p>
            <p className="text-xs text-slate-700">Эхлээд дэлгүүрээ нэмнэ үү</p>
          </div>
        ) : (
          <div className="space-y-4">
            {stores.map((store, idx) => (
              <motion.div
                key={store.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="bg-[#0f172a]/60 backdrop-blur-xl rounded-2xl border border-slate-800/50 p-5 hover:border-slate-700/50 transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20">
                      <Store size={20} className="text-blue-400" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-white">{store.name}</h3>
                      <div className="flex items-center gap-3 mt-1">
                        {store.address && (
                          <span className="text-[10px] text-slate-500 flex items-center gap-1">
                            <MapPin size={10} /> {store.address}
                          </span>
                        )}
                        <span className="text-[10px] text-slate-600 font-mono">
                          {store.camera_count || 0} камер
                        </span>
                        {store.telegram_chat_id && (
                          <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                            <MessageCircle size={10} /> Telegram
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleEdit(store)}
                      className="p-2 rounded-lg border border-slate-800 text-slate-500 hover:text-blue-400 hover:border-blue-500/30 transition-all"
                    >
                      <Edit3 size={14} />
                    </button>

                    {deleteConfirm === store.id ? (
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleDelete(store.id)}
                          className="p-2 rounded-lg bg-red-600 text-white text-xs font-bold"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="p-2 rounded-lg border border-slate-700 text-slate-400"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDeleteConfirm(store.id)}
                        className="p-2 rounded-lg border border-slate-800 text-slate-500 hover:text-red-400 hover:border-red-500/30 transition-all"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default MyStores;

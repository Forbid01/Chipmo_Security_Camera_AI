/* eslint-disable no-unused-vars */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Camera, Plus, Trash2, Edit3, Check, X,
  Wifi, WifiOff, Video, Store, Loader2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getMyCameras, getMyStores, addMyCamera, updateMyCamera, deleteMyCamera } from '../services/api';

const CAMERA_TYPES = [
  { value: 'rtsp', label: 'RTSP камер' },
  { value: 'mjpeg', label: 'MJPEG / IP камер' },
  { value: 'usb', label: 'USB / Webcam' },
  { value: 'axis', label: 'Axis камер' },
];

function MyCameras() {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState([]);
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const [form, setForm] = useState({
    name: '', url: '', camera_type: 'rtsp', store_id: '', is_ai_enabled: true, substream_url: '',
  });

  const loadData = async () => {
    try {
      const [camsData, storesData] = await Promise.all([getMyCameras(), getMyStores()]);
      setCameras(Array.isArray(camsData) ? camsData : []);
      setStores(Array.isArray(storesData) ? storesData : []);
    } catch (err) {
      console.error('Load error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const resetForm = () => {
    setForm({ name: '', url: '', camera_type: 'rtsp', store_id: '', is_ai_enabled: true, substream_url: '' });
    setShowForm(false);
    setEditingId(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.url || !form.store_id) return;
    setSaving(true);

    try {
      const payload = {
        ...form,
        store_id: parseInt(form.store_id),
        substream_url: form.substream_url?.trim() || null,
      };
      if (editingId) {
        await updateMyCamera(editingId, payload);
      } else {
        await addMyCamera(payload);
      }
      resetForm();
      await loadData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Алдаа гарлаа');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (cam) => {
    setForm({
      name: cam.name,
      url: cam.url,
      camera_type: cam.camera_type || 'rtsp',
      store_id: String(cam.store_id || ''),
      is_ai_enabled: cam.is_ai_enabled !== false,
      substream_url: cam.substream_url || '',
    });
    setEditingId(cam.id);
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    try {
      await deleteMyCamera(id);
      setDeleteConfirm(null);
      await loadData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Устгах боломжгүй');
    }
  };

  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 font-sans relative">
      <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none"
           style={{ backgroundImage: 'radial-gradient(#475569 1px, transparent 1px)', backgroundSize: '30px 30px' }} />

      <div className="relative z-10 max-w-4xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-2.5 rounded-xl border border-slate-800 hover:bg-slate-800/50 transition-all"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-2xl font-black uppercase tracking-tight text-white">Камерууд</h1>
              <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mt-0.5">
                {cameras.length} камер бүртгэлтэй
              </p>
            </div>
          </div>

          <button
            onClick={() => { resetForm(); setShowForm(!showForm); }}
            className="flex items-center gap-2 px-5 py-3 rounded-2xl bg-red-600 text-white text-xs font-bold uppercase tracking-wider hover:bg-red-500 transition-all"
          >
            <Plus size={16} />
            Камер нэмэх
          </button>
        </div>

        {/* Add/Edit Form */}
        <AnimatePresence>
          {showForm && (
            <motion.form
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              onSubmit={handleSubmit}
              className="mb-8 bg-[#0f172a]/60 backdrop-blur-xl rounded-3xl border border-slate-800/50 overflow-hidden"
            >
              <div className="p-6 border-b border-slate-800/50 bg-slate-900/40 flex justify-between items-center">
                <h2 className="text-xs font-black uppercase tracking-widest text-slate-300 flex items-center gap-2">
                  <Camera size={14} className="text-blue-400" />
                  {editingId ? 'Камер засах' : 'Шинэ камер нэмэх'}
                </h2>
                <button type="button" onClick={resetForm} className="text-slate-500 hover:text-white">
                  <X size={16} />
                </button>
              </div>

              <div className="p-6 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* Name */}
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Камерын нэр</label>
                    <input
                      type="text"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      placeholder="Жишээ: Кассын камер"
                      required
                      className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm focus:border-blue-500 focus:outline-none transition-colors"
                    />
                  </div>

                  {/* Store */}
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Дэлгүүр</label>
                    <select
                      value={form.store_id}
                      onChange={(e) => setForm({ ...form, store_id: e.target.value })}
                      required
                      className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm focus:border-blue-500 focus:outline-none transition-colors"
                    >
                      <option value="">Дэлгүүр сонгох...</option>
                      {stores.map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Primary URL */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                    Камерын URL / Address
                    <span className="ml-1.5 text-slate-600 normal-case tracking-normal font-normal">(дэлгэц + AI)</span>
                  </label>
                  <input
                    type="text"
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    placeholder="rtsp://192.168.1.100:554/stream1 эсвэл http://... эсвэл 0 (USB)"
                    required
                    className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm font-mono focus:border-blue-500 focus:outline-none transition-colors"
                  />
                </div>

                {/* Sub-stream URL */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                    Sub-stream URL
                    <span className="ml-1.5 text-slate-600 normal-case tracking-normal font-normal">
                      (заавал биш — зөвхөн AI-д бага нягтаршилтай stream)
                    </span>
                  </label>
                  <input
                    type="text"
                    value={form.substream_url}
                    onChange={(e) => setForm({ ...form, substream_url: e.target.value })}
                    placeholder="rtsp://192.168.1.100:554/stream2  — хоосон бол primary stream ашиглана"
                    className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm font-mono placeholder:text-slate-700 focus:border-violet-500 focus:outline-none transition-colors"
                  />
                  {form.substream_url?.trim() && (
                    <p className="mt-1.5 text-[10px] text-violet-400/80">
                      AI inference энэ stream-ээс уншина. Primary stream зөвхөн дэлгэцэд.
                    </p>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* Type */}
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Камерын төрөл</label>
                    <select
                      value={form.camera_type}
                      onChange={(e) => setForm({ ...form, camera_type: e.target.value })}
                      className="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700/50 text-white text-sm focus:border-blue-500 focus:outline-none transition-colors"
                    >
                      {CAMERA_TYPES.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* AI Enabled */}
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">AI илрүүлэлт</label>
                    <button
                      type="button"
                      onClick={() => setForm({ ...form, is_ai_enabled: !form.is_ai_enabled })}
                      className={`w-full px-4 py-3 rounded-xl border text-sm font-bold transition-all ${
                        form.is_ai_enabled
                          ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-400'
                          : 'bg-slate-900/80 border-slate-700/50 text-slate-500'
                      }`}
                    >
                      {form.is_ai_enabled ? 'AI идэвхтэй' : 'AI идэвхгүй (зөвхөн харах)'}
                    </button>
                  </div>
                </div>

                {/* Submit */}
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={resetForm}
                    className="px-6 py-3 rounded-xl border border-slate-700 text-slate-400 text-xs font-bold uppercase hover:bg-slate-800/50 transition-all"
                  >
                    Цуцлах
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-600 text-white text-xs font-bold uppercase hover:bg-blue-500 transition-all disabled:opacity-50"
                  >
                    {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                    {editingId ? 'Хадгалах' : 'Нэмэх'}
                  </button>
                </div>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

        {/* Camera List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : cameras.length === 0 ? (
          <div className="text-center py-20">
            <Camera size={48} className="mx-auto mb-4 text-slate-700" />
            <p className="text-slate-500 text-sm">Камер бүртгэлгүй байна</p>
            <p className="text-slate-600 text-xs mt-1">Дээрх "Камер нэмэх" товч дарж эхлээрэй</p>
          </div>
        ) : (
          <div className="space-y-4">
            {cameras.map((cam, idx) => (
              <motion.div
                key={cam.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="bg-[#0f172a]/60 backdrop-blur-xl rounded-2xl border border-slate-800/50 p-5 hover:border-slate-700/50 transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-xl ${cam.is_active !== false ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-800 text-slate-600'}`}>
                      {cam.is_active !== false ? <Wifi size={20} /> : <WifiOff size={20} />}
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-white">{cam.name}</h3>
                      <p className="text-[10px] font-mono text-slate-500 mt-0.5">{cam.url}</p>
                      <div className="flex items-center gap-3 mt-1.5">
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-500">
                          <Store size={10} />
                          {cam.store_name || 'Дэлгүүр тодорхойгүй'}
                        </span>
                        <span className="text-[10px] font-mono text-slate-600 uppercase">{cam.camera_type || 'N/A'}</span>
                        {cam.is_ai_enabled !== false && (
                          <span className="text-[10px] font-bold text-cyan-400/70">AI</span>
                        )}
                        {cam.substream_url && (
                          <span className="text-[10px] font-bold text-violet-400/70">SUB</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleEdit(cam)}
                      className="p-2.5 rounded-xl border border-slate-700/50 text-slate-500 hover:text-blue-400 hover:border-blue-500/30 transition-all"
                    >
                      <Edit3 size={14} />
                    </button>
                    {deleteConfirm === cam.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleDelete(cam.id)}
                          className="p-2.5 rounded-xl bg-red-600 text-white text-xs font-bold hover:bg-red-500 transition-all"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="p-2.5 rounded-xl border border-slate-700/50 text-slate-500 hover:text-white transition-all"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDeleteConfirm(cam.id)}
                        className="p-2.5 rounded-xl border border-slate-700/50 text-slate-500 hover:text-red-400 hover:border-red-500/30 transition-all"
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

export default MyCameras;

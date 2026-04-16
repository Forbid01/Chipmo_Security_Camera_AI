/* eslint-disable no-unused-vars */
import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  Building2, Video, Plus, Trash2, Edit3, Users, ShieldCheck,
  CheckCircle2, Save, AlertCircle, Loader2, BarChart3, Bell,
  Eye, EyeOff, X, LogOut, ChevronDown, ArrowLeft
} from 'lucide-react';

import {
  getOrganizations, createOrganization, deleteOrganization,
  getCameras, addCamera, deleteCamera, updateCamera,
  getUsers, updateUserRole, updateUserOrganization, deleteUser,
  getAdminStats, getAdminAlerts, markAlertReviewed, deleteAlert
} from '../services/api';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
  { id: 'users', label: 'Users', icon: Users },
  { id: 'organizations', label: 'Organizations', icon: Building2 },
  { id: 'cameras', label: 'Cameras', icon: Video },
  { id: 'alerts', label: 'Alerts', icon: Bell },
];

const StatCard = ({ icon: Icon, label, value, color }) => (
  <motion.div
    whileHover={{ scale: 1.03 }}
    className="bg-[#0f172a]/60 backdrop-blur-2xl p-6 rounded-2xl border border-slate-800/50 ring-1 ring-white/5"
  >
    <div className="flex items-center gap-4">
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon size={22} />
      </div>
      <div>
        <p className="text-3xl font-black text-white">{value}</p>
        <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mt-1">{label}</p>
      </div>
    </div>
  </motion.div>
);

const DashboardAdmin = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(false);

  // Data
  const [stats, setStats] = useState({ users: 0, organizations: 0, cameras: 0, alerts: 0 });
  const [users, setUsersList] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [alerts, setAlerts] = useState([]);

  // Forms
  const [newOrg, setNewOrg] = useState({ name: '' });
  const [newCam, setNewCam] = useState({ name: '', url: '', type: 'axis', organization_id: '' });
  const [editingCamera, setEditingCamera] = useState(null);

  // --- DATA FETCHING ---
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 'dashboard') {
        const s = await getAdminStats();
        setStats(s);
      } else if (activeTab === 'users') {
        const [u, o] = await Promise.all([getUsers(), getOrganizations()]);
        setUsersList(u);
        setOrgs(o);
      } else if (activeTab === 'organizations') {
        const o = await getOrganizations();
        setOrgs(o);
      } else if (activeTab === 'cameras') {
        const [c, o] = await Promise.all([getCameras(), getOrganizations()]);
        setCameras(c);
        setOrgs(o);
      } else if (activeTab === 'alerts') {
        const a = await getAdminAlerts({ limit: 100 });
        setAlerts(a);
      }
    } catch (err) {
      console.error("Fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // --- ORG ACTIONS ---
  const handleAddOrg = async (e) => {
    e.preventDefault();
    try {
      await createOrganization(newOrg.name);
      setNewOrg({ name: '' });
      fetchData();
    } catch (err) { alert("Байгууллага нэмэхэд алдаа гарлаа"); }
  };

  const handleDeleteOrg = async (id) => {
    if (!window.confirm("Байгууллага устгахдаа итгэлтэй байна уу?")) return;
    try { await deleteOrganization(id); fetchData(); } catch { alert("Устгахад алдаа"); }
  };

  // --- CAMERA ACTIONS ---
  const handleAddCamera = async (e) => {
    e.preventDefault();
    try {
      await addCamera({ ...newCam, organization_id: parseInt(newCam.organization_id) });
      setNewCam({ name: '', url: '', type: 'axis', organization_id: '' });
      fetchData();
    } catch { alert("Камер нэмэхэд алдаа"); }
  };

  const handleDeleteCamera = async (id) => {
    if (!window.confirm("Камер устгахдаа итгэлтэй байна уу?")) return;
    try { await deleteCamera(id); fetchData(); } catch { alert("Устгахад алдаа"); }
  };

  const handleUpdateCamera = async (e) => {
    e.preventDefault();
    try {
      await updateCamera(editingCamera.id, {
        name: editingCamera.name,
        url: editingCamera.url,
        type: editingCamera.type,
        organization_id: parseInt(editingCamera.organization_id)
      });
      setEditingCamera(null);
      fetchData();
    } catch { alert("Камер засахад алдаа"); }
  };

  // --- USER ACTIONS ---
  const handleRoleChange = async (userId, role) => {
    try { await updateUserRole(userId, role); fetchData(); } catch { alert("Эрх өөрчлөхөд алдаа"); }
  };

  const handleOrgChange = async (userId, orgId) => {
    try {
      await updateUserOrganization(userId, orgId ? parseInt(orgId) : null);
      fetchData();
    } catch { alert("Байгууллага онооход алдаа"); }
  };

  const handleDeleteUser = async (id) => {
    if (!window.confirm("Хэрэглэгчийг идэвхгүй болгох уу?")) return;
    try { await deleteUser(id); fetchData(); } catch (err) { alert(err.response?.data?.detail || "Алдаа"); }
  };

  // --- ALERT ACTIONS ---
  const handleReviewAlert = async (id) => {
    try { await markAlertReviewed(id); fetchData(); } catch { alert("Алдаа"); }
  };

  const handleDeleteAlert = async (id) => {
    if (!window.confirm("Alert устгах уу?")) return;
    try { await deleteAlert(id); fetchData(); } catch { alert("Устгахад алдаа"); }
  };

  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  // --- RENDER HELPERS ---
  const inputClass = "w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none transition-all text-white";
  const selectClass = "w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none appearance-none text-white cursor-pointer";
  const labelClass = "text-[10px] uppercase font-bold text-slate-500 ml-2";

  // =============================================
  // TAB: DASHBOARD
  // =============================================
  const renderDashboard = () => (
    <div className="space-y-8">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Users} label="Хэрэглэгч" value={stats.users} color="bg-blue-500/10 text-blue-400" />
        <StatCard icon={Building2} label="Байгууллага" value={stats.organizations} color="bg-emerald-500/10 text-emerald-400" />
        <StatCard icon={Video} label="Камер" value={stats.cameras} color="bg-purple-500/10 text-purple-400" />
        <StatCard icon={Bell} label="Alert" value={stats.alerts} color="bg-red-500/10 text-red-400" />
      </div>

      <div className="bg-[#0f172a]/40 backdrop-blur-xl rounded-2xl border border-slate-800/50 p-8">
        <h3 className="text-lg font-bold text-white mb-4">Системийн мэдээлэл</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="flex justify-between py-3 border-b border-slate-800/50">
            <span className="text-slate-500">Платформ</span>
            <span className="text-white font-bold">Chipmo Security AI v1.0</span>
          </div>
          <div className="flex justify-between py-3 border-b border-slate-800/50">
            <span className="text-slate-500">AI Model</span>
            <span className="text-white font-bold">YOLO v11 Pose + Detection</span>
          </div>
          <div className="flex justify-between py-3 border-b border-slate-800/50">
            <span className="text-slate-500">Backend</span>
            <span className="text-white font-bold">FastAPI + PostgreSQL</span>
          </div>
          <div className="flex justify-between py-3 border-b border-slate-800/50">
            <span className="text-slate-500">Deploy</span>
            <span className="text-white font-bold">Railway</span>
          </div>
        </div>
      </div>
    </div>
  );

  // =============================================
  // TAB: USERS
  // =============================================
  const renderUsers = () => (
    <div className="bg-[#0f172a]/40 backdrop-blur-xl rounded-2xl border border-slate-800/50 overflow-hidden shadow-2xl ring-1 ring-white/5">
      <div className="px-8 py-5 border-b border-slate-800/50 flex items-center justify-between">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Бүх хэрэглэгчид ({users.length})</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-900/80 border-b border-slate-800">
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Хэрэглэгч</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Email</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Role</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Байгууллага</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-right">Үйлдэл</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            <AnimatePresence mode="popLayout">
              {users.map((user) => (
                <motion.tr key={user.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  className="hover:bg-white/[0.02] transition-colors"
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-black ${user.is_active ? 'bg-blue-500/10 text-blue-400' : 'bg-red-500/10 text-red-400'}`}>
                        {user.username?.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white">{user.username}</p>
                        <p className="text-[10px] text-slate-500">{user.full_name || '—'}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-xs text-slate-400 font-mono">{user.email}</td>
                  <td className="px-6 py-4">
                    <select
                      value={user.role || 'user'}
                      onChange={(e) => handleRoleChange(user.id, e.target.value)}
                      className="bg-black/40 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white outline-none cursor-pointer"
                    >
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                      <option value="super_admin">Super Admin</option>
                    </select>
                  </td>
                  <td className="px-6 py-4">
                    <select
                      value={user.organization_id || ''}
                      onChange={(e) => handleOrgChange(user.id, e.target.value)}
                      className="bg-black/40 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white outline-none cursor-pointer"
                    >
                      <option value="">— Байгууллагагүй —</option>
                      {orgs.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}
                    </select>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button onClick={() => handleDeleteUser(user.id)}
                      className="p-2 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all"
                      title="Идэвхгүй болгох"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>
        {users.length === 0 && !loading && (
          <div className="py-16 flex flex-col items-center text-slate-600 gap-3">
            <Users size={36} className="opacity-20" />
            <p className="font-mono text-[10px] tracking-[0.4em] uppercase">Хэрэглэгч олдсонгүй</p>
          </div>
        )}
      </div>
    </div>
  );

  // =============================================
  // TAB: ORGANIZATIONS
  // =============================================
  const renderOrganizations = () => (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <div className="lg:col-span-4">
        <motion.div layout initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
          className="bg-[#0f172a]/60 backdrop-blur-2xl p-8 rounded-2xl border border-slate-800/50 ring-1 ring-white/5 shadow-2xl sticky top-8"
        >
          <h3 className="text-lg font-bold mb-6 flex items-center gap-3 text-white">
            <div className="p-2 bg-red-600/20 rounded-lg text-red-500"><Plus size={18} /></div>
            Байгууллага нэмэх
          </h3>
          <form onSubmit={handleAddOrg} className="space-y-4">
            <div className="space-y-1">
              <label className={labelClass}>Байгууллагын нэр</label>
              <input className={inputClass} placeholder="e.g. Nomin Supermarket"
                value={newOrg.name} onChange={(e) => setNewOrg({ name: e.target.value })} required />
            </div>
            <button type="submit" className="w-full bg-red-600 hover:bg-red-500 text-white font-bold py-3.5 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 active:scale-95">
              <Save size={16} /> Хадгалах
            </button>
          </form>
        </motion.div>
      </div>
      <div className="lg:col-span-8">
        <div className="bg-[#0f172a]/40 backdrop-blur-xl rounded-2xl border border-slate-800/50 overflow-hidden shadow-2xl ring-1 ring-white/5">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-900/80 border-b border-slate-800">
                  <th className="px-8 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Нэр</th>
                  <th className="px-8 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-center">Статус</th>
                  <th className="px-8 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-right">Үйлдэл</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                <AnimatePresence mode="popLayout">
                  {orgs.map((org) => (
                    <motion.tr key={org.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, x: -10 }}
                      className="hover:bg-white/[0.02] transition-colors group"
                    >
                      <td className="px-8 py-5">
                        <div className="flex items-center gap-4">
                          <div className="p-3 bg-blue-500/10 rounded-xl text-blue-400 border border-blue-500/20 group-hover:scale-110 transition-transform"><Building2 size={20} /></div>
                          <div>
                            <p className="text-sm font-bold text-white">{org.name}</p>
                            <p className="text-[10px] text-slate-500 font-mono mt-0.5">ID: {org.id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-8 py-5 text-center">
                        <span className="px-3 py-1 bg-emerald-500/10 text-emerald-500 text-[9px] font-black rounded-full border border-emerald-500/20 uppercase tracking-widest">Active</span>
                      </td>
                      <td className="px-8 py-5 text-right">
                        <button onClick={() => handleDeleteOrg(org.id)} className="p-2.5 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all"><Trash2 size={16} /></button>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {orgs.length === 0 && !loading && (
              <div className="py-16 flex flex-col items-center text-slate-600 gap-3">
                <Building2 size={36} className="opacity-20" />
                <p className="font-mono text-[10px] tracking-[0.4em] uppercase">Байгууллага олдсонгүй</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  // =============================================
  // TAB: CAMERAS
  // =============================================
  const renderCameras = () => (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <div className="lg:col-span-4">
        <motion.div layout initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
          className="bg-[#0f172a]/60 backdrop-blur-2xl p-8 rounded-2xl border border-slate-800/50 ring-1 ring-white/5 shadow-2xl sticky top-8"
        >
          <h3 className="text-lg font-bold mb-6 flex items-center gap-3 text-white">
            <div className="p-2 bg-red-600/20 rounded-lg text-red-500"><Plus size={18} /></div>
            Камер нэмэх
          </h3>
          <form onSubmit={handleAddCamera} className="space-y-4">
            <div className="space-y-1">
              <label className={labelClass}>Камерын нэр</label>
              <input className={inputClass} placeholder="Main Entrance"
                value={newCam.name} onChange={(e) => setNewCam({...newCam, name: e.target.value})} required />
            </div>
            <div className="space-y-1">
              <label className={labelClass}>URL (RTSP/IP)</label>
              <input className={`${inputClass} font-mono`} placeholder="rtsp://admin:pass@ip..."
                value={newCam.url} onChange={(e) => setNewCam({...newCam, url: e.target.value})} required />
            </div>
            <div className="space-y-1">
              <label className={labelClass}>Байгууллага</label>
              <select className={selectClass} value={newCam.organization_id}
                onChange={(e) => setNewCam({...newCam, organization_id: e.target.value})} required>
                <option value="" className="bg-slate-900">Сонгох...</option>
                {orgs.map(org => <option key={org.id} value={org.id} className="bg-slate-900">{org.name}</option>)}
              </select>
            </div>
            <button type="submit" className="w-full bg-red-600 hover:bg-red-500 text-white font-bold py-3.5 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 active:scale-95">
              <Save size={16} /> Хадгалах
            </button>
          </form>
        </motion.div>
      </div>
      <div className="lg:col-span-8">
        <div className="bg-[#0f172a]/40 backdrop-blur-xl rounded-2xl border border-slate-800/50 overflow-hidden shadow-2xl ring-1 ring-white/5">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-900/80 border-b border-slate-800">
                  <th className="px-6 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Камер</th>
                  <th className="px-6 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Байгууллага</th>
                  <th className="px-6 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-center">Статус</th>
                  <th className="px-6 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-right">Үйлдэл</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                <AnimatePresence mode="popLayout">
                  {cameras.map((cam) => (
                    <motion.tr key={cam.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, x: -10 }}
                      className="hover:bg-white/[0.02] transition-colors group"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2.5 bg-purple-500/10 rounded-xl text-purple-400 border border-purple-500/20"><Video size={18} /></div>
                          <div className="max-w-[180px]">
                            <p className="text-sm font-bold text-white truncate">{cam.name}</p>
                            <p className="text-[10px] text-slate-500 truncate font-mono mt-0.5">{cam.url}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-xs text-slate-400">{cam.organization_name || '—'}</span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex items-center justify-center gap-1.5 text-blue-400">
                          <CheckCircle2 size={12} className="animate-pulse" />
                          <span className="text-[10px] font-bold uppercase">Live</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right space-x-2">
                        <button onClick={() => setEditingCamera({ ...cam, organization_id: cam.organization_id || '' })}
                          className="p-2 bg-slate-800 text-slate-400 rounded-lg hover:bg-blue-600 hover:text-white transition-all"><Edit3 size={14} /></button>
                        <button onClick={() => handleDeleteCamera(cam.id)}
                          className="p-2 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all"><Trash2 size={14} /></button>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {cameras.length === 0 && !loading && (
              <div className="py-16 flex flex-col items-center text-slate-600 gap-3">
                <Video size={36} className="opacity-20" />
                <p className="font-mono text-[10px] tracking-[0.4em] uppercase">Камер олдсонгүй</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* CAMERA EDIT MODAL */}
      <AnimatePresence>
        {editingCamera && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setEditingCamera(null)}
          >
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
              className="bg-[#0f172a] border border-slate-800 rounded-2xl p-8 w-full max-w-md"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-bold text-white">Камер засах</h3>
                <button onClick={() => setEditingCamera(null)} className="text-slate-500 hover:text-white"><X size={20} /></button>
              </div>
              <form onSubmit={handleUpdateCamera} className="space-y-4">
                <div className="space-y-1">
                  <label className={labelClass}>Нэр</label>
                  <input className={inputClass} value={editingCamera.name}
                    onChange={(e) => setEditingCamera({...editingCamera, name: e.target.value})} required />
                </div>
                <div className="space-y-1">
                  <label className={labelClass}>URL</label>
                  <input className={`${inputClass} font-mono`} value={editingCamera.url}
                    onChange={(e) => setEditingCamera({...editingCamera, url: e.target.value})} required />
                </div>
                <div className="space-y-1">
                  <label className={labelClass}>Төрөл</label>
                  <select className={selectClass} value={editingCamera.type}
                    onChange={(e) => setEditingCamera({...editingCamera, type: e.target.value})}>
                    <option value="axis" className="bg-slate-900">Axis</option>
                    <option value="mac" className="bg-slate-900">Mac</option>
                    <option value="phone" className="bg-slate-900">Phone</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className={labelClass}>Байгууллага</label>
                  <select className={selectClass} value={editingCamera.organization_id}
                    onChange={(e) => setEditingCamera({...editingCamera, organization_id: e.target.value})} required>
                    <option value="" className="bg-slate-900">Сонгох...</option>
                    {orgs.map(org => <option key={org.id} value={org.id} className="bg-slate-900">{org.name}</option>)}
                  </select>
                </div>
                <div className="flex gap-3 pt-2">
                  <button type="button" onClick={() => setEditingCamera(null)}
                    className="flex-1 bg-slate-800 text-slate-300 font-bold py-3 rounded-xl hover:bg-slate-700 transition-all">Болих</button>
                  <button type="submit"
                    className="flex-1 bg-red-600 text-white font-bold py-3 rounded-xl hover:bg-red-500 transition-all flex items-center justify-center gap-2">
                    <Save size={16} /> Хадгалах
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  // =============================================
  // TAB: ALERTS
  // =============================================
  const renderAlerts = () => (
    <div className="bg-[#0f172a]/40 backdrop-blur-xl rounded-2xl border border-slate-800/50 overflow-hidden shadow-2xl ring-1 ring-white/5">
      <div className="px-8 py-5 border-b border-slate-800/50 flex items-center justify-between">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Бүх Alert-ууд ({alerts.length})</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-900/80 border-b border-slate-800">
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">ID</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Тайлбар</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Байгууллага</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">Огноо</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-center">Шалгасан</th>
              <th className="px-6 py-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest text-right">Үйлдэл</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            <AnimatePresence mode="popLayout">
              {alerts.map((alert) => (
                <motion.tr key={alert.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  className="hover:bg-white/[0.02] transition-colors"
                >
                  <td className="px-6 py-4 text-xs font-mono text-slate-400">#{alert.id}</td>
                  <td className="px-6 py-4">
                    <p className="text-sm text-white max-w-[200px] truncate">{alert.description || `Person #${alert.person_id}`}</p>
                  </td>
                  <td className="px-6 py-4 text-xs text-slate-400">{alert.organization_name || '—'}</td>
                  <td className="px-6 py-4 text-xs text-slate-500 font-mono">{alert.event_time}</td>
                  <td className="px-6 py-4 text-center">
                    {alert.reviewed ? (
                      <span className="px-2.5 py-1 bg-emerald-500/10 text-emerald-400 text-[9px] font-bold rounded-full border border-emerald-500/20 uppercase">Шалгасан</span>
                    ) : (
                      <button onClick={() => handleReviewAlert(alert.id)}
                        className="px-2.5 py-1 bg-yellow-500/10 text-yellow-400 text-[9px] font-bold rounded-full border border-yellow-500/20 uppercase hover:bg-yellow-500/20 transition-all cursor-pointer">
                        Шалгаагүй
                      </button>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button onClick={() => handleDeleteAlert(alert.id)}
                      className="p-2 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all"><Trash2 size={14} /></button>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>
        {alerts.length === 0 && !loading && (
          <div className="py-16 flex flex-col items-center text-slate-600 gap-3">
            <Bell size={36} className="opacity-20" />
            <p className="font-mono text-[10px] tracking-[0.4em] uppercase">Alert олдсонгүй</p>
          </div>
        )}
      </div>
    </div>
  );

  // =============================================
  // MAIN RENDER
  // =============================================
  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 p-6 md:p-8 font-sans relative overflow-hidden">
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-red-600/5 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-blue-600/5 blur-[120px] rounded-full pointer-events-none" />

      <div className="max-w-7xl mx-auto relative z-10">
        {/* HEADER */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              title="Хэрэглэгчийн хэсэг рүү буцах"
              className="px-4 py-2.5 rounded-xl border border-slate-700/60 hover:border-blue-500/50 bg-slate-900/40 hover:bg-blue-500/10 text-slate-300 hover:text-blue-400 transition-all flex items-center gap-2 text-xs font-bold uppercase tracking-wider"
            >
              <ArrowLeft size={16} />
              <span className="hidden sm:inline">Dashboard</span>
            </button>
            <div>
              <h1 className="text-3xl md:text-4xl font-black italic tracking-tighter text-white uppercase flex items-center gap-3">
                Admin<span className="text-red-600">.Control</span>
                {loading && <Loader2 className="animate-spin text-slate-500" size={22} />}
              </h1>
              <p className="text-[10px] font-mono text-slate-500 tracking-[0.3em] uppercase mt-2">Системийн удирдлага</p>
            </div>
          </div>

          <button onClick={handleLogout}
            className="px-5 py-2.5 border border-red-500/30 text-red-500 rounded-xl text-xs font-bold uppercase tracking-wider hover:bg-red-500 hover:text-white transition-all flex items-center gap-2">
            <LogOut size={14} /> Гарах
          </button>
        </div>

        {/* TAB NAVIGATION */}
        <div className="flex flex-wrap bg-slate-900/50 p-1.5 rounded-2xl border border-slate-800/50 backdrop-blur-xl shadow-2xl mb-8 gap-1">
          {TABS.map(tab => {
            const Icon = tab.icon;
            return (
              <button key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 md:px-6 py-2.5 rounded-xl text-[10px] md:text-xs font-bold uppercase tracking-wider transition-all flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-red-600 text-white shadow-[0_0_20px_rgba(220,38,38,0.4)]'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                <Icon size={14} />
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* TAB CONTENT */}
        <AnimatePresence mode="wait">
          <motion.div key={activeTab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
            {activeTab === 'dashboard' && renderDashboard()}
            {activeTab === 'users' && renderUsers()}
            {activeTab === 'organizations' && renderOrganizations()}
            {activeTab === 'cameras' && renderCameras()}
            {activeTab === 'alerts' && renderAlerts()}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
};

export default DashboardAdmin;

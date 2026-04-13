/* eslint-disable no-unused-vars */
import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Building2, Video, Plus, Trash2, Edit3, 
  CheckCircle2, Save, AlertCircle, Loader2
} from 'lucide-react';
import axios from 'axios';
import { API_BASE_URL } from '../services/api';

const DashboardAdmin = () => {
  const [activeTab, setActiveTab] = useState('organizations'); 
  const [orgs, setOrgs] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(false);

  // Form states
  const [newOrg, setNewOrg] = useState({ name: '', address: '', contact_info: '' });
  const [newCam, setNewCam] = useState({ name: '', url: '', type: 'axis', organization_id: '' });

  const token = localStorage.getItem('token');

  // --- 1. FUNCTIONS FIRST (To avoid "Accessed before declaration" error) ---

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      
      // Байгууллагуудыг үргэлж татна (Камер нэмэхэд хэрэгтэй тул)
      const orgRes = await axios.get(`${API_BASE_URL}/auth/admin/organizations`, { headers });
      setOrgs(orgRes.data);

      if (activeTab === 'cameras') {
        const camRes = await axios.get(`${API_BASE_URL}/auth/admin/cameras`, { headers });
        setCameras(camRes.data);
      }
    } catch (err) {
      console.error("Мэдээлэл татахад алдаа гарлаа:", err);
    } finally {
      setLoading(false);
    }
  }, [activeTab, token]);

  const handleAddOrg = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API_BASE_URL}/auth/admin/organizations`, newOrg, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setNewOrg({ name: '', address: '', contact_info: '' });
      fetchData();
    } catch (err) {
      console.error(err);
      alert("Байгууллага нэмэхэд алдаа гарлаа");
    }
  };

  const handleAddCamera = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API_BASE_URL}/auth/admin/cameras`, newCam, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setNewCam({ name: '', url: '', type: 'axis', organization_id: '' });
      fetchData();
    } catch (err) {
      console.error(err);
      alert("Камер нэмэхэд алдаа гарлаа");
    }
  };

  const handleDelete = async (type, id) => {
    if (!window.confirm("Та устгахдаа итгэлтэй байна уу?")) return;
    try {
      await axios.delete(`${API_BASE_URL}/auth/admin/${type}/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchData();
    } catch (err) {
      console.error(err);
      alert("Устгахад алдаа гарлаа");
    }
  };

  // --- 2. USEEFFECT CALLS ---

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // --- 3. RENDER ---

  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 p-8 font-sans relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-red-600/5 blur-[120px] rounded-full pointer-events-none" />
      
      <div className="max-w-6xl mx-auto relative z-10">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-6">
          <div>
            <h1 className="text-4xl font-black italic tracking-tighter text-white uppercase flex items-center gap-3">
              Admin<span className="text-red-600">.Control</span>
              {loading && <Loader2 className="animate-spin text-slate-500" size={24} />}
            </h1>
            <p className="text-[10px] font-mono text-slate-500 tracking-[0.3em] uppercase mt-2">Neural Node Management v1.0</p>
          </div>
          
          <div className="flex bg-slate-900/50 p-1.5 rounded-2xl border border-slate-800/50 backdrop-blur-xl shadow-2xl">
            <button 
              onClick={() => setActiveTab('organizations')}
              className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'organizations' ? 'bg-red-600 text-white shadow-[0_0_20px_rgba(220,38,38,0.4)]' : 'text-slate-500 hover:text-slate-300'}`}
            >
              Organizations
            </button>
            <button 
              onClick={() => setActiveTab('cameras')}
              className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'cameras' ? 'bg-red-600 text-white shadow-[0_0_20px_rgba(220,38,38,0.4)]' : 'text-slate-500 hover:text-slate-300'}`}
            >
              Cameras
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left Panel: Creation Form */}
          <div className="lg:col-span-4">
            <motion.div 
              layout
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="bg-[#0f172a]/60 backdrop-blur-2xl p-8 rounded-[2.5rem] border border-slate-800/50 ring-1 ring-white/5 shadow-2xl sticky top-8"
            >
              <h3 className="text-lg font-bold mb-6 flex items-center gap-3 text-white">
                <div className="p-2 bg-red-600/20 rounded-lg text-red-500"><Plus size={18} /></div>
                {activeTab === 'organizations' ? 'Add Organization' : 'Register Camera'}
              </h3>

              <form onSubmit={activeTab === 'organizations' ? handleAddOrg : handleAddCamera} className="space-y-4">
                {activeTab === 'organizations' ? (
                  <>
                    <div className="space-y-1">
                      <label className="text-[10px] uppercase font-bold text-slate-500 ml-2">Company Name</label>
                      <input 
                        className="w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none transition-all text-white" 
                        placeholder="e.g. Nomin Supermarket"
                        value={newOrg.name}
                        onChange={(e) => setNewOrg({...newOrg, name: e.target.value})}
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] uppercase font-bold text-slate-500 ml-2">Location</label>
                      <input 
                        className="w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none transition-all text-white" 
                        placeholder="Ulaanbaatar, MN"
                        value={newOrg.address}
                        onChange={(e) => setNewOrg({...newOrg, address: e.target.value})}
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <div className="space-y-1">
                      <label className="text-[10px] uppercase font-bold text-slate-500 ml-2">Camera Name</label>
                      <input 
                        className="w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none transition-all text-white" 
                        placeholder="Main Entrance"
                        value={newCam.name}
                        onChange={(e) => setNewCam({...newCam, name: e.target.value})}
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] uppercase font-bold text-slate-500 ml-2">RTSP URL</label>
                      <input 
                        className="w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none transition-all text-white font-mono" 
                        placeholder="rtsp://admin:pass@ip..."
                        value={newCam.url}
                        onChange={(e) => setNewCam({...newCam, url: e.target.value})}
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] uppercase font-bold text-slate-500 ml-2">Assign Organization</label>
                      <select 
                        className="w-full bg-black/40 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500/50 outline-none appearance-none text-white cursor-pointer"
                        value={newCam.organization_id}
                        onChange={(e) => setNewCam({...newCam, organization_id: e.target.value})}
                        required
                      >
                        <option value="" className="bg-slate-900">Select...</option>
                        {orgs.map(org => <option key={org.id} value={org.id} className="bg-slate-900">{org.name}</option>)}
                      </select>
                    </div>
                  </>
                )}
                <button type="submit" className="w-full bg-red-600 hover:bg-red-500 text-white font-bold py-4 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 mt-4 active:scale-95">
                  <Save size={18} /> Save Record
                </button>
              </form>
            </motion.div>
          </div>

          {/* Right Panel: Data Table */}
          <div className="lg:col-span-8">
            <div className="bg-[#0f172a]/40 backdrop-blur-xl rounded-[2.5rem] border border-slate-800/50 overflow-hidden shadow-2xl ring-1 ring-white/5">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-900/80 border-b border-slate-800">
                      <th className="px-8 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest font-black">Information</th>
                      <th className="px-8 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest font-black text-center">System Status</th>
                      <th className="px-8 py-5 text-[10px] font-mono text-slate-500 uppercase tracking-widest font-black text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    <AnimatePresence mode="popLayout">
                      {activeTab === 'organizations' ? orgs.map((org) => (
                        <motion.tr 
                          key={org.id} 
                          initial={{ opacity: 0 }} 
                          animate={{ opacity: 1 }} 
                          exit={{ opacity: 0, x: -10 }}
                          className="hover:bg-white/[0.02] transition-colors group"
                        >
                          <td className="px-8 py-5">
                            <div className="flex items-center gap-4">
                              <div className="p-3 bg-blue-500/10 rounded-2xl text-blue-400 border border-blue-500/20 group-hover:scale-110 transition-transform"><Building2 size={20}/></div>
                              <div>
                                <p className="text-sm font-black text-white">{org.name}</p>
                                <p className="text-[10px] text-slate-500 font-mono mt-0.5 uppercase tracking-tighter">{org.address || 'Global Access'}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-8 py-5 text-center">
                            <span className="px-3 py-1 bg-emerald-500/10 text-emerald-500 text-[9px] font-black rounded-full border border-emerald-500/20 uppercase tracking-widest shadow-[0_0_10px_rgba(16,185,129,0.1)]">Active</span>
                          </td>
                          <td className="px-8 py-5 text-right space-x-2">
                            <button onClick={() => handleDelete('organizations', org.id)} className="p-2.5 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all"><Trash2 size={16}/></button>
                          </td>
                        </motion.tr>
                      )) : cameras.map((cam) => (
                        <motion.tr 
                          key={cam.id} 
                          initial={{ opacity: 0 }} 
                          animate={{ opacity: 1 }} 
                          exit={{ opacity: 0, x: -10 }}
                          className="hover:bg-white/[0.02] transition-colors group"
                        >
                          <td className="px-8 py-5">
                            <div className="flex items-center gap-4">
                              <div className="p-3 bg-purple-500/10 rounded-2xl text-purple-400 border border-purple-500/20 group-hover:scale-110 transition-transform"><Video size={20}/></div>
                              <div className="max-w-[200px]">
                                <p className="text-sm font-black text-white truncate">{cam.name}</p>
                                <p className="text-[10px] text-slate-500 truncate font-mono mt-0.5">{cam.url}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-8 py-5 text-center">
                             <div className="flex items-center justify-center gap-2 text-blue-400">
                                <CheckCircle2 size={14} className="animate-pulse" />
                                <span className="text-[10px] font-black uppercase tracking-tighter">Live Stream</span>
                             </div>
                          </td>
                          <td className="px-8 py-5 text-right space-x-2">
                            <button className="p-2.5 bg-slate-800 text-slate-400 rounded-lg hover:bg-blue-600 hover:text-white transition-all"><Edit3 size={16}/></button>
                            <button onClick={() => handleDelete('cameras', cam.id)} className="p-2.5 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all"><Trash2 size={16}/></button>
                          </td>
                        </motion.tr>
                      ))}
                    </AnimatePresence>
                  </tbody>
                </table>
                {((activeTab === 'organizations' ? orgs : cameras).length === 0 && !loading) && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-24 flex flex-col items-center justify-center text-slate-600 gap-4">
                    <AlertCircle size={40} className="opacity-20" />
                    <p className="font-mono text-[10px] tracking-[0.4em] uppercase font-bold">No Neural Nodes Detected</p>
                  </motion.div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardAdmin;
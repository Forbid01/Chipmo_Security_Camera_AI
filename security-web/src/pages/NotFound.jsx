import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowLeft, Home } from 'lucide-react';
import { motion } from 'framer-motion';

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05080d] p-6 font-sans relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none"
           style={{ backgroundImage: `radial-gradient(#475569 1px, transparent 1px)`, backgroundSize: '30px 30px' }} />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center z-10 max-w-md"
      >
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-red-500/10 border border-red-500/20 mb-8">
          <ShieldCheck size={40} className="text-red-500" />
        </div>

        <h1 className="text-8xl font-black text-white tracking-tighter mb-2">404</h1>
        <p className="text-slate-400 text-lg mb-2">Хуудас олдсонгүй</p>
        <p className="text-slate-600 text-sm mb-10">Таны хайсан хуудас байхгүй эсвэл зөөгдсөн байна.</p>

        <div className="flex gap-4 justify-center">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 px-6 py-3 rounded-2xl border border-slate-700 text-slate-300 text-xs font-bold uppercase tracking-widest hover:bg-slate-800/50 transition-all"
          >
            <ArrowLeft size={14} /> Буцах
          </button>
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-6 py-3 rounded-2xl bg-red-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-red-500 transition-all"
          >
            <Home size={14} /> Нүүр хуудас
          </button>
        </div>
      </motion.div>
    </div>
  );
}

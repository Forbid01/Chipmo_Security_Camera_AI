/* eslint-disable no-unused-vars */
import { motion, AnimatePresence } from 'framer-motion';
import { X, Activity } from 'lucide-react';

export const VideoModal = ({ videoUrl, onClose }) => (
  <AnimatePresence>
    {videoUrl && (
      <motion.div 
        initial={{ opacity: 0 }} 
        animate={{ opacity: 1 }} 
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md"
      >
        <motion.div 
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          className="relative w-full max-w-4xl bg-[#151b2c] rounded-3xl border border-slate-700 overflow-hidden shadow-2xl"
        >
          {/* Хаах товч */}
          <button 
            onClick={onClose} 
            className="absolute top-4 right-4 p-2 bg-black/50 hover:bg-red-500 rounded-full z-10 transition-colors text-white"
          >
            <X size={24} />
          </button>

          {/* ЧУХАЛ ЗАСВАР: src-ийг шууд videoUrl болгох */}
          <video 
            src={videoUrl} 
            controls 
            autoPlay 
            className="w-full aspect-video bg-black"
          >
            Your browser does not support the video tag.
          </video>

          <div className="p-6 bg-slate-900/50">
            <h3 className="text-xl font-bold flex items-center gap-2 text-white">
              <Activity className="text-red-500" /> AI Evidence Playback
            </h3>
            <p className="text-slate-400 text-sm italic">Security Recording ID: {videoUrl.split('/').pop()}</p>
          </div>
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
);
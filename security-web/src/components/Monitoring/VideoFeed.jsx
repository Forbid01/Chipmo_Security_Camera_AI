// src/components/Monitoring/VideoFeed.jsx
import React, { useMemo } from 'react';
import { getVideoFeedUrl } from '../../services/api';
import { Camera } from 'lucide-react';

// React.memo prevents re-mounting the <img> (and thus re-opening the MJPEG
// socket) when an unrelated parent state changes. MJPEG re-connects are the
// #1 source of "dashboard lag" symptoms — every remount causes a 1-2s gap.
export const VideoFeed = React.memo(function VideoFeed({ cameraId = 'mac' }) {
  const src = useMemo(() => getVideoFeedUrl(cameraId), [cameraId]);

  return (
    <div className="flex flex-col w-full h-full bg-[#151b2c] rounded-2xl border border-slate-700 overflow-hidden shadow-lg">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 bg-slate-800/50">
        <h2 className="text-white font-semibold flex items-center gap-2">
          <Camera size={20} className="text-emerald-400" />
          Live Monitoring
        </h2>
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
          </span>
          <span className="text-red-400 text-xs font-bold uppercase">Live</span>
        </div>
      </div>

      <div className="relative w-full aspect-video bg-black flex items-center justify-center">
        <img
          key={cameraId}
          src={src}
          alt="AI Camera Feed"
          decoding="async"
          className="w-full h-full object-contain"
        />
      </div>
    </div>
  );
});

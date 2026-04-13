import { Image, PlayCircle, TriangleAlert } from 'lucide-react';

export const AlertCard = ({ alert, onSelect }) => {
  const description = alert?.description || 'Suspicious activity detected';
  const eventTime = alert?.event_time || 'Unknown time';
  const imageUrl = alert?.web_url;
  const videoUrl = alert?.video_url;

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-950/60 p-4 shadow-lg ring-1 ring-white/5">
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-red-500/10 text-red-400">
          <TriangleAlert size={20} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-black uppercase tracking-wide text-slate-100">
                Alert #{alert?.id ?? 'N/A'}
              </p>
              <p className="mt-1 text-xs text-slate-400">{description}</p>
            </div>
            <p className="shrink-0 text-[10px] font-mono uppercase tracking-wider text-slate-500">
              {eventTime}
            </p>
          </div>

          <div className="mt-4 flex items-center gap-3">
            {imageUrl ? (
              <a
                href={imageUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-2 text-xs font-bold text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
              >
                <Image size={14} />
                Snapshot
              </a>
            ) : (
              <span className="inline-flex items-center gap-2 rounded-full border border-slate-800 px-3 py-2 text-xs font-bold text-slate-500">
                <Image size={14} />
                No Image
              </span>
            )}

            <button
              type="button"
              disabled={!videoUrl}
              onClick={() => videoUrl && onSelect(videoUrl)}
              className="inline-flex items-center gap-2 rounded-full bg-red-600 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
            >
              <PlayCircle size={14} />
              Review Video
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

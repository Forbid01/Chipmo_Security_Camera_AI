import { useState } from 'react';
import { Image, PlayCircle, TriangleAlert, ThumbsUp, ThumbsDown, Loader2 } from 'lucide-react';
import { submitAlertFeedback } from '../../services/api';

export const AlertCard = ({ alert, onSelect }) => {
  const [feedbackStatus, setFeedbackStatus] = useState(alert?.feedback_status || 'unreviewed');
  const [loading, setLoading] = useState(false);

  const description = alert?.description || 'Suspicious activity detected';
  const eventTime = alert?.event_time || 'Unknown time';
  const imageUrl = alert?.web_url;
  const videoUrl = alert?.video_url;

  const handleFeedback = async (type) => {
    if (loading || feedbackStatus !== 'unreviewed') return;
    setLoading(true);
    try {
      await submitAlertFeedback(alert.id, type);
      setFeedbackStatus(type);
    } catch (err) {
      console.error('Feedback error:', err);
    } finally {
      setLoading(false);
    }
  };

  const feedbackBadge = {
    true_positive: { text: 'Зөв сэрэмжлүүлэг', color: 'text-green-400 border-green-500/30 bg-green-500/10' },
    false_positive: { text: 'Буруу сэрэмжлүүлэг', color: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' },
    unreviewed: null,
  };

  const badge = feedbackBadge[feedbackStatus];

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
              {alert?.store_name && (
                <p className="mt-0.5 text-[10px] text-cyan-400/70">{alert.store_name}</p>
              )}
            </div>
            <div className="text-right">
              <p className="shrink-0 text-[10px] font-mono uppercase tracking-wider text-slate-500">
                {eventTime}
              </p>
              {alert?.confidence_score && (
                <p className="text-[10px] text-slate-600">Score: {Math.round(alert.confidence_score)}</p>
              )}
            </div>
          </div>

          {/* Feedback badge */}
          {badge && (
            <div className={`mt-2 inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${badge.color}`}>
              {badge.text}
            </div>
          )}

          <div className="mt-4 flex items-center gap-2">
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
              Review
            </button>

            {/* AI Feedback buttons */}
            {feedbackStatus === 'unreviewed' && (
              <>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => handleFeedback('true_positive')}
                  className="inline-flex items-center gap-1.5 rounded-full border border-green-500/30 px-2.5 py-2 text-xs font-bold text-green-400 transition-colors hover:bg-green-500/10 disabled:opacity-50"
                  title="Зөв сэрэмжлүүлэг (AI суралцана)"
                >
                  {loading ? <Loader2 size={12} className="animate-spin" /> : <ThumbsUp size={12} />}
                </button>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => handleFeedback('false_positive')}
                  className="inline-flex items-center gap-1.5 rounded-full border border-yellow-500/30 px-2.5 py-2 text-xs font-bold text-yellow-400 transition-colors hover:bg-yellow-500/10 disabled:opacity-50"
                  title="Буруу сэрэмжлүүлэг (AI суралцана)"
                >
                  {loading ? <Loader2 size={12} className="animate-spin" /> : <ThumbsDown size={12} />}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

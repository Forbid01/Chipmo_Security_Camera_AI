import { memo, useState } from 'react';
import { Image, PlayCircle, TriangleAlert, ThumbsUp, ThumbsDown, Loader2, ScanFace, ChevronDown, ChevronUp } from 'lucide-react';
import { submitAlertFeedback, getReidMatches } from '../../services/api';
import AlertVerdictBadges from '../Alerts/AlertVerdictBadges';
import AlertVlmDetail from '../Alerts/AlertVlmDetail';

const AlertCardInner = ({ alert, onSelect }) => {
  const [feedbackStatus, setFeedbackStatus] = useState(alert?.feedback_status || 'unreviewed');
  const [loading, setLoading] = useState(false);
  const [reidOpen, setReidOpen] = useState(false);
  const [reidMatches, setReidMatches] = useState(null);
  const [reidLoading, setReidLoading] = useState(false);

  const description = alert?.description || 'Сэжигтэй үйлдэл илэрлээ';
  const eventTime = alert?.event_time || 'Тодорхойгүй';
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

  const handleReidToggle = async () => {
    if (reidOpen) { setReidOpen(false); return; }
    setReidOpen(true);
    if (reidMatches !== null) return;
    setReidLoading(true);
    try {
      const data = await getReidMatches(alert.id);
      setReidMatches(data.matches || []);
    } catch {
      setReidMatches([]);
    } finally {
      setReidLoading(false);
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
                <p className="text-[10px] text-slate-600">Оноо: {Math.round(alert.confidence_score)}</p>
              )}
            </div>
          </div>

          {/* Feedback badge */}
          {badge && (
            <div className={`mt-2 inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${badge.color}`}>
              {badge.text}
            </div>
          )}

          {/* RAG / VLM verdict badges (Phase 2). Returns null on legacy
              alerts where the pipeline never ran, so the row is invisible
              for older data. */}
          <div className="mt-2">
            <AlertVerdictBadges alert={alert} />
          </div>

          {/* VLM caption — only on alerts that the VLM actually saw and
              that weren't suppressed by RAG. Polls the backend until the
              annotation row is ready, then degrades silently. */}
          {alert?.vlm_decision && alert.vlm_decision !== 'not_run' && !alert.suppressed && (
            <div className="mt-3">
              <AlertVlmDetail alertId={alert.id} />
            </div>
          )}

          {/* Cross-camera Re-ID matches */}
          <div className="mt-3">
            <button
              type="button"
              onClick={handleReidToggle}
              className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 hover:text-violet-400 transition-colors"
            >
              <ScanFace size={12} />
              Бусад камер дахь ижил хүн
              {reidOpen ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            </button>

            {reidOpen && (
              <div className="mt-2 rounded-xl border border-violet-500/20 bg-violet-500/5 p-3">
                {reidLoading ? (
                  <div className="flex items-center gap-2 text-[10px] text-slate-500">
                    <Loader2 size={10} className="animate-spin" />
                    Хайж байна...
                  </div>
                ) : reidMatches && reidMatches.length > 0 ? (
                  <div className="space-y-2">
                    {reidMatches.map((m, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ScanFace size={10} className="text-violet-400 shrink-0" />
                          <span className="text-[10px] text-slate-300 font-mono">
                            Камер #{m.camera_id}
                          </span>
                          {m.alert_id && (
                            <span className="text-[10px] text-slate-500">
                              · Alert #{m.alert_id}
                            </span>
                          )}
                          <span className="text-[10px] text-slate-600">
                            {m.captured_at ? new Date(m.captured_at).toLocaleTimeString('mn-MN') : ''}
                          </span>
                        </div>
                        <span className={`text-[10px] font-black font-mono ${
                          m.similarity >= 0.9 ? 'text-red-400' :
                          m.similarity >= 0.8 ? 'text-orange-400' : 'text-yellow-400'
                        }`}>
                          {Math.round(m.similarity * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[10px] text-slate-600">
                    Сүүлийн 30 минутад бусад камерт ижил хүн илрэлгүй
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center gap-2">
            {imageUrl ? (
              <a
                href={imageUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-2 text-xs font-bold text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
              >
                <Image size={14} />
                Зураг
              </a>
            ) : (
              <span className="inline-flex items-center gap-2 rounded-full border border-slate-800 px-3 py-2 text-xs font-bold text-slate-500">
                <Image size={14} />
                Зургүй
              </span>
            )}

            <button
              type="button"
              disabled={!videoUrl}
              onClick={() => videoUrl && onSelect(videoUrl)}
              className="inline-flex items-center gap-2 rounded-full bg-red-600 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
            >
              <PlayCircle size={14} />
              Бичлэг
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

// Only re-render if the alert identity or feedback state actually changes.
// onSelect is stable (setState setter) so ignoring it is safe.
const alertPropsEqual = (prev, next) => {
  const a = prev.alert;
  const b = next.alert;
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.id === b.id &&
    a.feedback_status === b.feedback_status &&
    a.web_url === b.web_url &&
    a.video_url === b.video_url &&
    a.event_time === b.event_time &&
    a.rag_decision === b.rag_decision &&
    a.vlm_decision === b.vlm_decision &&
    a.suppressed === b.suppressed
  );
};

export const AlertCard = memo(AlertCardInner, alertPropsEqual);

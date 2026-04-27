// Tiny badges that surface the RAG/VLM pipeline verdict on alert
// cards and admin tables.
//
// `alert` is the row returned by /api/v1/alerts — the relevant fields
// are `rag_decision`, `vlm_decision`, `suppressed`, `suppressed_reason`.
// All four are nullable, so the component degrades to nothing when an
// alert was created before the pipeline shipped.

const PALETTE = {
  passed: "bg-emerald-100 text-emerald-700 border-emerald-300",
  suppressed: "bg-rose-100 text-rose-700 border-rose-300",
  not_run: "bg-gray-100 text-gray-500 border-gray-300",
};

function Pill({ label, variant, title }) {
  const cls = PALETTE[variant] || PALETTE.not_run;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

function variantFor(decision, kind) {
  if (decision === `suppressed_by_${kind}`) return "suppressed";
  if (decision === "passed") return "passed";
  return "not_run";
}

export default function AlertVerdictBadges({ alert }) {
  if (!alert) return null;
  const rag = alert.rag_decision;
  const vlm = alert.vlm_decision;
  const suppressed = alert.suppressed;
  const reason = alert.suppressed_reason;

  // Hide the row entirely on legacy alerts where the pipeline never ran.
  if (!rag && !vlm && !suppressed) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {rag && (
        <Pill
          label={`RAG: ${rag === "suppressed_by_rag" ? "suppressed" : rag}`}
          variant={variantFor(rag, "rag")}
          title={rag === "suppressed_by_rag" ? reason || "RAG suppressed" : rag}
        />
      )}
      {vlm && (
        <Pill
          label={`VLM: ${vlm === "suppressed_by_vlm" ? "suppressed" : vlm}`}
          variant={variantFor(vlm, "vlm")}
          title={vlm === "suppressed_by_vlm" ? reason || "VLM suppressed" : vlm}
        />
      )}
    </div>
  );
}

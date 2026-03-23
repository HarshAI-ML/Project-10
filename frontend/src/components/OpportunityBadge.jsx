export default function OpportunityBadge({ level }) {
  const value = (level || "").toUpperCase();

  const styles = {
    HIGH: "bg-emerald-100 text-emerald-700 border-emerald-200",
    MEDIUM: "bg-amber-100 text-amber-700 border-amber-200",
    LOW: "bg-rose-100 text-rose-700 border-rose-200",
  };

  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${
        styles[value] || "bg-slate-100 text-slate-700 border-slate-200"
      }`}
    >
      {value || "N/A"}
    </span>
  );
}

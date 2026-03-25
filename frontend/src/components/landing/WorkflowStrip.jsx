const STEPS = [
  { title: "Discover", desc: "Browse capabilities and evaluate opportunities." },
  { title: "Analyze", desc: "Use prediction, sentiment, compare, and clustering context." },
  { title: "Execute", desc: "Apply decisions through portfolios and AutoSignal workflows." },
];

export default function WorkflowStrip() {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-lg backdrop-blur">
      <h3 className="text-2xl font-black text-white">Workflow that matches your product</h3>
      <div className="mt-5 grid gap-4 md:grid-cols-3">
        {STEPS.map((item, idx) => (
          <article key={item.title} className="rounded-xl border border-white/10 bg-slate-900/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">Step {idx + 1}</p>
            <h4 className="mt-2 text-lg font-bold text-white">{item.title}</h4>
            <p className="mt-1 text-sm text-slate-300">{item.desc}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

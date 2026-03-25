const BLOCKS = [
  {
    title: "Portfolio Hub",
    text: "Organize and monitor your custom and default portfolios with cleaner state awareness.",
    color: "from-cyan-400 to-blue-500",
  },
  {
    title: "Stock Compare",
    text: "Evaluate two stocks side by side before making execution decisions.",
    color: "from-indigo-400 to-violet-500",
  },
  {
    title: "Price Prediction",
    text: "Run model-based projection flows and review confidence before entry.",
    color: "from-emerald-400 to-teal-500",
  },
  {
    title: "Cluster View",
    text: "Identify behavior patterns and similarities through clustering analytics.",
    color: "from-fuchsia-400 to-pink-500",
  },
  {
    title: "AutoSignal",
    text: "Get condensed recommendations to prioritize your next action.",
    color: "from-sky-400 to-indigo-500",
  },
  {
    title: "Telegram OTP Flows",
    text: "Fast secure onboarding and password recovery using Telegram verification.",
    color: "from-orange-400 to-rose-500",
  },
];

export default function FeatureHighlights() {
  return (
    <section id="features" className="space-y-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">Feature Architecture</p>
        <h2 className="mt-1 text-3xl font-black text-white">Designed around what your app actually does</h2>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {BLOCKS.map((item) => (
          <article
            key={item.title}
            className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-5 shadow-lg backdrop-blur transition hover:-translate-y-1 hover:border-cyan-300/40"
          >
            <div className={`mb-3 h-1.5 w-14 rounded-full bg-gradient-to-r ${item.color}`} />
            <h3 className="text-lg font-bold text-white">{item.title}</h3>
            <p className="mt-2 text-sm text-slate-300">{item.text}</p>
            <div className={`pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-gradient-to-r ${item.color} opacity-10 blur-2xl transition group-hover:opacity-25`} />
          </article>
        ))}
      </div>
    </section>
  );
}

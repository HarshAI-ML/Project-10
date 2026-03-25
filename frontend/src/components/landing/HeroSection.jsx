import { Link } from "react-router-dom";

export default function HeroSection() {
  return (
    <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl backdrop-blur md:p-10">
      <div className="pointer-events-none absolute -left-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/20 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-12 h-72 w-72 rounded-full bg-indigo-500/20 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 left-1/3 h-64 w-64 rounded-full bg-fuchsia-500/10 blur-3xl" />

      <div className="relative grid gap-8 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <div>
          <span className="inline-flex items-center rounded-full border border-cyan-300/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-cyan-200">
            Built around your real product features
          </span>
          <h1 className="mt-4 text-4xl font-black leading-tight text-white sm:text-6xl">
            A beautiful command center
            <span className="block bg-gradient-to-r from-cyan-300 via-indigo-300 to-fuchsia-300 bg-clip-text text-transparent">
              for smarter investing.
            </span>
          </h1>
          <p className="mt-5 max-w-2xl text-sm text-slate-300 sm:text-base">
            Portfolio tracking, stock comparison, prediction pipelines, clustering insights, AutoSignal, and adaptive chatbot intelligence,
            all wrapped in one clean interface.
          </p>

          <div className="mt-7 flex flex-wrap gap-3">
            <Link
              to="/register"
              className="rounded-xl bg-gradient-to-r from-cyan-300 to-indigo-400 px-5 py-3 text-sm font-semibold text-slate-950 shadow-md transition hover:from-cyan-200 hover:to-indigo-300"
            >
              Start Free
            </Link>
            <a
              href="#features"
              className="rounded-xl border border-white/20 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:border-cyan-300 hover:text-cyan-200"
            >
              View Features
            </a>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-[#0b1227]/80 p-5 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Session Preview</p>
              <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
                Synced
              </span>
            </div>
            <div className="space-y-2 text-sm">
              <div className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Compare selected equities across risk + trend.</div>
              <div className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Run prediction and inspect confidence output.</div>
              <div className="rounded-lg bg-cyan-500/10 px-3 py-2 text-cyan-200">Use chatbot for generic/public or personal/account context.</div>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}

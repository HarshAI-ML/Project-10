import { Link } from "react-router-dom";

export default function LandingFooter() {
  return (
    <footer className="border-t border-white/10 bg-[#050816] py-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-3 px-4 sm:flex-row sm:px-6 lg:px-8">
        <p className="text-sm text-slate-400">Auto Invest AI (c) 2026</p>
        <div className="flex items-center gap-4 text-sm">
          <Link to="/login" className="text-slate-300 transition hover:text-cyan-300">
            Login
          </Link>
          <Link to="/register" className="text-slate-300 transition hover:text-cyan-300">
            Register
          </Link>
        </div>
      </div>
    </footer>
  );
}

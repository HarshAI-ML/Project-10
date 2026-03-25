import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  if (isAuthenticated) return <Navigate to="/portfolio" replace />;

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 shadow-lg">
            <span className="text-2xl font-black text-white">AI</span>
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900">Create account</h1>
          <p className="mt-1 text-sm text-slate-500">All registrations require Telegram OTP verification.</p>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-xl ring-1 ring-slate-100">
          <p className="mb-5 text-sm text-slate-600">
            For security, new accounts must be created through the Telegram OTP flow (username + email + password + OTP).
          </p>

          <button
            onClick={() => navigate("/telegram-register")}
            className="w-full rounded-xl bg-gradient-to-r from-blue-500 to-cyan-500 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-blue-600 hover:to-cyan-600"
          >
            🔐 Register with Telegram (Required)
          </button>

          <p className="mt-5 text-center text-sm text-slate-500">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-800">
              Sign in →
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

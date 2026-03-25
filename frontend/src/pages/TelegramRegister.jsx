import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Loader from "../components/Loader";
import { generateTelegramQR, verifyTelegramOTP } from "../api/auth";

export default function TelegramRegister() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: QR, 2: OTP, 3: Details, 4: Success
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [qrData, setQrData] = useState(null);
  const [refId, setRefId] = useState("");
  const [isOtpVerified, setIsOtpVerified] = useState(false);
  const [form, setForm] = useState({ otp_code: "", username: "", password: "", email: "" });
  const [showPass, setShowPass] = useState(false);
  const [successData, setSuccessData] = useState(null);

  if (isAuthenticated) return <Navigate to="/portfolio" replace />;

  const handleGenerateQR = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await generateTelegramQR("registration");
      setQrData(data);
      setRefId(data.ref_id);
      setIsOtpVerified(false);
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to generate QR code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOTP = async () => {
    if (!form.otp_code || form.otp_code.length !== 6) {
      setError("OTP must be 6 digits");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await verifyTelegramOTP(refId, form.otp_code);
      setIsOtpVerified(true);
      setStep(3);
    } catch (err) {
      setError(err.response?.data?.detail || "OTP verification failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: value }));
  };

  const handleCompleteRegistration = async () => {
    if (!isOtpVerified) {
      setError("Please verify OTP first.");
      return;
    }

    // Validate inputs
    if (!form.username || !form.password || !form.email) {
      setError("All fields are required");
      return;
    }
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      setError("Invalid email address");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const data = await verifyTelegramOTP(refId, form.otp_code, {
        username: form.username,
        password: form.password,
        email: form.email,
      });

      setSuccessData(data);
      setStep(4);

      // Store token and redirect after 2 seconds
      setTimeout(() => {
        localStorage.setItem("auth_token", data.token);
        localStorage.setItem("auth_username", data.username);
        navigate("/portfolio", { replace: true });
      }, 2000);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
        err.response?.data?.username?.[0] ||
        err.response?.data?.email?.[0] ||
        "Registration failed. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Brand */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 shadow-lg">
            <span className="text-2xl font-black text-white">AI</span>
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900">Create account</h1>
          <p className="mt-1 text-sm text-slate-500">Register with Telegram OTP verification</p>
          <p className="mt-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">Step {step} of 4</p>
        </div>

        {/* Card */}
        <div className="rounded-2xl bg-white p-8 shadow-xl ring-1 ring-slate-100">
          {/* Step 1: QR Code Generation */}
          {step === 1 && (
            <div className="space-y-5">
              <div>
                <p className="text-sm text-slate-600 mb-4">
                  Scan the QR code with Telegram to verify your identity and receive an OTP.
                </p>
                <button
                  onClick={handleGenerateQR}
                  disabled={loading}
                  className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50"
                >
                  {loading ? "Generating..." : "Generate QR Code"}
                </button>
              </div>
              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              )}
              <div className="pt-4 border-t border-slate-200">
                <p className="text-xs text-slate-500 text-center">
                  Already have an account?{" "}
                  <Link to="/login" className="font-semibold text-indigo-600 hover:underline">
                    Login
                  </Link>
                </p>
              </div>
            </div>
          )}

          {/* Step 2: OTP Verification */}
          {step === 2 && qrData && (
            <div className="space-y-5">
              <div className="text-center">
                <p className="mb-4 text-sm text-slate-600">
                  Scan this QR code with Telegram:
                </p>
                <div className="mx-auto mb-4 rounded-2xl border-2 border-indigo-200 bg-slate-50 p-4 w-fit">
                  <img
                    src={`data:image/png;base64,${qrData.qr_code_base64}`}
                    alt="Telegram QR Code"
                    className="h-64 w-64"
                  />
                </div>
                <p className="mb-3 text-xs text-slate-500">
                  Or{" "}
                  <a
                    href={qrData.telegram_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold text-indigo-600 hover:underline"
                  >
                    open Telegram directly
                  </a>
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  OTP Code
                </label>
                <input
                  type="text"
                  name="otp_code"
                  value={form.otp_code}
                  onChange={handleChange}
                  maxLength={6}
                  placeholder="000000"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-lg font-bold letter-spacing tracking-widest transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
                <p className="mt-1 text-xs text-slate-400">
                  Enter the 6-digit code from Telegram
                </p>
              </div>

              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              )}

              <button
                onClick={handleVerifyOTP}
                disabled={loading || form.otp_code.length !== 6}
                className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50"
              >
                {loading ? "Verifying..." : "Continue"}
              </button>

              <div className="pt-4 border-t border-slate-200">
                <button
                  onClick={() => setStep(1)}
                  className="w-full text-center text-xs font-semibold text-slate-500 hover:text-slate-700 transition"
                >
                  Back to QR Code
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Account Details */}
          {step === 3 && (
            <form className="space-y-5">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Username
                </label>
                <input
                  type="text"
                  name="username"
                  value={form.username}
                  onChange={handleChange}
                  placeholder="johndoe"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  required
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Email
                </label>
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="john@example.com"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  required
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPass ? "text" : "password"}
                    name="password"
                    value={form.password}
                    onChange={handleChange}
                    placeholder="Min 8 characters"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 pr-12 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                    minLength={8}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass((p) => !p)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPass ? (
                      <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                      </svg>
                    ) : (
                      <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              )}

              <button
                type="button"
                onClick={handleCompleteRegistration}
                disabled={loading}
                className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50"
              >
                {loading ? "Creating account..." : "Complete Registration"}
              </button>

              <div className="pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="w-full text-center text-xs font-semibold text-slate-500 hover:text-slate-700 transition"
                >
                  Back
                </button>
              </div>
            </form>
          )}

          {/* Step 4: Success */}
          {step === 4 && successData && (
            <div className="text-center space-y-5">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
                  <svg className="h-8 w-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div>
                <h2 className="text-2xl font-extrabold text-slate-900">Welcome, {successData.username}!</h2>
                <p className="mt-1 text-sm text-slate-500">Your account has been created successfully</p>
              </div>
              <p className="text-xs text-slate-400">Redirecting to dashboard...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

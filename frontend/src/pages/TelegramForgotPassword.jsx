import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { initiateForgotPassword, resetPassword, verifyTelegramOTP } from "../api/auth";

export default function TelegramForgotPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: Email, 2: QR, 3: OTP, 4: New Password, 5: Success
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "",
    otp_code: "",
    new_password: "",
    confirm_password: "",
  });
  const [showNewPass, setShowNewPass] = useState(false);
  const [showConfirmPass, setShowConfirmPass] = useState(false);
  const [qrData, setQrData] = useState(null);
  const [refId, setRefId] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: value }));
  };

  const handleSendEmail = async () => {
    if (!form.email) {
      setError("Email is required");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      setError("Invalid email address");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const data = await initiateForgotPassword(form.email);
      setQrData(data);
      setRefId(data.ref_id);
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate password reset. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOTP = async () => {
    const otpCode = String(form.otp_code || "").trim();
    if (!otpCode || otpCode.length !== 6 || !/^\d{6}$/.test(otpCode)) {
      setError("OTP must be 6 digits");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await verifyTelegramOTP(refId, otpCode);
      // Move to password reset step only when backend verifies OTP
      setStep(4);
    } catch (err) {
      setError(err.response?.data?.detail || "OTP verification failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (!form.new_password || !form.confirm_password) {
      setError("Both password fields are required");
      return;
    }
    if (form.new_password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (form.new_password !== form.confirm_password) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const data = await resetPassword(refId, form.otp_code, form.new_password, form.confirm_password);
      setSuccessMessage(data.message);
      setStep(5);

      // Redirect to login after 2 seconds
      setTimeout(() => {
        navigate("/login", { replace: true });
      }, 2000);
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.confirm_password?.[0] || "Password reset failed. Please try again.");
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
          <h1 className="text-2xl font-extrabold text-slate-900">Reset password</h1>
          <p className="mt-1 text-sm text-slate-500">Recover your account with Telegram OTP</p>
          <p className="mt-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">Step {step} of 5</p>
        </div>

        {/* Card */}
        <div className="rounded-2xl bg-white p-8 shadow-xl ring-1 ring-slate-100">
          {/* Step 1: Enter Email */}
          {step === 1 && (
            <div className="space-y-5">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Email Address
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
                <p className="mt-2 text-xs text-slate-400">Enter the email associated with your account</p>
              </div>

              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {error}
                </div>
              )}

              <button
                onClick={handleSendEmail}
                disabled={loading}
                className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50"
              >
                {loading ? "Sending..." : "Continue"}
              </button>

              <div className="pt-4 border-t border-slate-200">
                <p className="text-xs text-slate-500 text-center">
                  Remember your password?{" "}
                  <Link to="/login" className="font-semibold text-indigo-600 hover:underline">
                    Login
                  </Link>
                </p>
              </div>
            </div>
          )}

          {/* Step 2: QR Code */}
          {step === 2 && qrData && (
            <div className="space-y-5">
              <div className="text-center">
                <p className="mb-4 text-sm text-slate-600">
                  Scan this QR code with Telegram to verify your identity:
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

              <button
                onClick={() => setStep(3)}
                className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700"
              >
                I've scanned the code
              </button>

              <div className="pt-4 border-t border-slate-200">
                <button
                  onClick={() => setStep(1)}
                  className="w-full text-center text-xs font-semibold text-slate-500 hover:text-slate-700 transition"
                >
                  Back
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Verify OTP */}
          {step === 3 && (
            <div className="space-y-5">
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
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-lg font-bold tracking-widest transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
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
                  onClick={() => setStep(2)}
                  className="w-full text-center text-xs font-semibold text-slate-500 hover:text-slate-700 transition"
                >
                  Back
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Reset Password */}
          {step === 4 && (
            <form className="space-y-5">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  New Password
                </label>
                <div className="relative">
                  <input
                    type={showNewPass ? "text" : "password"}
                    name="new_password"
                    value={form.new_password}
                    onChange={handleChange}
                    placeholder="Min 8 characters"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 pr-12 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                    minLength={8}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPass((p) => !p)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showNewPass ? (
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

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Confirm Password
                </label>
                <div className="relative">
                  <input
                    type={showConfirmPass ? "text" : "password"}
                    name="confirm_password"
                    value={form.confirm_password}
                    onChange={handleChange}
                    placeholder="Repeat password"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 pr-12 text-sm transition focus:border-indigo-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                    minLength={8}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPass((p) => !p)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showConfirmPass ? (
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
                onClick={handleResetPassword}
                disabled={loading}
                className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50"
              >
                {loading ? "Resetting password..." : "Reset Password"}
              </button>

              <div className="pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="w-full text-center text-xs font-semibold text-slate-500 hover:text-slate-700 transition"
                >
                  Back
                </button>
              </div>
            </form>
          )}

          {/* Step 5: Success */}
          {step === 5 && (
            <div className="text-center space-y-5">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
                  <svg className="h-8 w-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div>
                <h2 className="text-2xl font-extrabold text-slate-900">Password reset!</h2>
                <p className="mt-1 text-sm text-slate-500">{successMessage}</p>
              </div>
              <p className="text-xs text-slate-400">Redirecting to login...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

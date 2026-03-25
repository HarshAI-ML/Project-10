import api from "./axios";

export const loginUser = async (payload) => {
  const { data } = await api.post("login/", payload);
  return data;
};

export const registerUser = async (payload) => {
  const { data } = await api.post("register/", payload);
  return data;
};

// ── Telegram OTP Authentication ────────────────────────────────────

export const generateTelegramQR = async (purpose, email = null) => {
  const payload = { purpose };
  if (email) payload.email = email;
  const { data } = await api.post("telegram-otp/generate-qr/", payload);
  return data;
};

export const verifyTelegramOTP = async (refId, otpCode, additionalData = {}) => {
  const payload = {
    ref_id: refId,
    otp_code: otpCode,
    ...additionalData,
  };
  const { data } = await api.post("telegram-otp/verify/", payload);
  return data;
};

export const initiateForgotPassword = async (email) => {
  const { data } = await api.post("forgot-password/", { email });
  return data;
};

export const resetPassword = async (refId, otpCode, newPassword, confirmPassword) => {
  const { data } = await api.post("reset-password/", {
    ref_id: refId,
    otp_code: otpCode,
    new_password: newPassword,
    confirm_password: confirmPassword,
  });
  return data;
};

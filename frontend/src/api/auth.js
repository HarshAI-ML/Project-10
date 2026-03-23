import api from "./axios";

export const loginUser = async (payload) => {
  const { data } = await api.post("login/", payload);
  return data;
};

export const registerUser = async (payload) => {
  const { data } = await api.post("register/", payload);
  return data;
};

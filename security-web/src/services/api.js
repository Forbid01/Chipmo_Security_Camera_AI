import axios from "axios";

export const API_BASE_URL =
  "https://chipmosecuritycameraai-production.up.railway.app";
export const VIDEO_FEED_URL = `${API_BASE_URL}/video_feed`;

// 1. Axios instance үүсгэх
export const api = axios.create({
  baseURL: API_BASE_URL,
});

// Request interceptor: Хүсэлт болгонд Токен автоматаар хавсаргана
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// --- НЭВТРЭХ БОЛОН БҮРТГЭЛ ---

export const loginUser = async (username, password) => {
  const formData = new FormData();
  formData.append("username", username);
  formData.append("password", password);

  // FastAPI OAuth2PasswordRequestForm-д FormData хэрэгтэй байдаг
  const response = await api.post("/token", formData);
  return response.data;
};

// --- НУУЦ ҮГ СЭРГЭЭХ (AUTH) ---

export const forgotPassword = async (email) => {
  const response = await api.post("/auth/forgot-password", { email });
  return response.data;
};

export const verifyCode = async (email, code) => {
  const response = await api.post("/auth/verify-code", { email, code });
  return response.data;
};

export const resetPassword = async (email, code, newPassword) => {
  const response = await api.post("/auth/reset-password", {
    email: email,
    code: code,
    new_password: newPassword,
  });
  return response.data;
};

// --- АДМИН ХЯНАЛТ (ORGANIZATIONS & CAMERAS) ---

// Байгууллагууд
export const getOrganizations = async () => {
  const response = await api.get("/auth/admin/organizations");
  return response.data;
};

export const createOrganization = async (name) => {
  const response = await api.post("/auth/admin/organizations", { name });
  return response.data;
};

export const deleteOrganization = async (id) => {
  const response = await api.delete(`/auth/admin/organizations/${id}`);
  return response.data;
};

// Камерууд
export const getCameras = async () => {
  const response = await api.get("/auth/admin/cameras");
  return response.data;
};

export const addCamera = async (cameraData) => {
  const response = await api.post("/auth/admin/cameras", cameraData);
  return response.data;
};

export const deleteCamera = async (id) => {
  const response = await api.delete(`/auth/admin/cameras/${id}`);
  return response.data;
};

export default api;

import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "https://chipmosecuritycameraai-production.up.railway.app";
export const VIDEO_FEED_URL = `${API_BASE_URL}/video_feed`;
export const getVideoFeedUrl = (cameraId) =>
  cameraId ? `${API_BASE_URL}/video_feed/${cameraId}` : VIDEO_FEED_URL;

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

// --- ХЭРЭГЛЭГЧИЙН МЭДЭЭЛЭЛ ---

export const getUserProfile = async () => {
  const response = await api.get("/users/me");
  return response.data;
};

// --- НУУЦ ҮГ СЭРГЭЭХ (AUTH) ---

export const forgotPassword = async (email) => {
  const response = await api.post("/forgot-password", { email });
  return response.data;
};

export const verifyCode = async (email, code) => {
  const response = await api.post("/verify-code", { email, code });
  return response.data;
};

export const resetPassword = async (email, code, newPassword) => {
  const response = await api.post("/reset-password", {
    email: email,
    code: code,
    new_password: newPassword,
  });
  return response.data;
};

// --- АДМИН ХЯНАЛТ (ORGANIZATIONS & CAMERAS) ---

// Байгууллагууд
export const getOrganizations = async () => {
  const response = await api.get("/admin/organizations");
  return response.data;
};

export const createOrganization = async (name) => {
  const response = await api.post("/admin/organizations", { name });
  return response.data;
};

export const deleteOrganization = async (id) => {
  const response = await api.delete(`/admin/organizations/${id}`);
  return response.data;
};

// Камерууд
export const getCameras = async () => {
  const response = await api.get("/admin/cameras");
  return response.data;
};

export const addCamera = async (cameraData) => {
  const response = await api.post("/admin/cameras", cameraData);
  return response.data;
};

export const deleteCamera = async (id) => {
  const response = await api.delete(`/admin/cameras/${id}`);
  return response.data;
};

export const updateCamera = async (id, data) => {
  const response = await api.put(`/admin/cameras/${id}`, data);
  return response.data;
};

// --- ADMIN PANEL (USERS, STATS, ALERTS) ---

// Хэрэглэгч удирдах
export const getUsers = async () => {
  const response = await api.get("/admin/users");
  return response.data;
};

export const updateUserRole = async (id, role) => {
  const response = await api.put(`/admin/users/${id}/role`, { role });
  return response.data;
};

export const updateUserOrganization = async (id, organizationId) => {
  const response = await api.put(`/admin/users/${id}/organization`, { organization_id: organizationId });
  return response.data;
};

export const deleteUser = async (id) => {
  const response = await api.delete(`/admin/users/${id}`);
  return response.data;
};

// Статистик
export const getAdminStats = async () => {
  const response = await api.get("/admin/stats");
  return response.data;
};

// Alert удирдах
export const getAdminAlerts = async (params = {}) => {
  const response = await api.get("/admin/alerts", { params });
  return response.data;
};

export const markAlertReviewed = async (id) => {
  const response = await api.put(`/admin/alerts/${id}/reviewed`);
  return response.data;
};

export const deleteAlert = async (id) => {
  const response = await api.delete(`/admin/alerts/${id}`);
  return response.data;
};

export default api;

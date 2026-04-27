import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://chipmosecuritycameraai-production.up.railway.app";

// Legacy video URLs (backward compat)
export const VIDEO_FEED_URL = `${API_BASE_URL}/video_feed`;
export const getVideoFeedUrl = (cameraId) =>
  cameraId ? `${API_BASE_URL}/video_feed/${cameraId}` : VIDEO_FEED_URL;

// New v2 video URLs (authenticated)
export const getVideoFeedUrlV2 = (cameraId) =>
  `${API_BASE_URL}/api/v1/video/feed/${cameraId}`;
export const getStoreVideoUrl = (storeId) =>
  `${API_BASE_URL}/api/v1/video/store/${storeId}`;

// Axios instance
export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // httpOnly cookie support
});

// Request interceptor: Attach token from localStorage (fallback for API clients)
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

// Response interceptor: Handle 401 globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      // Redirect to login if not already there
      if (
        window.location.pathname !== "/" &&
        window.location.pathname !== "/login"
      ) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

// ============================================
// AUTH
// ============================================

export const loginUser = async (username, password) => {
  const formData = new FormData();
  formData.append("username", username);
  formData.append("password", password);
  const response = await api.post("/token", formData);
  return response.data;
};

export const registerUser = async (userData) => {
  const response = await api.post("/register", userData);
  return response.data;
};

export const logoutUser = async () => {
  try {
    await api.post("/api/v1/auth/logout");
  } catch (error) {
    console.error(error);
    // Ignore errors on logout
  }
  localStorage.removeItem("token");
  localStorage.removeItem("user");
};

export const getUserProfile = async () => {
  const response = await api.get("/users/me");
  return response.data;
};

// ============================================
// PASSWORD RECOVERY
// ============================================

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
    email,
    code,
    new_password: newPassword,
  });
  return response.data;
};

// ============================================
// STORES (NEW)
// ============================================

export const getStores = async (organizationId = null) => {
  const params = organizationId ? { organization_id: organizationId } : {};
  const response = await api.get("/api/v1/stores", { params });
  return response.data;
};

export const createStore = async (storeData) => {
  // Regular org users hit the self-scoped endpoint; it auto-assigns org_id
  // from the JWT. The super_admin-only /api/v1/stores is for global mgmt.
  const response = await api.post("/api/v1/my/cameras/stores", storeData);
  return response.data;
};

export const updateStore = async (id, data) => {
  const response = await api.put(`/api/v1/my/cameras/stores/${id}`, data);
  return response.data;
};

export const deleteStore = async (id) => {
  const response = await api.delete(`/api/v1/my/cameras/stores/${id}`);
  return response.data;
};

// ============================================
// ADMIN - ORGANIZATIONS
// ============================================

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

// ============================================
// ADMIN - CAMERAS
// ============================================

export const getCameras = async (storeId = null) => {
  const params = storeId ? { store_id: storeId } : {};
  const response = await api.get("/admin/cameras", { params });
  return response.data;
};

export const addCamera = async (cameraData) => {
  const response = await api.post("/admin/cameras", cameraData);
  return response.data;
};

export const updateCamera = async (id, data) => {
  const response = await api.put(`/admin/cameras/${id}`, data);
  return response.data;
};

export const deleteCamera = async (id) => {
  const response = await api.delete(`/admin/cameras/${id}`);
  return response.data;
};

export const getCameraStatus = async (config = {}) => {
  const response = await api.get("/api/v1/cameras/status", config);
  return response.data;
};

// ============================================
// ADMIN - USERS
// ============================================

export const getUsers = async () => {
  const response = await api.get("/admin/users");
  return response.data;
};

export const updateUserRole = async (id, role) => {
  const response = await api.put(`/admin/users/${id}/role`, { role });
  return response.data;
};

export const updateUserOrganization = async (id, organizationId) => {
  const response = await api.put(`/admin/users/${id}/organization`, {
    organization_id: organizationId,
  });
  return response.data;
};

export const deleteUser = async (id) => {
  const response = await api.delete(`/admin/users/${id}`);
  return response.data;
};

// ============================================
// ADMIN - STATS
// ============================================

export const getAdminStats = async () => {
  const response = await api.get("/admin/stats");
  return response.data;
};

// ============================================
// ALERTS
// ============================================

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

// ============================================
// STORE SETTINGS (per-store AI config — RAG / VLM / severity / FPS)
// ============================================

export const getStoreSettings = async (storeId) => {
  const response = await api.get(`/api/v1/stores/${storeId}/settings`);
  return response.data;
};

export const patchStoreSettings = async (storeId, patch) => {
  const response = await api.patch(`/api/v1/stores/${storeId}/settings`, patch);
  return response.data;
};

// ============================================
// VLM ANNOTATIONS (Phase 2)
// ============================================

// Returns the cached Qwen2.5-VL output for an alert. The backend
// persists this asynchronously after the alert is created, so a 404
// just means "not ready yet" — callers should retry, not surface as
// an error.
export const getAlertVlmAnnotation = async (alertId) => {
  try {
    const response = await api.get(`/api/v1/alerts/${alertId}/vlm-annotation`);
    return response.data;
  } catch (err) {
    if (err.response?.status === 404) return null;
    throw err;
  }
};

// ============================================
// RAG CORPUS (Phase 1)
// ============================================

export const listRagCorpus = async (storeId, params = {}) => {
  const response = await api.get(
    `/api/v1/stores/${storeId}/rag-corpus`,
    { params },
  );
  return response.data;
};

export const createRagCorpus = async (storeId, payload) => {
  const response = await api.post(
    `/api/v1/stores/${storeId}/rag-corpus`,
    payload,
  );
  return response.data;
};

export const deleteRagCorpus = async (docId) => {
  const response = await api.delete(`/api/v1/rag-corpus/${docId}`);
  return response.data;
};

// ============================================
// MY CAMERAS (User-level camera management)
// ============================================

export const getMyCameras = async () => {
  const response = await api.get("/api/v1/my/cameras");
  return response.data;
};

export const getMyStores = async () => {
  const response = await api.get("/api/v1/my/cameras/stores");
  return response.data;
};

export const addMyCamera = async (cameraData) => {
  const response = await api.post("/api/v1/my/cameras", cameraData);
  return response.data;
};

export const updateMyCamera = async (id, data) => {
  const response = await api.put(`/api/v1/my/cameras/${id}`, data);
  return response.data;
};

export const deleteMyCamera = async (id) => {
  const response = await api.delete(`/api/v1/my/cameras/${id}`);
  return response.data;
};

// ============================================
// AI FEEDBACK & AUTO-LEARNING (NEW)
// ============================================

export const submitAlertFeedback = async (
  alertId,
  feedbackType,
  notes = null,
) => {
  const response = await api.post("/api/v1/feedback", {
    alert_id: alertId,
    feedback_type: feedbackType, // "true_positive" | "false_positive"
    notes,
  });
  return response.data;
};

export const getFeedbackStats = async (storeId = null) => {
  const params = storeId ? { store_id: storeId } : {};
  const response = await api.get("/api/v1/feedback/stats", { params });
  return response.data;
};

export const getLearningStatus = async (storeId = null) => {
  const params = storeId ? { store_id: storeId } : {};
  const response = await api.get("/api/v1/feedback/learning-status", {
    params,
  });
  return response.data;
};

// ============================================
// TELEGRAM NOTIFICATIONS
// ============================================

export const setupTelegram = async (storeId, chatId) => {
  const response = await api.post("/api/v1/telegram/setup", {
    store_id: storeId,
    chat_id: chatId,
  });
  return response.data;
};

export const testTelegram = async (storeId, chatId) => {
  const response = await api.post("/api/v1/telegram/test", {
    store_id: storeId,
    chat_id: chatId,
  });
  return response.data;
};

export const removeTelegram = async (storeId) => {
  const response = await api.delete(`/api/v1/telegram/${storeId}`);
  return response.data;
};

// ============================================
// CONTACT
// ============================================

export const sendContactForm = async (formData) => {
  const response = await api.post("/api/contact", formData);
  return response.data;
};

export default api;

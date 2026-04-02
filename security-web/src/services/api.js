import axios from "axios";

export const API_BASE_URL = "http://192.168.0.246:8000";
export const VIDEO_FEED_URL = `${API_BASE_URL}/video_feed`;

// 1. Axios instance үүсгэх
export const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// --- НУУЦ ҮГ СЭРГЭЭХ (AUTH) АПИ-УУД ---

/**
 * 1. Имэйл рүү OTP код илгээх хүсэлт
 */
export const forgotPassword = async (email) => {
  try {
    const response = await api.post("/forgot-password", { email });
    return response.data;
  } catch (error) {
    throw error.response?.data || error.message;
  }
};

/**
 * 2. Хэрэглэгчийн оруулсан кодыг баталгаажуулах
 */
export const verifyCode = async (email, code) => {
  try {
    const response = await api.post("/verify-code", { email, code });
    return response.data;
  } catch (error) {
    throw error.response?.data || error.message;
  }
};

/**
 * 3. Шинэ нууц үгийг хадгалах
 */
export const resetPassword = async (email, code, newPassword) => {
  try {
    const response = await api.post("/reset-password", {
      email: email,
      code: code,
      new_password: newPassword, // Бэкенд дээр "new_password" гэж байгааг анхаарна уу
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || error.message;
  }
};

export default api;

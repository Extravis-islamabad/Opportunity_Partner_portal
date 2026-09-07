import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { logger } from '@/utils/logger';
import type { ErrorResponse } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// Endpoints where a 401 is the real answer, not an expired access token.
// Logging in with a wrong password, replaying a stale MFA challenge, or
// calling /auth/refresh without a valid cookie all legitimately return 401.
// Running those through the refresh-and-retry path below would swallow the
// server's actual message and hard-redirect to /login, so the user sees a
// page reload instead of "Invalid email or password".
const NO_REFRESH_PATHS = [
  '/auth/login',
  '/auth/login/mfa',
  '/auth/refresh',
  '/auth/forgot-password',
  '/auth/reset-password',
  '/auth/activate',
];

const skipsRefresh = (url?: string): boolean => {
  if (!url) return false;
  const path = url.replace(API_BASE_URL, '');
  return NO_REFRESH_PATHS.some((p) => path.startsWith(p));
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ErrorResponse>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !skipsRefresh(originalRequest?.url)
    ) {
      originalRequest._retry = true;

      try {
        const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {}, {
          withCredentials: true,
        });
        const newAccessToken = response.data.access_token as string;
        localStorage.setItem('access_token', newAccessToken);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        }
        return apiClient(originalRequest);
      } catch (refreshError) {
        logger.error('Token refresh failed', refreshError);
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;

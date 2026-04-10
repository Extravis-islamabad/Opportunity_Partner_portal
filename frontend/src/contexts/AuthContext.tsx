import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { Modal } from 'antd';
import type { UserBasic } from '@/types';
import { authApi } from '@/api/endpoints';
import { logger } from '@/utils/logger';

interface AuthContextType {
  user: UserBasic | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Decode the payload of a JWT without verifying signature.
 * Returns the parsed JSON payload or null on failure.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

const SESSION_WARNING_BEFORE_MS = 5 * 60 * 1000; // 5 minutes

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserBasic | null>(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      try {
        return JSON.parse(stored) as UserBasic;
      } catch {
        return null;
      }
    }
    return null;
  });
  const [isLoading, setIsLoading] = useState(true);
  const expiryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modalRef = useRef<ReturnType<typeof Modal.confirm> | null>(null);

  const isAuthenticated = user !== null && !!localStorage.getItem('access_token');

  const clearExpiryTimer = useCallback(() => {
    if (expiryTimerRef.current) {
      clearTimeout(expiryTimerRef.current);
      expiryTimerRef.current = null;
    }
    if (modalRef.current) {
      modalRef.current.destroy();
      modalRef.current = null;
    }
  }, []);

  const scheduleExpiryWarning = useCallback((accessToken: string) => {
    clearExpiryTimer();

    const payload = decodeJwtPayload(accessToken);
    if (!payload || typeof payload.exp !== 'number') return;

    const expiresAtMs = payload.exp * 1000;
    const warningAtMs = expiresAtMs - SESSION_WARNING_BEFORE_MS;
    const delayMs = warningAtMs - Date.now();

    if (delayMs <= 0) {
      // Token already within the warning window or expired -- skip warning
      return;
    }

    expiryTimerRef.current = setTimeout(() => {
      modalRef.current = Modal.confirm({
        title: 'Your session is about to expire',
        content: 'Your session will expire soon. Would you like to continue your session?',
        okText: 'Continue Session',
        cancelText: 'Log Out',
        onOk: async () => {
          try {
            const response = await authApi.refresh();
            const newToken = response.data.access_token;
            localStorage.setItem('access_token', newToken);
            scheduleExpiryWarning(newToken);
          } catch {
            logger.error('Failed to refresh session from expiry warning');
            localStorage.removeItem('access_token');
            localStorage.removeItem('user');
            setUser(null);
            clearExpiryTimer();
            window.location.href = '/login';
          }
        },
        onCancel: async () => {
          try {
            await authApi.logout();
          } catch (err) {
            logger.error('Logout error', err);
          } finally {
            localStorage.removeItem('access_token');
            localStorage.removeItem('user');
            setUser(null);
            clearExpiryTimer();
          }
        },
      });
    }, delayMs);
  }, [clearExpiryTimer]);

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const response = await authApi.getMe();
      setUser(response.data);
      localStorage.setItem('user', JSON.stringify(response.data));
    } catch {
      setUser(null);
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  // On mount, if there's an existing access_token schedule the warning
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      scheduleExpiryWarning(token);
    }
    return () => clearExpiryTimer();
  }, [scheduleExpiryWarning, clearExpiryTimer]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login({ email, password });
    const { access_token, user: userData } = response.data;
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
    scheduleExpiryWarning(access_token);
  }, [scheduleExpiryWarning]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (err) {
      logger.error('Logout error', err);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      setUser(null);
      clearExpiryTimer();
    }
  }, [clearExpiryTimer]);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, isLoading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

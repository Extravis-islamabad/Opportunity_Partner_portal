import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { LoginResponse, UserBasic } from '@/types';
import { isMfaChallenge } from '@/types';
import { authApi } from '@/api/endpoints';
import { logger } from '@/utils/logger';

/**
 * What a password step produced. On an account with a second factor the
 * password is only half the answer, so login() can return without a session —
 * the caller then has to ask for a code and call completeMfaLogin().
 */
export type LoginResult =
  | { mfaRequired: false }
  | { mfaRequired: true; challengeToken: string };

interface AuthContextType {
  user: UserBasic | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  completeMfaLogin: (challengeToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

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

  const isAuthenticated = user !== null && !!localStorage.getItem('access_token');

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

  // Session lifetime is governed by inactivity (components/common/IdleTimeout),
  // not by the access token's expiry: an expired token is refreshed silently
  // by the API client on the next request.

  // Shared by the plain login and the second-factor completion, so a session
  // established after MFA is exactly the session established without it.
  const startSession = useCallback((data: LoginResponse) => {
    const { access_token, user: userData } = data;
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const response = await authApi.login({ email, password });
    if (isMfaChallenge(response.data)) {
      // Deliberately nothing stored: the challenge token is not a session, and
      // parking it in localStorage would turn a half-finished login into one.
      return { mfaRequired: true, challengeToken: response.data.challenge_token };
    }
    startSession(response.data);
    return { mfaRequired: false };
  }, [startSession]);

  const completeMfaLogin = useCallback(async (challengeToken: string, code: string) => {
    const response = await authApi.completeMfaLogin(challengeToken, code);
    startSession(response.data);
  }, [startSession]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (err) {
      logger.error('Logout error', err);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated, isLoading, login, completeMfaLogin, logout, refreshUser }}
    >
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

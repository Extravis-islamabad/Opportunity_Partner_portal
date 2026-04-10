import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ConfigProvider, theme as antdTheme } from 'antd';

type ThemeMode = 'light' | 'dark';

interface ThemeContextValue {
  mode: ThemeMode;
  isDark: boolean;
  toggle: () => void;
  setMode: (mode: ThemeMode) => void;
}

const STORAGE_KEY = 'portal_theme';

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function readInitialMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // localStorage may be unavailable (private mode)
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(readInitialMode);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const toggle = useCallback(() => {
    setMode(mode === 'dark' ? 'light' : 'dark');
  }, [mode, setMode]);

  // Reflect mode as a data-attribute on the <html> element so global CSS can
  // style scrollbars, body background, etc.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset['theme'] = mode;
    document.body.style.backgroundColor = mode === 'dark' ? '#0e1116' : '#f5f5f5';
  }, [mode]);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, isDark: mode === 'dark', toggle, setMode }),
    [mode, toggle, setMode],
  );

  const antdConfig = useMemo(
    () => ({
      algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        // Royal Blue 500 — primary action color (CTAs, links, focus rings)
        colorPrimary: '#3750ed',
        colorLink: '#3750ed',
        colorLinkHover: '#4961f1',
        colorLinkActive: '#3750ed',
        colorInfo: '#3750ed',
        // Royal Blue 50 — subtle hover/selected backgrounds
        controlItemBgHover: '#e7e7f1',
        controlItemBgActive: '#e7e7f1',
        controlOutline: 'rgba(55, 80, 237, 0.16)',
        borderRadius: 6,
        fontFamily:
          "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      components: {
        Button: {
          colorPrimary: '#3750ed',
          colorPrimaryHover: '#4961f1',
          colorPrimaryActive: '#3750ed',
          primaryShadow: '0 2px 0 rgba(55, 80, 237, 0.12)',
        },
        Menu: {
          // Dark sider menu — keep dark navy background, white active text
          darkItemBg: '#1c1c3a',
          darkItemSelectedBg: '#3750ed',
          darkItemSelectedColor: '#ffffff',
          darkItemColor: '#b4b6f7',
          darkItemHoverBg: 'rgba(55, 80, 237, 0.18)',
          darkItemHoverColor: '#ffffff',
        },
        Layout: {
          siderBg: '#1c1c3a',
          triggerBg: '#1c1c3a',
        },
        Tag: {
          defaultBg: '#f0e6ff',
          defaultColor: '#5b1965',
        },
      },
    }),
    [mode],
  );

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider theme={antdConfig}>{children}</ConfigProvider>
    </ThemeContext.Provider>
  );
};

export const useAppTheme = (): ThemeContextValue => {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useAppTheme must be used within a ThemeProvider');
  }
  return ctx;
};

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Modal, Progress, Typography } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

/**
 * Sign the user out after a stretch of inactivity — and only then.
 *
 * The session used to warn on a timer counted from the access token's
 * expiry, so someone working steadily in the portal was still asked to
 * "continue" ten minutes after logging in. What matters is whether they are
 * still at the keyboard: after IDLE_MINUTES with no input, a 15-second
 * countdown appears, and if nobody answers it they are signed out.
 *
 * The last-activity time lives in localStorage so every open tab shares it:
 * working in one tab keeps the others signed in, and "Stay signed in" in one
 * tab closes the countdown in all of them.
 */
const IDLE_MINUTES = Number(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES) || 15;
const IDLE_MS = IDLE_MINUTES * 60 * 1000;
const COUNTDOWN_SECONDS = 15;
const STORAGE_KEY = 'last_activity_at';
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'wheel'] as const;
// Writing to localStorage on every mousemove is wasteful; once a few seconds
// is plenty when the timeout is measured in minutes.
const WRITE_THROTTLE_MS = 5000;

function readLastActivity(): number {
  try {
    const v = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(v) && v > 0 ? v : Date.now();
  } catch {
    return Date.now();
  }
}

function writeLastActivity(at: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(at));
  } catch {
    // Storage unavailable: each tab simply tracks itself via the ref below.
  }
}

const IdleTimeout: React.FC = () => {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const lastActivityRef = useRef<number>(Date.now());
  const lastWriteRef = useRef<number>(0);
  const warningRef = useRef(false);
  const loggingOutRef = useRef(false);

  const markActive = useCallback((force = false) => {
    const now = Date.now();
    lastActivityRef.current = now;
    if (force || now - lastWriteRef.current > WRITE_THROTTLE_MS) {
      lastWriteRef.current = now;
      writeLastActivity(now);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return undefined;
    loggingOutRef.current = false;
    markActive(true);

    // Ignore input while the countdown is showing: brushing the mouse should
    // not silently cancel it — the user answers it with the button.
    const onActivity = () => {
      if (!warningRef.current) markActive();
    };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));

    const tick = window.setInterval(() => {
      const last = Math.max(lastActivityRef.current, readLastActivity());
      const idleFor = Date.now() - last;
      if (idleFor < IDLE_MS) {
        if (warningRef.current) {
          warningRef.current = false;
          setSecondsLeft(null);
        }
        return;
      }
      const remaining = COUNTDOWN_SECONDS - Math.floor((idleFor - IDLE_MS) / 1000);
      if (remaining <= 0) {
        if (loggingOutRef.current) return;
        loggingOutRef.current = true;
        warningRef.current = false;
        setSecondsLeft(null);
        // Via sessionStorage, not the URL: clearing the session makes the
        // route guard redirect to /login straight away, dropping any query.
        try {
          sessionStorage.setItem('signed_out_reason', 'idle');
        } catch {
          // The login page just won't explain itself.
        }
        void logout().finally(() => navigate('/login', { replace: true }));
        return;
      }
      warningRef.current = true;
      setSecondsLeft(remaining);
    }, 1000);

    return () => {
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, onActivity));
      window.clearInterval(tick);
    };
  }, [isAuthenticated, logout, navigate, markActive]);

  const stay = () => {
    warningRef.current = false;
    setSecondsLeft(null);
    markActive(true);
  };

  const signOutNow = () => {
    loggingOutRef.current = true;
    warningRef.current = false;
    setSecondsLeft(null);
    void logout().finally(() => navigate('/login', { replace: true }));
  };

  return (
    <Modal
      open={secondsLeft !== null}
      closable={false}
      maskClosable={false}
      keyboard={false}
      centered
      width={400}
      title={<><ClockCircleOutlined style={{ marginRight: 8 }} />Are you still there?</>}
      footer={[
        <Button key="out" onClick={signOutNow}>Log Out</Button>,
        <Button key="stay" type="primary" onClick={stay} autoFocus>Stay Signed In</Button>,
      ]}
    >
      <Typography.Paragraph>
        You've been inactive for {IDLE_MINUTES} minute{IDLE_MINUTES === 1 ? '' : 's'}. For your security you will be
        signed out in <strong>{secondsLeft ?? 0}</strong> second{secondsLeft === 1 ? '' : 's'}.
      </Typography.Paragraph>
      <Progress
        percent={((secondsLeft ?? 0) / COUNTDOWN_SECONDS) * 100}
        showInfo={false}
        status="active"
        strokeColor={{ from: '#faad14', to: '#ff4d4f' }}
      />
    </Modal>
  );
};

export default IdleTimeout;

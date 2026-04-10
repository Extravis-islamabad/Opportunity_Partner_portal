import React, { useState } from 'react';
import { Form, Input, Button, Typography, Alert, Checkbox } from 'antd';
import {
  MailOutlined,
  LockOutlined,
  ThunderboltFilled,
  TrophyOutlined,
  SafetyCertificateOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const { Title, Text, Paragraph } = Typography;

const features = [
  {
    icon: <RocketOutlined />,
    title: 'Accelerate Deal Flow',
    description: 'Register opportunities and track every deal from lead to close.',
  },
  {
    icon: <TrophyOutlined />,
    title: 'Tier-Based Rewards',
    description: 'Climb the partner tiers and unlock higher commission rates.',
  },
  {
    icon: <SafetyCertificateOutlined />,
    title: 'Certified Training',
    description: 'Complete LMS modules and earn certifications recognized across the network.',
  },
];

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as Record<string, string>)?.from || '/dashboard';

  const onFinish = async (values: { email: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await login(values.email, values.password);
      navigate(from, { replace: true });
    } catch (err) {
      const axiosError = err as AxiosError<ErrorResponse>;
      setError(axiosError.response?.data?.message || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      {/* Background blobs for the brand panel */}
      <div className="login-brand-panel">
        <div className="login-blob login-blob-1" />
        <div className="login-blob login-blob-2" />
        <div className="login-blob login-blob-3" />

        <div className="login-brand-inner">
          <img
            src="/White Gradient@4x-8.png"
            alt="Extravis"
            className="login-brand-logo"
          />

          <Title level={2} style={{ color: '#ffffff', marginTop: 32, marginBottom: 8, fontWeight: 700, lineHeight: 1.2 }}>
            Welcome to the<br />Partner Portal
          </Title>
          <Paragraph style={{ color: 'rgba(255,255,255,0.78)', fontSize: 15, marginBottom: 40, maxWidth: 420 }}>
            Analyze. Automate. Accelerate. Manage opportunities, deals, training and commissions in one place.
          </Paragraph>

          <div className="login-features">
            {features.map((f) => (
              <div className="login-feature" key={f.title}>
                <div className="login-feature-icon">{f.icon}</div>
                <div className="login-feature-text">
                  <div className="login-feature-title">{f.title}</div>
                  <div className="login-feature-desc">{f.description}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="login-brand-footer">
            &copy; {new Date().getFullYear()} Extravis. All rights reserved.
          </div>
        </div>
      </div>

      {/* Form panel */}
      <div className="login-form-panel">
        <div className="login-form-card">
          {/* Mobile-only logo (brand panel hidden under 992px) */}
          <div className="login-mobile-logo">
            <img src="/Black@4x-8.png" alt="Extravis" />
          </div>

          <div className="login-form-header">
            <Title level={3} style={{ marginBottom: 6, color: '#1c1c3a', fontWeight: 700 }}>
              Sign in to your account
            </Title>
            <Text type="secondary" style={{ fontSize: 14 }}>
              Enter your credentials to access the partner portal
            </Text>
          </div>

          {error && (
            <Alert
              message={error}
              type="error"
              showIcon
              closable
              onClose={() => setError(null)}
              style={{ marginBottom: 20 }}
            />
          )}

          <Form
            layout="vertical"
            onFinish={onFinish}
            size="large"
            autoComplete="off"
            requiredMark={false}
          >
            <Form.Item
              name="email"
              label={<span style={{ fontWeight: 500 }}>Work Email</span>}
              rules={[
                { required: true, message: 'Please enter your email' },
                { type: 'email', message: 'Please enter a valid email' },
              ]}
            >
              <Input
                prefix={<MailOutlined style={{ color: '#8c93f1' }} />}
                placeholder="you@company.com"
                style={{ borderRadius: 8, height: 46 }}
              />
            </Form.Item>

            <Form.Item
              name="password"
              label={<span style={{ fontWeight: 500 }}>Password</span>}
              rules={[{ required: true, message: 'Please enter your password' }]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: '#8c93f1' }} />}
                placeholder="••••••••"
                style={{ borderRadius: 8, height: 46 }}
              />
            </Form.Item>

            <div className="login-form-row">
              <Form.Item name="remember" valuePropName="checked" noStyle initialValue={true}>
                <Checkbox>Remember me</Checkbox>
              </Form.Item>
              <Link to="/forgot-password" className="login-forgot-link">
                Forgot password?
              </Link>
            </div>

            <Form.Item style={{ marginTop: 24, marginBottom: 16 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={loading}
                style={{
                  height: 48,
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 15,
                  boxShadow: '0 6px 16px rgba(55, 80, 237, 0.32)',
                }}
                icon={!loading ? <ThunderboltFilled /> : undefined}
              >
                Sign In
              </Button>
            </Form.Item>
          </Form>

          <div className="login-help">
            <Text type="secondary" style={{ fontSize: 13 }}>
              Need access? Contact your administrator or{' '}
              <a href="mailto:support@extravis.co">support@extravis.co</a>
            </Text>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;

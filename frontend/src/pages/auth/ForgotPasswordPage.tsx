import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Space, Result } from 'antd';
import { MailOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { authApi } from '@/api/endpoints';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const { Title, Text } = Typography;

const ForgotPasswordPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const onFinish = async (values: { email: string }) => {
    setLoading(true);
    setError(null);
    try {
      await authApi.forgotPassword(values.email);
      setSent(true);
    } catch (err) {
      const axiosError = err as AxiosError<ErrorResponse>;
      setError(axiosError.response?.data?.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', background: 'linear-gradient(135deg, #001529 0%, #003a70 100%)' }}>
        <Card style={{ width: 420, borderRadius: 12 }}>
          <Result
            status="success"
            title="Check Your Email"
            subTitle="If an account exists with that email, we've sent a password reset link."
            extra={<Link to="/login"><Button type="primary">Back to Login</Button></Link>}
          />
        </Card>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', background: 'linear-gradient(135deg, #001529 0%, #003a70 100%)' }}>
      <Card style={{ width: 420, borderRadius: 12 }}>
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <Title level={3}>Forgot Password</Title>
            <Text type="secondary">Enter your email to receive a reset link</Text>
          </div>
          {error && <Alert message={error} type="error" showIcon closable onClose={() => setError(null)} />}
          <Form layout="vertical" onFinish={onFinish} size="large">
            <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email', message: 'Please enter a valid email' }]}>
              <Input prefix={<MailOutlined />} placeholder="you@company.com" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" block loading={loading}>Send Reset Link</Button>
            </Form.Item>
            <div style={{ textAlign: 'center' }}><Link to="/login">Back to Login</Link></div>
          </Form>
        </Space>
      </Card>
    </div>
  );
};

export default ForgotPasswordPage;

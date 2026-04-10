import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Space, Result } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { authApi } from '@/api/endpoints';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const { Title } = Typography;

const ResetPasswordPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const onFinish = async (values: { password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await authApi.resetPassword(token, values.password);
      setSuccess(true);
    } catch (err) {
      const axiosError = err as AxiosError<ErrorResponse>;
      setError(axiosError.response?.data?.message || 'Reset failed');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', background: 'linear-gradient(135deg, #001529 0%, #003a70 100%)' }}>
        <Card style={{ width: 420, borderRadius: 12 }}>
          <Result status="success" title="Password Reset" subTitle="Your password has been reset successfully."
            extra={<Link to="/login"><Button type="primary">Sign In</Button></Link>} />
        </Card>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', background: 'linear-gradient(135deg, #001529 0%, #003a70 100%)' }}>
      <Card style={{ width: 420, borderRadius: 12 }}>
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}><Title level={3}>Reset Password</Title></div>
          {error && <Alert message={error} type="error" showIcon closable onClose={() => setError(null)} />}
          <Form layout="vertical" onFinish={onFinish} size="large">
            <Form.Item name="password" label="New Password" rules={[{ required: true, min: 8, message: 'Password must be at least 8 characters' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="New password" />
            </Form.Item>
            <Form.Item name="confirm" label="Confirm Password" dependencies={['password']}
              rules={[{ required: true, message: 'Please confirm your password' },
                ({ getFieldValue }) => ({ validator(_, value) { if (!value || getFieldValue('password') === value) return Promise.resolve(); return Promise.reject(new Error('Passwords do not match')); } }),
              ]}>
              <Input.Password prefix={<LockOutlined />} placeholder="Confirm password" />
            </Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" block loading={loading}>Reset Password</Button></Form.Item>
          </Form>
        </Space>
      </Card>
    </div>
  );
};

export default ResetPasswordPage;

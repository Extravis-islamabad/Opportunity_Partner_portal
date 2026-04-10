import React, { useState } from 'react';
import { Card, Form, Input, Button, Descriptions, Tag, Divider, Alert, message, Row, Col } from 'antd';
import { useAuth } from '@/contexts/AuthContext';
import { useMutation } from '@tanstack/react-query';
import { usersApi, authApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const ProfilePage: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [profileError, setProfileError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const profileMut = useMutation({
    mutationFn: (data: { full_name?: string; job_title?: string; phone?: string }) => usersApi.updateProfile(data),
    onSuccess: () => { void refreshUser(); void message.success('Profile updated'); },
    onError: (err: AxiosError<ErrorResponse>) => setProfileError(err.response?.data?.message || 'Failed'),
  });

  const passwordMut = useMutation({
    mutationFn: (data: { current: string; newPass: string }) => authApi.changePassword(data.current, data.newPass),
    onSuccess: () => { passwordForm.resetFields(); void message.success('Password changed'); },
    onError: (err: AxiosError<ErrorResponse>) => setPasswordError(err.response?.data?.message || 'Failed'),
  });

  if (!user) return null;

  return (
    <>
      <PageHeader title="My Profile" />
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={12}>
          <Card title="Account Information">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Name">{user.full_name}</Descriptions.Item>
              <Descriptions.Item label="Email">{user.email}</Descriptions.Item>
              <Descriptions.Item label="Role"><Tag color={user.role === 'admin' ? 'blue' : 'green'}>{user.role.toUpperCase()}</Tag></Descriptions.Item>
              {user.company_name && <Descriptions.Item label="Company">{user.company_name}</Descriptions.Item>}
            </Descriptions>
          </Card>

          <Card title="Update Profile" style={{ marginTop: 16 }}>
            {profileError && <Alert message={profileError} type="error" closable onClose={() => setProfileError(null)} style={{ marginBottom: 16 }} />}
            <Form form={profileForm} layout="vertical" initialValues={{ full_name: user.full_name }}
              onFinish={(v) => profileMut.mutate(v)}>
              <Form.Item name="full_name" label="Full Name" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="job_title" label="Job Title"><Input /></Form.Item>
              <Form.Item name="phone" label="Phone"><Input /></Form.Item>
              <Form.Item><Button type="primary" htmlType="submit" loading={profileMut.isPending}>Update Profile</Button></Form.Item>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Change Password">
            {passwordError && <Alert message={passwordError} type="error" closable onClose={() => setPasswordError(null)} style={{ marginBottom: 16 }} />}
            <Form form={passwordForm} layout="vertical"
              onFinish={(v) => passwordMut.mutate({ current: v.current_password, newPass: v.new_password })}>
              <Form.Item name="current_password" label="Current Password" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="new_password" label="New Password" rules={[{ required: true, min: 8 }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="confirm" label="Confirm New Password" dependencies={['new_password']}
                rules={[{ required: true }, ({ getFieldValue }) => ({ validator(_, value) { if (!value || getFieldValue('new_password') === value) return Promise.resolve(); return Promise.reject(new Error('Passwords do not match')); } })]}>
                <Input.Password />
              </Form.Item>
              <Form.Item><Button type="primary" htmlType="submit" loading={passwordMut.isPending}>Change Password</Button></Form.Item>
            </Form>
          </Card>
        </Col>
      </Row>
    </>
  );
};

export default ProfilePage;

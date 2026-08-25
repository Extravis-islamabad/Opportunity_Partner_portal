/**
 * Setting up, checking and turning off your own second factor.
 *
 * Two things drive the shape of this: enrolment is two steps, so the card has
 * to hold a half-finished setup without pretending the account is protected;
 * and the recovery codes are shown exactly once, so the moment they appear is
 * the only chance anybody has to write them down.
 */
import React, { useState } from 'react';
import { Alert, Button, Card, Form, Input, Modal, Space, Tag, Typography, message } from 'antd';
import { SafetyOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';

import { mfaApi } from '@/api/endpoints';
import type { ErrorResponse, MfaSetupResponse } from '@/types';

const { Paragraph, Text } = Typography;

const failureMessage = (err: unknown, fallback: string) =>
  (err as AxiosError<ErrorResponse>).response?.data?.message || fallback;

const RecoveryCodes: React.FC<{ codes: string[] }> = ({ codes }) => (
  <>
    <Alert
      type="warning"
      showIcon
      message="Save these recovery codes now"
      description={
        'Each one signs you in once if you lose your phone. They are stored ' +
        'hashed, so this is the only time they can be shown.'
      }
      style={{ marginBottom: 16 }}
    />
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
        gap: 8,
        fontFamily: 'monospace',
        fontSize: 15,
      }}
    >
      {codes.map((code) => (
        <Tag key={code} style={{ textAlign: 'center', padding: '4px 0', margin: 0 }}>
          {code}
        </Tag>
      ))}
    </div>
  </>
);

const TwoFactorCard: React.FC = () => {
  const queryClient = useQueryClient();
  const [setup, setSetup] = useState<MfaSetupResponse | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmForm] = Form.useForm();

  const status = useQuery({
    queryKey: ['mfa-status'],
    queryFn: async () => (await mfaApi.status()).data,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['mfa-status'] });

  const beginMut = useMutation({
    mutationFn: async () => (await mfaApi.setup()).data,
    onSuccess: (data) => {
      setError(null);
      setSetup(data);
    },
    onError: (err) => setError(failureMessage(err, 'Could not start setup')),
  });

  const confirmMut = useMutation({
    mutationFn: async (code: string) => (await mfaApi.confirm(code)).data,
    onSuccess: (data) => {
      // A mistyped code before the right one is normal. Leaving its message on
      // screen next to a card that now says "On" reads as a failure.
      setError(null);
      setSetup(null);
      confirmForm.resetFields();
      setCodes(data.recovery_codes);
      void invalidate();
      void message.success('Two-factor authentication is on');
    },
    onError: (err) => setError(failureMessage(err, 'That code was not accepted')),
  });

  const regenerateMut = useMutation({
    mutationFn: async () => (await mfaApi.regenerateRecoveryCodes()).data,
    onSuccess: (data) => {
      setError(null);
      setCodes(data.recovery_codes);
      void invalidate();
    },
    onError: (err) => setError(failureMessage(err, 'Could not issue new codes')),
  });

  const disableMut = useMutation({
    mutationFn: () => mfaApi.disable(),
    onSuccess: () => {
      setError(null);
      setSetup(null);
      setCodes(null);
      void invalidate();
      void message.success('Two-factor authentication turned off');
    },
    onError: (err) => setError(failureMessage(err, 'Could not turn it off')),
  });

  const enabled = status.data?.enabled ?? false;
  const required = status.data?.required ?? false;
  const remaining = status.data?.recovery_codes_remaining ?? 0;

  return (
    <Card
      title={
        <Space>
          <SafetyOutlined />
          Two-Factor Authentication
          {enabled ? <Tag color="success">On</Tag> : <Tag>Off</Tag>}
        </Space>
      }
      style={{ marginTop: 16 }}
      loading={status.isLoading}
    >
      {error && (
        <Alert
          message={error}
          type="error"
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      {required && !enabled && (
        <Alert
          type="warning"
          showIcon
          message="Your role requires two-factor authentication"
          description={
            status.data?.grace_days
              ? `Set it up within ${status.data.grace_days} days of your account being created, ` +
                'or you will not be able to sign in.'
              : 'Set it up now — sign-in without it is no longer allowed.'
          }
          style={{ marginBottom: 16 }}
        />
      )}

      {!enabled && !setup && (
        <>
          <Paragraph type="secondary">
            Add a code from an authenticator app to your password. Nothing changes about
            how you sign in until you have proved a code works.
          </Paragraph>
          <Button type="primary" loading={beginMut.isPending} onClick={() => beginMut.mutate()}>
            Set up
          </Button>
        </>
      )}

      {setup && (
        <>
          <Paragraph>
            Scan this with your authenticator app, then enter the code it shows.
          </Paragraph>
          <div
            style={{ maxWidth: 200, marginBottom: 16 }}
            // The QR is rendered server-side so the secret is never handed to a
            // third-party script, and so no QR library ships in this bundle.
            dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
          />
          <Paragraph type="secondary" style={{ fontSize: 13 }}>
            Cannot scan? Enter this key by hand: <Text code copyable>{setup.secret}</Text>
          </Paragraph>
          <Form
            form={confirmForm}
            layout="inline"
            onFinish={(v: { code: string }) => confirmMut.mutate(v.code)}
          >
            <Form.Item
              name="code"
              rules={[{ required: true, message: 'Enter the 6-digit code' }]}
            >
              <Input placeholder="123456" style={{ width: 140, letterSpacing: 2 }} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={confirmMut.isPending}>
                Confirm
              </Button>
            </Form.Item>
            <Form.Item>
              <Button onClick={() => setSetup(null)}>Cancel</Button>
            </Form.Item>
          </Form>
        </>
      )}

      {enabled && !setup && (
        <>
          <Paragraph type="secondary">
            You will be asked for a code from your authenticator every time you sign in.{' '}
            {remaining} recovery {remaining === 1 ? 'code' : 'codes'} left.
          </Paragraph>
          {remaining <= 2 && (
            <Alert
              type="warning"
              showIcon
              message="You are nearly out of recovery codes"
              description="Issue a fresh set while you can still sign in."
              style={{ marginBottom: 16 }}
            />
          )}
          <Space>
            <Button
              loading={regenerateMut.isPending}
              onClick={() =>
                Modal.confirm({
                  title: 'Issue new recovery codes?',
                  content: 'Your existing codes stop working immediately.',
                  okText: 'Issue new codes',
                  onOk: () => regenerateMut.mutateAsync(),
                })
              }
            >
              New recovery codes
            </Button>
            <Button
              danger
              loading={disableMut.isPending}
              onClick={() =>
                Modal.confirm({
                  title: 'Turn off two-factor authentication?',
                  content: 'Your password alone will sign you in again.',
                  okText: 'Turn it off',
                  okButtonProps: { danger: true },
                  onOk: () => disableMut.mutateAsync(),
                })
              }
            >
              Turn off
            </Button>
          </Space>
        </>
      )}

      <Modal
        open={codes !== null}
        title="Your recovery codes"
        onCancel={() => setCodes(null)}
        onOk={() => setCodes(null)}
        okText="I have saved them"
        cancelButtonProps={{ style: { display: 'none' } }}
        width={520}
      >
        {codes && <RecoveryCodes codes={codes} />}
      </Modal>
    </Card>
  );
};

export default TwoFactorCard;

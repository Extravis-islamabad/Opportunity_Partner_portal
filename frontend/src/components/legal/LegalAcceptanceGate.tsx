import React, { useState } from 'react';
import { Modal, Typography, Checkbox, Space, Alert, Tag, message } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { legalApi } from '@/api/endpoints';

/**
 * Asks a partner to accept the current agreement and NDA.
 *
 * Shown wherever the app is, because a partner who has not accepted cannot
 * register business — the API refuses it — and finding that out at the point
 * of submitting a deal is a bad way to learn. Deliberately *not* a hard block
 * on the whole portal: they can still read, which includes reading this.
 *
 * One document at a time, in the order the API returns them, so each version
 * is accepted deliberately rather than by one tick covering both.
 */
const LegalAcceptanceGate: React.FC = () => {
  const queryClient = useQueryClient();
  const [agreed, setAgreed] = useState(false);

  const { data: pending } = useQuery({
    queryKey: ['legal-pending'],
    queryFn: async () => (await legalApi.pending()).data,
    // Cheap, and the answer changes when somebody publishes a new version.
    refetchInterval: 5 * 60 * 1000,
  });

  const acceptMut = useMutation({
    mutationFn: (documentId: number) => legalApi.accept(documentId),
    onSuccess: () => {
      setAgreed(false);
      void queryClient.invalidateQueries({ queryKey: ['legal-pending'] });
    },
    onError: () => { void message.error('Could not record your acceptance'); },
  });

  const current = pending?.[0];
  if (!current) return null;

  return (
    <Modal
      title={current.title}
      open
      closable={false}
      maskClosable={false}
      keyboard={false}
      okText="Accept"
      okButtonProps={{ disabled: !agreed, loading: acceptMut.isPending }}
      onOk={() => acceptMut.mutate(current.id)}
      // No cancel: there is nothing to do with this dialog except read it and
      // decide. Closing it would just hide the thing blocking their work.
      cancelButtonProps={{ style: { display: 'none' } }}
      width={720}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space>
          <Tag color="blue">{current.label}</Tag>
          <Tag>Version {current.version}</Tag>
        </Space>

        {(pending?.length ?? 0) > 1 && (
          <Alert
            type="info"
            showIcon
            message={`${pending!.length} documents to accept — this is the first.`}
          />
        )}

        <div
          style={{
            maxHeight: 360,
            overflowY: 'auto',
            padding: 12,
            background: '#fafafa',
            borderRadius: 6,
            whiteSpace: 'pre-wrap',
          }}
        >
          <Typography.Text>{current.body}</Typography.Text>
        </div>

        <Checkbox checked={agreed} onChange={(e) => setAgreed(e.target.checked)}>
          I have read and accept the {current.label} (version {current.version})
        </Checkbox>

        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Your acceptance is recorded against this version, with the date. You
          can review what you have accepted from your profile.
        </Typography.Text>
      </Space>
    </Modal>
  );
};

export default LegalAcceptanceGate;

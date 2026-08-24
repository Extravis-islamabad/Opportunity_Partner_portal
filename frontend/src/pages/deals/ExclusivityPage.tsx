import React, { useState } from 'react';
import {
  Card, Table, Tag, Alert, Button, Space, Modal, Input, InputNumber,
  Typography, message, Empty, Radio,
} from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dashboardApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { ExpiringExclusivity, ExtensionRequest } from '@/types';
import dayjs from 'dayjs';

/**
 * Exclusivity about to lapse, and the requests for more time.
 *
 * An exclusivity window blocks every other partner from the same customer, so
 * it is worth something while it is open and worth nothing the day after. Both
 * halves of this page are about that day: what is approaching it, and who has
 * asked to move it. Extending takes the customer away from everyone else for
 * longer, which is why it is a decision rather than a setting.
 */
const statusColors: Record<string, string> = {
  pending: 'orange',
  approved: 'green',
  refused: 'red',
};

const ExclusivityPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const queryClient = useQueryClient();

  const [deciding, setDeciding] = useState<ExtensionRequest | null>(null);
  const [approve, setApprove] = useState(true);
  const [grantedDays, setGrantedDays] = useState<number | null>(null);
  const [note, setNote] = useState('');

  const { data: expiring, isLoading: loadingExpiring, error } = useQuery({
    queryKey: ['exclusivity-expiring'],
    queryFn: async () => (await dashboardApi.listExpiringExclusivity()).data,
  });

  const { data: requests, isLoading: loadingRequests } = useQuery({
    queryKey: ['extension-requests'],
    queryFn: async () => (await dashboardApi.listExtensionRequests()).data,
  });

  const decideMut = useMutation({
    mutationFn: (req: ExtensionRequest) =>
      dashboardApi.decideExtension(req.id, {
        approve,
        // Omitted rather than sent as the requested number: the API grants
        // exactly what was asked for when this is absent.
        ...(approve && grantedDays !== null ? { granted_days: grantedDays } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      }),
    onSuccess: () => {
      setDeciding(null);
      setNote('');
      setGrantedDays(null);
      void queryClient.invalidateQueries({ queryKey: ['extension-requests'] });
      void queryClient.invalidateQueries({ queryKey: ['exclusivity-expiring'] });
      void queryClient.invalidateQueries({ queryKey: ['deals'] });
      void message.success(approve ? 'Extension granted' : 'Extension refused');
    },
    onError: () => { void message.error('Could not record the decision'); },
  });

  if (error) return <Alert type="error" message="Failed to load exclusivity" showIcon />;

  const expiringColumns = [
    { title: 'Customer', dataIndex: 'customer_name' },
    ...(isAdmin ? [{ title: 'Partner', dataIndex: 'company_name' as const }] : []),
    {
      title: 'Value',
      dataIndex: 'estimated_value',
      align: 'right' as const,
      render: (v: string) => `$${Number(v).toLocaleString()}`,
    },
    { title: 'Ends', dataIndex: 'exclusivity_end' },
    {
      title: 'Left',
      dataIndex: 'days_left',
      sorter: (a: ExpiringExclusivity, b: ExpiringExclusivity) => a.days_left - b.days_left,
      render: (days: number) => (
        <Tag color={days <= 3 ? 'red' : 'orange'} icon={<ClockCircleOutlined />}>
          {days === 0 ? 'ends today' : `${days} ${days === 1 ? 'day' : 'days'}`}
        </Tag>
      ),
    },
    {
      title: '',
      key: 'pending',
      render: (_: unknown, row: ExpiringExclusivity) =>
        row.extension_pending ? <Tag color="processing">Extension requested</Tag> : null,
    },
  ];

  const requestColumns = [
    { title: 'Customer', dataIndex: 'customer_name', render: (v: string | null) => v ?? '—' },
    ...(isAdmin ? [{ title: 'Partner', dataIndex: 'company_name' as const, render: (v: string | null) => v ?? '—' }] : []),
    { title: 'Asked by', dataIndex: 'requested_by_name', render: (v: string | null) => v ?? '—' },
    {
      title: 'Asked for',
      dataIndex: 'requested_days',
      render: (d: number, row: ExtensionRequest) =>
        row.granted_days !== null && row.granted_days !== d
          ? <span>{d} days <Typography.Text type="secondary">(granted {row.granted_days})</Typography.Text></span>
          : `${d} days`,
    },
    { title: 'Ends', dataIndex: 'exclusivity_end', render: (v: string | null) => v ?? '—' },
    {
      title: 'Status',
      dataIndex: 'status',
      render: (s: string) => <Tag color={statusColors[s] ?? 'default'}>{s.toUpperCase()}</Tag>,
    },
    {
      title: 'Asked',
      dataIndex: 'created_at',
      render: (v: string) => dayjs(v).format('MMM D, YYYY'),
    },
    ...(isAdmin ? [{
      title: '',
      key: 'actions',
      render: (_: unknown, row: ExtensionRequest) =>
        row.status === 'pending' ? (
          <Button size="small" onClick={() => { setDeciding(row); setApprove(true); setGrantedDays(row.requested_days); }}>
            Decide
          </Button>
        ) : null,
    }] : []),
  ];

  return (
    <>
      <PageHeader
        title="Exclusivity"
        subtitle={isAdmin
          ? 'Windows about to lapse across your partners, and requests for more time'
          : 'Your exclusivity windows that are about to end'}
        breadcrumbs={[{ label: 'Deal Registration', path: '/deals' }, { label: 'Exclusivity' }]}
      />

      <Card
        title="Ending soon"
        style={{ marginBottom: 16 }}
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            once a window lapses another partner can register the same customer
          </Typography.Text>
        }
      >
        <Table
          rowKey="deal_id"
          loading={loadingExpiring}
          dataSource={expiring ?? []}
          columns={expiringColumns}
          pagination={false}
          locale={{ emptyText: <Empty description="No exclusivity window is close to ending" /> }}
        />
      </Card>

      <Card title="Extension requests">
        <Table
          rowKey="id"
          loading={loadingRequests}
          dataSource={requests ?? []}
          columns={requestColumns}
          pagination={false}
          locale={{ emptyText: <Empty description="No extensions have been requested" /> }}
        />
      </Card>

      <Modal
        title="Decide Extension"
        open={deciding !== null}
        onCancel={() => { setDeciding(null); setNote(''); }}
        onOk={() => deciding && decideMut.mutate(deciding)}
        confirmLoading={decideMut.isPending}
        okText={approve ? 'Grant' : 'Refuse'}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            {deciding?.requested_by_name} asked for {deciding?.requested_days} more days on{' '}
            {deciding?.customer_name}, which currently ends {deciding?.exclusivity_end}.
            {deciding?.reason ? ` Reason: ${deciding.reason}` : ''}
          </Typography.Paragraph>
          <Radio.Group value={approve} onChange={(e) => setApprove(e.target.value as boolean)}>
            <Radio.Button value={true}>Grant</Radio.Button>
            <Radio.Button value={false}>Refuse</Radio.Button>
          </Radio.Group>
          {approve && (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text type="secondary">
                Days to grant — the new window runs from the current end date, not from today.
              </Typography.Text>
              <InputNumber
                min={1}
                max={365}
                value={grantedDays}
                onChange={setGrantedDays}
                addonAfter="days"
                style={{ width: 180 }}
              />
            </Space>
          )}
          <Input.TextArea
            rows={3}
            placeholder="Note to the partner (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
          />
        </Space>
      </Modal>
    </>
  );
};

export default ExclusivityPage;

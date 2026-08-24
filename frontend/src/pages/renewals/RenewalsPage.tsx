import React, { useState } from 'react';
import {
  Card, Table, Tag, Alert, Button, Space, Modal, InputNumber, DatePicker,
  Typography, message, Empty, Select,
} from 'antd';
import { ClockCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { renewalsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { UpcomingRenewal } from '@/types';
import dayjs from 'dayjs';

/**
 * Licences coming up for renewal.
 *
 * Raising the renewal from here rather than as a fresh opportunity is the
 * point: the deployment's details carry across, the renewal is linked to the
 * licence it replaces, and a deal registration is created alongside it so the
 * renewal earns commission when it is approved.
 */
const RenewalsPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [days, setDays] = useState<number | undefined>();
  const [raising, setRaising] = useState<UpcomingRenewal | null>(null);
  const [worth, setWorth] = useState<number | null>(null);
  const [closing, setClosing] = useState<dayjs.Dayjs | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['renewals', days],
    queryFn: async () => (await renewalsApi.list(days)).data,
  });

  const createMut = useMutation({
    mutationFn: (row: UpcomingRenewal) =>
      renewalsApi.create(row.license_id, {
        ...(worth !== null ? { worth } : {}),
        ...(closing ? { closing_date: closing.format('YYYY-MM-DD') } : {}),
      }),
    onSuccess: (res) => {
      setRaising(null);
      setWorth(null);
      setClosing(null);
      void queryClient.invalidateQueries({ queryKey: ['renewals'] });
      void message.success('Renewal raised as a draft — review it and submit');
      navigate(`/opportunities/${res.data.id}`);
    },
    onError: () => { void message.error('Could not raise the renewal'); },
  });

  if (error) return <Alert type="error" message="Failed to load renewals" showIcon />;

  const columns = [
    {
      title: 'Customer',
      dataIndex: 'customer_name',
      render: (v: string, row: UpcomingRenewal) => (
        <a onClick={() => navigate(`/opportunities/${row.opportunity_id}`)}>{v}</a>
      ),
    },
    ...(isAdmin ? [{ title: 'Partner', dataIndex: 'company_name' as const, render: (v: string | null) => v ?? '—' }] : []),
    { title: 'Product', dataIndex: 'product', render: (v: string | null) => v ?? '—' },
    {
      title: 'Devices / Nodes',
      key: 'scale',
      render: (_: unknown, row: UpcomingRenewal) =>
        `${row.device_count ?? 0} / ${row.node_count ?? 0}`,
    },
    {
      title: 'Licence Value',
      dataIndex: 'po_value',
      align: 'right' as const,
      render: (v: string | null) => (v ? `$${Number(v).toLocaleString()}` : '—'),
    },
    { title: 'Expires', dataIndex: 'expires_at' },
    {
      title: 'Left',
      dataIndex: 'days_left',
      sorter: (a: UpcomingRenewal, b: UpcomingRenewal) => a.days_left - b.days_left,
      render: (d: number) => (
        <Tag color={d <= 30 ? 'red' : 'orange'} icon={<ClockCircleOutlined />}>
          {d === 0 ? 'expires today' : `${d} ${d === 1 ? 'day' : 'days'}`}
        </Tag>
      ),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, row: UpcomingRenewal) =>
        row.renewal_opportunity_id ? (
          <Button
            size="small"
            type="link"
            onClick={() => navigate(`/opportunities/${row.renewal_opportunity_id}`)}
          >
            Renewal raised
          </Button>
        ) : (
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => {
              setRaising(row);
              setWorth(row.po_value ? Number(row.po_value) : null);
              setClosing(dayjs(row.expires_at));
            }}
          >
            Raise Renewal
          </Button>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Renewals"
        subtitle={isAdmin
          ? 'Licences approaching expiry across your partners'
          : 'Your licences approaching expiry'}
        extra={
          <Select
            placeholder="Next 90 days"
            allowClear
            style={{ width: 170 }}
            value={days}
            onChange={setDays}
            options={[
              { value: 30, label: 'Next 30 days' },
              { value: 90, label: 'Next 90 days' },
              { value: 180, label: 'Next 180 days' },
              { value: 365, label: 'Next year' },
            ]}
          />
        }
      />

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Raise the renewal from the licence"
        description="The deployment's details carry across, the renewal stays linked to the licence it replaces, and a deal registration is created alongside it so the renewal earns commission once approved."
      />

      <Card>
        <Table
          rowKey="license_id"
          loading={isLoading}
          dataSource={data ?? []}
          columns={columns}
          pagination={false}
          locale={{ emptyText: <Empty description="No licence is close to expiring" /> }}
        />
      </Card>

      <Modal
        title="Raise Renewal"
        open={raising !== null}
        onCancel={() => setRaising(null)}
        onOk={() => raising && createMut.mutate(raising)}
        confirmLoading={createMut.isPending}
        okText="Raise"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            A draft renewal for {raising?.customer_name}, plus the deal registration
            that earns the commission. Everything else carries over from the current
            deployment.
          </Typography.Paragraph>
          <div>
            <Typography.Text type="secondary">Value</Typography.Text>
            <InputNumber
              style={{ width: '100%' }}
              min={1}
              value={worth}
              onChange={setWorth}
              prefix="$"
            />
          </div>
          <div>
            <Typography.Text type="secondary">
              Closing date — defaults to the licence expiry, because a renewal
              closing later is a gap in service.
            </Typography.Text>
            <DatePicker
              style={{ width: '100%' }}
              value={closing}
              onChange={setClosing}
            />
          </div>
        </Space>
      </Modal>
    </>
  );
};

export default RenewalsPage;

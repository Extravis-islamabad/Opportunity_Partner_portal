import React, { useState } from 'react';
import { Table, Tag, Space, Alert, Select, Button, Modal, Input, message } from 'antd';
import { CheckOutlined, CloseOutlined, DollarOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { commissionsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import EmptyState from '@/components/common/EmptyState';
import TableSkeleton from '@/components/common/TableSkeleton';
import type { CommissionRead, CommissionStatus } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

const statusColors: Record<CommissionStatus, string> = {
  pending: 'orange',
  approved: 'blue',
  paid: 'green',
  void: 'default',
};

const fmtUsd = (value: string) => `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const CommissionsListPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [actionModal, setActionModal] = useState<{ commission: CommissionRead; action: 'approved' | 'paid' | 'void' } | null>(null);
  const [notes, setNotes] = useState('');
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['commissions', page, statusFilter],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (statusFilter) params['status'] = statusFilter;
      const res = await commissionsApi.list(params);
      return res.data;
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status, notes }: { id: number; status: string; notes?: string }) =>
      commissionsApi.updateStatus(id, status, notes),
    onSuccess: () => {
      setActionModal(null);
      setNotes('');
      void queryClient.invalidateQueries({ queryKey: ['commissions'] });
      void message.success('Commission updated');
    },
    onError: () => {
      void message.error('Failed to update commission');
    },
  });

  const columns: ColumnsType<CommissionRead> = [
    { title: 'Deal', dataIndex: 'deal_customer_name', key: 'deal', render: (v, r) => v ?? `#${r.deal_id}` },
    ...(isAdmin ? [{ title: 'Company', dataIndex: 'company_name' as const, key: 'company' }] : []),
    {
      title: 'Tier',
      dataIndex: 'tier_at_calculation',
      key: 'tier',
      render: (t: string) => <Tag>{t.toUpperCase()}</Tag>,
    },
    { title: 'Rate', dataIndex: 'rate_percentage', key: 'rate', render: (v: string) => `${v}%` },
    { title: 'Deal Value', dataIndex: 'deal_value', key: 'deal_value', render: fmtUsd },
    { title: 'Commission', dataIndex: 'amount', key: 'amount', render: (v: string) => <strong>{fmtUsd(v)}</strong> },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (s: CommissionStatus) => <Tag color={statusColors[s] ?? 'default'}>{s.toUpperCase()}</Tag>,
    },
    {
      title: 'Calculated',
      dataIndex: 'calculated_at',
      key: 'calculated_at',
      render: (d: string) => dayjs(d).format('MMM D, YYYY'),
    },
    ...(isAdmin
      ? [
          {
            title: 'Actions' as const,
            key: 'actions' as const,
            render: (_: unknown, record: CommissionRead) => {
              const canApprove = record.status === 'pending';
              const canPay = record.status === 'approved';
              const canVoid = record.status === 'pending' || record.status === 'approved';
              return (
                <Space size={4}>
                  {canApprove && (
                    <Button
                      type="link"
                      icon={<CheckOutlined />}
                      size="small"
                      onClick={() => setActionModal({ commission: record, action: 'approved' })}
                    >
                      Approve
                    </Button>
                  )}
                  {canPay && (
                    <Button
                      type="link"
                      icon={<DollarOutlined />}
                      size="small"
                      onClick={() => setActionModal({ commission: record, action: 'paid' })}
                    >
                      Mark Paid
                    </Button>
                  )}
                  {canVoid && (
                    <Button
                      type="link"
                      danger
                      icon={<CloseOutlined />}
                      size="small"
                      onClick={() => setActionModal({ commission: record, action: 'void' })}
                    >
                      Void
                    </Button>
                  )}
                </Space>
              );
            },
          },
        ]
      : []),
  ];

  if (error) return <Alert type="error" message="Failed to load commissions" showIcon />;

  return (
    <>
      <PageHeader
        title={isAdmin ? 'All Commissions' : 'My Commissions'}
        subtitle={`${data?.total ?? 0} total`}
      />
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="Status"
          allowClear
          style={{ width: 160 }}
          onChange={setStatusFilter}
          options={[
            { value: 'pending', label: 'Pending' },
            { value: 'approved', label: 'Approved' },
            { value: 'paid', label: 'Paid' },
            { value: 'void', label: 'Void' },
          ]}
        />
      </Space>
      {isLoading ? (
        <TableSkeleton />
      ) : data && data.items.length > 0 ? (
        <Table
          columns={columns}
          dataSource={data.items}
          rowKey="id"
          pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage, showTotal: (t) => `Total ${t}` }}
        />
      ) : (
        <EmptyState
          title="No commissions yet"
          description="Commissions are automatically calculated when a registered deal is approved."
        />
      )}

      <Modal
        title={
          actionModal
            ? `${actionModal.action === 'approved' ? 'Approve' : actionModal.action === 'paid' ? 'Mark as Paid' : 'Void'} Commission`
            : ''
        }
        open={actionModal !== null}
        onCancel={() => {
          setActionModal(null);
          setNotes('');
        }}
        onOk={() =>
          actionModal &&
          statusMutation.mutate({
            id: actionModal.commission.id,
            status: actionModal.action,
            notes: notes || undefined,
          })
        }
        confirmLoading={statusMutation.isPending}
      >
        {actionModal && (
          <>
            <p>
              Commission <strong>{fmtUsd(actionModal.commission.amount)}</strong> for{' '}
              {actionModal.commission.deal_customer_name ?? `deal #${actionModal.commission.deal_id}`}
            </p>
            <Input.TextArea
              rows={3}
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </>
        )}
      </Modal>
    </>
  );
};

export default CommissionsListPage;

import React, { useState } from 'react';
import { Table, Button, Tag, Space, Alert, Modal, Form, Input, InputNumber, DatePicker, message } from 'antd';
import { PlusOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dashboardApi, exportsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import EmptyState from '@/components/common/EmptyState';
import TableSkeleton from '@/components/common/TableSkeleton';
import ExportMenu from '@/components/common/ExportMenu';
import type { DealRegistrationResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

const statusColors: Record<string, string> = { pending: 'orange', approved: 'green', rejected: 'red', expired: 'default' };

const DealsPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isPartner = user?.role === 'partner';
  const queryClient = useQueryClient();

  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const [approveModal, setApproveModal] = useState<number | null>(null);
  const [exclusivityDays, setExclusivityDays] = useState(90);
  const [rejectModal, setRejectModal] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['deals', page],
    queryFn: async () => { const res = await dashboardApi.listDeals({ page, page_size: 20 }); return res.data; },
  });

  const createMut = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      const data = { ...values, expected_close_date: (values['expected_close_date'] as dayjs.Dayjs).format('YYYY-MM-DD') };
      return dashboardApi.createDeal(data);
    },
    onSuccess: () => { setCreateModal(false); createForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['deals'] }); void message.success('Deal registered'); },
  });

  const approveMut = useMutation({
    mutationFn: ({ id, days }: { id: number; days: number }) => dashboardApi.approveDeal(id, days),
    onSuccess: () => { setApproveModal(null); void queryClient.invalidateQueries({ queryKey: ['deals'] }); void message.success('Deal approved'); },
  });

  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => dashboardApi.rejectDeal(id, reason),
    onSuccess: () => { setRejectModal(null); setRejectReason(''); void queryClient.invalidateQueries({ queryKey: ['deals'] }); void message.success('Deal rejected'); },
  });

  const columns: ColumnsType<DealRegistrationResponse> = [
    { title: 'Customer', dataIndex: 'customer_name', key: 'customer' },
    ...(isAdmin ? [{ title: 'Company', dataIndex: 'company_name' as const, key: 'company' }] : []),
    { title: 'Value', dataIndex: 'estimated_value', key: 'value', render: (v: string) => `$${Number(v).toLocaleString()}` },
    { title: 'Close Date', dataIndex: 'expected_close_date', key: 'date' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={statusColors[s] ?? 'default'}>{s.toUpperCase()}</Tag> },
    { title: 'Exclusivity', key: 'excl', render: (_, r) => r.exclusivity_end ? `Until ${r.exclusivity_end}` : '-' },
    ...(isAdmin ? [{
      title: 'Actions' as const, key: 'actions' as const, render: (_: unknown, record: DealRegistrationResponse) => record.status === 'pending' ? (
        <Space>
          <Button type="link" icon={<CheckOutlined />} onClick={() => setApproveModal(record.id)}>Approve</Button>
          <Button type="link" danger icon={<CloseOutlined />} onClick={() => setRejectModal(record.id)}>Reject</Button>
        </Space>
      ) : null,
    }] : []),
  ];

  if (error) return <Alert type="error" message="Failed to load deals" showIcon />;

  return (
    <>
      <PageHeader
        title="Deal Registration"
        subtitle="Register and protect your deals"
        extra={
          <Space>
            <ExportMenu
              filenamePrefix="deals"
              pdf={() => exportsApi.dealsPdf()}
              xlsx={() => exportsApi.dealsXlsx()}
            />
            {isPartner && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
                Register Deal
              </Button>
            )}
          </Space>
        }
      />
      {isLoading ? <TableSkeleton /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }} />
        ) : (
          <EmptyState
            title="No deal registrations"
            description={isPartner
              ? 'Register a deal to protect your pipeline with exclusivity.'
              : 'No deal registrations have been submitted yet.'}
            action={isPartner && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
                Register Deal
              </Button>
            )}
          />
        )
      )}

      <Modal title="Register New Deal" open={createModal} onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()} confirmLoading={createMut.isPending}>
        <Form form={createForm} layout="vertical" onFinish={createMut.mutate}>
          <Form.Item name="customer_name" label="Customer Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="deal_description" label="Deal Description" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="estimated_value" label="Estimated Value (USD)" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} min={0.01} precision={2} /></Form.Item>
          <Form.Item name="expected_close_date" label="Expected Close Date" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="Approve Deal" open={approveModal !== null} onCancel={() => setApproveModal(null)}
        onOk={() => approveModal && approveMut.mutate({ id: approveModal, days: exclusivityDays })} confirmLoading={approveMut.isPending}>
        <p>Set exclusivity window (days):</p>
        <InputNumber min={1} max={365} value={exclusivityDays} onChange={(v) => setExclusivityDays(v ?? 90)} />
      </Modal>

      <Modal title="Reject Deal" open={rejectModal !== null} onCancel={() => { setRejectModal(null); setRejectReason(''); }}
        onOk={() => rejectModal && rejectMut.mutate({ id: rejectModal, reason: rejectReason })}
        confirmLoading={rejectMut.isPending} okButtonProps={{ disabled: !rejectReason.trim() }}>
        <Input.TextArea rows={3} placeholder="Rejection reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
      </Modal>
    </>
  );
};

export default DealsPage;

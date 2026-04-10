import React, { useState } from 'react';
import { Table, Button, Tag, Space, Select, Skeleton, Alert, Empty, Modal, Form, Input, Upload, message } from 'antd';
import { PlusOutlined, UploadOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { docRequestsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { DocRequestResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

const urgencyColors: Record<string, string> = { low: 'blue', medium: 'orange', high: 'red' };
const statusColors: Record<string, string> = { pending: 'orange', fulfilled: 'green', declined: 'red' };

const DocRequestPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isPartner = user?.role === 'partner';
  const queryClient = useQueryClient();

  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const [fulfillModal, setFulfillModal] = useState<number | null>(null);
  const [fulfillFile, setFulfillFile] = useState<File | null>(null);
  const [addToKb, setAddToKb] = useState(false);
  const [declineModal, setDeclineModal] = useState<number | null>(null);
  const [declineReason, setDeclineReason] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['doc-requests', page, statusFilter],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (statusFilter) params['status'] = statusFilter;
      const res = await docRequestsApi.list(params);
      return res.data;
    },
  });

  const createMut = useMutation({
    mutationFn: (values: { description: string; reason: string; urgency: string }) => docRequestsApi.create(values),
    onSuccess: () => { setCreateModal(false); createForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['doc-requests'] }); void message.success('Request submitted'); },
  });

  const fulfillMut = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => docRequestsApi.fulfill(id, file, addToKb),
    onSuccess: () => { setFulfillModal(null); setFulfillFile(null); void queryClient.invalidateQueries({ queryKey: ['doc-requests'] }); void message.success('Request fulfilled'); },
  });

  const declineMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => docRequestsApi.decline(id, reason),
    onSuccess: () => { setDeclineModal(null); setDeclineReason(''); void queryClient.invalidateQueries({ queryKey: ['doc-requests'] }); void message.success('Request declined'); },
  });

  const columns: ColumnsType<DocRequestResponse> = [
    ...(isAdmin ? [{ title: 'Company', dataIndex: 'company_name' as const, key: 'company' }] : []),
    ...(isAdmin ? [{ title: 'Requester', dataIndex: 'requester_name' as const, key: 'requester' }] : []),
    { title: 'Description', dataIndex: 'description', key: 'desc', ellipsis: true },
    { title: 'Urgency', dataIndex: 'urgency', key: 'urgency', render: (u: string) => <Tag color={urgencyColors[u] ?? 'default'}>{u.toUpperCase()}</Tag> },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={statusColors[s] ?? 'default'}>{s.toUpperCase()}</Tag> },
    { title: 'Date', dataIndex: 'created_at', key: 'date', render: (d: string) => dayjs(d).format('MMM D, YYYY') },
    ...(isAdmin ? [{
      title: 'Actions' as const, key: 'actions' as const, render: (_: unknown, record: DocRequestResponse) => record.status === 'pending' ? (
        <Space>
          <Button type="link" icon={<CheckOutlined />} onClick={() => setFulfillModal(record.id)}>Fulfill</Button>
          <Button type="link" danger icon={<CloseOutlined />} onClick={() => setDeclineModal(record.id)}>Decline</Button>
        </Space>
      ) : record.fulfilled_file_url ? (
        <a href={record.fulfilled_file_url} target="_blank" rel="noopener noreferrer">Download</a>
      ) : null,
    }] : []),
  ];

  if (error) return <Alert type="error" message="Failed to load requests" showIcon />;

  return (
    <>
      <PageHeader
        title="Document Requests"
        subtitle={`${data?.total ?? 0} requests`}
        extra={isPartner && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>New Request</Button>}
      />
      <Select placeholder="Status" allowClear style={{ width: 180, marginBottom: 16 }} onChange={setStatusFilter}
        options={[{ value: 'pending', label: 'Pending' }, { value: 'fulfilled', label: 'Fulfilled' }, { value: 'declined', label: 'Declined' }]} />

      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }} />
        ) : <Empty description="No document requests" />
      )}

      <Modal title="Request Document" open={createModal} onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()} confirmLoading={createMut.isPending}>
        <Form form={createForm} layout="vertical" onFinish={createMut.mutate}>
          <Form.Item name="description" label="Document Description" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="reason" label="Reason"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="urgency" label="Urgency" initialValue="medium">
            <Select options={[{ value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="Fulfill Request" open={fulfillModal !== null} onCancel={() => { setFulfillModal(null); setFulfillFile(null); }}
        onOk={() => fulfillFile && fulfillModal && fulfillMut.mutate({ id: fulfillModal, file: fulfillFile })}
        confirmLoading={fulfillMut.isPending} okButtonProps={{ disabled: !fulfillFile }}>
        <Upload beforeUpload={(f) => { setFulfillFile(f); return false; }} maxCount={1}>
          <Button icon={<UploadOutlined />}>Select File</Button>
        </Upload>
        <div style={{ marginTop: 16 }}>
          <label><input type="checkbox" checked={addToKb} onChange={(e) => setAddToKb(e.target.checked)} /> Also add to Knowledge Base</label>
        </div>
      </Modal>

      <Modal title="Decline Request" open={declineModal !== null} onCancel={() => { setDeclineModal(null); setDeclineReason(''); }}
        onOk={() => declineModal && declineMut.mutate({ id: declineModal, reason: declineReason })}
        confirmLoading={declineMut.isPending} okButtonProps={{ disabled: !declineReason.trim() }}>
        <Input.TextArea rows={3} placeholder="Decline reason" value={declineReason} onChange={(e) => setDeclineReason(e.target.value)} />
      </Modal>
    </>
  );
};

export default DocRequestPage;

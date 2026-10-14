import React, { useMemo, useState } from 'react';
import { Table, Button, Tag, Space, Select, Skeleton, Alert, Empty, Modal, Form, Input, Upload, Checkbox, Typography, message } from 'antd';
import { PlusOutlined, UploadOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { docRequestsApi, knowledgeBaseApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { DocRequestResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { KB_CATEGORIES } from '@/utils/kbCategories';

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
  const [kbCategory, setKbCategory] = useState<string>('Extravis');
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

  // Same list the KB page offers: canonical categories plus those in use,
  // which is exactly what the server accepts for kb_category.
  const { data: kbCategories } = useQuery({
    queryKey: ['kb-categories'],
    queryFn: async () => { const res = await knowledgeBaseApi.getCategories(); return res.data; },
    enabled: isAdmin,
  });
  const kbCategoryOptions = useMemo(() => {
    const names = new Set<string>(KB_CATEGORIES);
    kbCategories?.forEach((c) => names.add(c.name));
    return [...names].map((value) => ({ value, label: value }));
  }, [kbCategories]);

  const createMut = useMutation({
    mutationFn: (values: { description: string; reason: string; urgency: string }) => docRequestsApi.create(values),
    onSuccess: () => { setCreateModal(false); createForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['doc-requests'] }); void message.success('Request submitted'); },
  });

  const fulfillMut = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) =>
      docRequestsApi.fulfill(id, file, addToKb, undefined, addToKb ? kbCategory : undefined),
    onSuccess: () => {
      setFulfillModal(null); setFulfillFile(null); setAddToKb(false);
      void queryClient.invalidateQueries({ queryKey: ['doc-requests'] });
      void queryClient.invalidateQueries({ queryKey: ['kb-documents'] });
      void queryClient.invalidateQueries({ queryKey: ['kb-categories'] });
      void message.success('Request fulfilled');
    },
    onError: (err: { response?: { data?: { message?: string } } }) =>
      void message.error(err.response?.data?.message ?? 'Could not fulfil the request'),
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
      title: 'Actions' as const, fixed: 'right' as const, key: 'actions' as const, render: (_: unknown, record: DocRequestResponse) => record.status === 'pending' ? (
        <Space>
          <Button type="link" icon={<CheckOutlined />} onClick={() => setFulfillModal(record.id)}>Fulfill</Button>
          <Button type="link" danger icon={<CloseOutlined />} onClick={() => setDeclineModal(record.id)}>Decline</Button>
        </Space>
      ) : record.fulfilled_file_url ? (
        <a href={record.fulfilled_file_url} target="_blank" rel="noopener noreferrer">Download</a>
      ) : null,
    }] : [{
      // The requester is who the document was for: they need the download
      // link (and the reason, when it was declined) far more than the admin.
      title: 'Document' as const, key: 'document' as const, render: (_: unknown, record: DocRequestResponse) =>
        record.fulfilled_file_url ? (
          <a href={record.fulfilled_file_url} target="_blank" rel="noopener noreferrer">Download</a>
        ) : record.status === 'declined' && record.decline_reason ? (
          <Typography.Text type="secondary">{record.decline_reason}</Typography.Text>
        ) : <Typography.Text type="secondary">—</Typography.Text>,
    }]),
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
          <Table scroll={{ x: 'max-content' }} columns={columns} dataSource={data.items} rowKey="id"
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
          <Checkbox checked={addToKb} onChange={(e) => setAddToKb(e.target.checked)}>Also add to Knowledge Base</Checkbox>
        </div>
        {addToKb && (
          <div style={{ marginTop: 12 }}>
            <div style={{ marginBottom: 4 }}>Knowledge Base category</div>
            <Select style={{ width: '100%' }} value={kbCategory} onChange={setKbCategory} options={kbCategoryOptions} />
          </div>
        )}
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

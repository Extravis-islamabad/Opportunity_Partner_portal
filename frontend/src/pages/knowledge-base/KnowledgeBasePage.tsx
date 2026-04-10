import React, { useState } from 'react';
import { Table, Button, Input, Tag, Space, Select, Skeleton, Alert, Empty, Upload, Modal, Form, message, Popconfirm } from 'antd';
import { UploadOutlined, SearchOutlined, DownloadOutlined, DeleteOutlined, PlusOutlined, FileOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { knowledgeBaseApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { KBDocumentResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

const KnowledgeBasePage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | undefined>();
  const [uploadModal, setUploadModal] = useState(false);
  const [uploadForm] = Form.useForm();
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['kb-documents', page, search, category],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (search) params['search'] = search;
      if (category) params['category'] = category;
      const res = await knowledgeBaseApi.list(params);
      return res.data;
    },
  });

  const { data: categories } = useQuery({
    queryKey: ['kb-categories'],
    queryFn: async () => { const res = await knowledgeBaseApi.getCategories(); return res.data; },
  });

  const uploadMut = useMutation({
    mutationFn: async (values: { title: string; category: string; description: string }) => {
      const formData = new FormData();
      formData.append('title', values.title);
      formData.append('category', values.category);
      if (values.description) formData.append('description', values.description);
      if (uploadFile) formData.append('file', uploadFile);
      return knowledgeBaseApi.uploadDocument(formData);
    },
    onSuccess: () => {
      setUploadModal(false);
      uploadForm.resetFields();
      setUploadFile(null);
      void queryClient.invalidateQueries({ queryKey: ['kb-documents'] });
      void message.success('Document uploaded');
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => knowledgeBaseApi.delete(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['kb-documents'] }); void message.success('Document deleted'); },
  });

  const handleDownload = async (id: number) => {
    const res = await knowledgeBaseApi.download(id);
    window.open(res.data.file_url, '_blank');
  };

  const columns: ColumnsType<KBDocumentResponse> = [
    { title: 'Title', dataIndex: 'title', key: 'title', render: (t: string) => <Space><FileOutlined />{t}</Space> },
    { title: 'Category', dataIndex: 'category', key: 'category', render: (c: string) => <Tag color="blue">{c}</Tag> },
    { title: 'Version', dataIndex: 'version', key: 'version' },
    { title: 'Downloads', dataIndex: 'download_count', key: 'downloads' },
    { title: 'Published', dataIndex: 'published_at', key: 'published', render: (d: string) => dayjs(d).format('MMM D, YYYY') },
    {
      title: 'Actions', key: 'actions', render: (_, record) => (
        <Space>
          <Button type="link" icon={<DownloadOutlined />} onClick={() => void handleDownload(record.id)}>Download</Button>
          {isAdmin && (
            <Popconfirm title="Delete?" onConfirm={() => deleteMut.mutate(record.id)}>
              <Button type="link" danger icon={<DeleteOutlined />}>Delete</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  if (error) return <Alert type="error" message="Failed to load documents" showIcon />;

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        subtitle="Product documents and resources"
        extra={isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadModal(true)}>Upload Document</Button>}
      />
      <Space style={{ marginBottom: 16 }}>
        <Input.Search placeholder="Search..." allowClear onSearch={setSearch} style={{ width: 300 }} prefix={<SearchOutlined />} />
        <Select placeholder="Category" allowClear style={{ width: 200 }} onChange={setCategory}
          options={categories?.map(c => ({ value: c.name, label: `${c.name} (${c.document_count})` })) ?? []} />
      </Space>
      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }} />
        ) : <Empty description="No documents found" />
      )}

      <Modal title="Upload Document" open={uploadModal} onCancel={() => setUploadModal(false)}
        onOk={() => uploadForm.submit()} confirmLoading={uploadMut.isPending}
        okButtonProps={{ disabled: !uploadFile }}>
        <Form form={uploadForm} layout="vertical" onFinish={(v) => uploadMut.mutate(v)}>
          <Form.Item name="title" label="Title" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="category" label="Category" rules={[{ required: true }]}>
            <Select options={[{ value: 'MonetX' }, { value: 'SupportX' }, { value: 'GreenX' }, { value: 'Product Sheets' }, { value: 'Case Studies' }, { value: 'Technical Guides' }]} />
          </Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
          <Upload beforeUpload={(file) => { setUploadFile(file); return false; }} maxCount={1}>
            <Button icon={<UploadOutlined />}>Select File</Button>
          </Upload>
        </Form>
      </Modal>
    </>
  );
};

export default KnowledgeBasePage;

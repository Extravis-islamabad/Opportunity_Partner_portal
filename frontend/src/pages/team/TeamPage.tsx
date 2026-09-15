import React, { useState } from 'react';
import { Table, Button, Input, Tag, Space, Skeleton, Alert, Empty, Modal, Form, message } from 'antd';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { teamApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { UserResponse, TeamMemberCreateRequest, ErrorResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import { AxiosError } from 'axios';

/**
 * A partner's own company roster — add and view the individuals working for
 * this partner. Unlike the admin-only Users page, this is scoped entirely to
 * the caller's own company on the backend, so there is no company picker
 * here: everything created lands under the same company automatically, and
 * admins retain full visibility of it from the company detail page.
 */
const TeamPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['team', page, search],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (search) params['search'] = search;
      const res = await teamApi.list(params);
      return res.data;
    },
  });

  const createMut = useMutation({
    mutationFn: (values: TeamMemberCreateRequest) => teamApi.create(values),
    onSuccess: (res) => {
      setCreateModal(false);
      createForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['team'] });
      // The password never appears here — it went straight to their inbox.
      void message.success(`Team member added — sign-in details were emailed to ${res.data.email}`);
    },
    onError: (err: AxiosError<ErrorResponse>) =>
      void message.error(err.response?.data?.message || 'Failed to add team member'),
  });

  const columns: ColumnsType<UserResponse> = [
    { title: 'Name', dataIndex: 'full_name', key: 'name' },
    { title: 'Email', dataIndex: 'email', key: 'email' },
    { title: 'Contact', dataIndex: 'phone', key: 'phone', render: (v: string | null) => v ?? '—' },
    { title: 'Designation', dataIndex: 'job_title', key: 'job_title', render: (v: string | null) => v ?? '—' },
    { title: 'Department', dataIndex: 'department', key: 'department', render: (v: string | null) => v ?? '—' },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'pending_activation' ? 'orange' : 'red'}>{s.replace(/_/g, ' ').toUpperCase()}</Tag>,
    },
  ];

  if (error) return <Alert type="error" message="Failed to load your team" showIcon />;

  return (
    <>
      <PageHeader
        title="My Team"
        subtitle={`${data?.total ?? 0} people in your company`}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>Add Team Member</Button>}
      />
      <Space style={{ marginBottom: 16 }}>
        <Input.Search placeholder="Search..." allowClear onSearch={setSearch} style={{ width: 300 }} prefix={<SearchOutlined />} />
      </Space>
      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }} />
        ) : <Empty description="No team members yet" />
      )}

      <Modal
        title="Add Team Member"
        open={createModal}
        onCancel={() => { setCreateModal(false); createForm.resetFields(); }}
        onOk={() => createForm.submit()}
        confirmLoading={createMut.isPending}
        okText="Add & Send Login Details"
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" onFinish={createMut.mutate}>
          <Form.Item name="full_name" label="Name" rules={[{ required: true, max: 255 }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="email" label="Email"
            rules={[{ required: true, type: 'email' }]}
            extra="Their login details — including an auto-generated password — are sent here."
          >
            <Input />
          </Form.Item>
          <Form.Item name="contact" label="Contact" rules={[{ required: true, max: 50 }]}>
            <Input />
          </Form.Item>
          <Form.Item name="designation" label="Designation" rules={[{ required: true, max: 255 }]}>
            <Input />
          </Form.Item>
          <Form.Item name="department" label="Department" rules={[{ required: true, max: 255 }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default TeamPage;

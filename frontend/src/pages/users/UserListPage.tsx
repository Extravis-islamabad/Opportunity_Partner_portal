import React, { useState } from 'react';
import { Table, Button, Input, Tag, Space, Select, Skeleton, Alert, Empty, Modal, Form, message, Popconfirm } from 'antd';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi, companiesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { UserResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const UserListPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['users', page, search, roleFilter],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (search) params['search'] = search;
      if (roleFilter) params['role'] = roleFilter;
      const res = await usersApi.list(params);
      return res.data;
    },
  });

  const { data: companies } = useQuery({
    queryKey: ['companies-simple'],
    queryFn: async () => { const res = await companiesApi.list({ page: 1, page_size: 100 }); return res.data; },
  });

  const createMut = useMutation({
    mutationFn: (values: { full_name: string; email: string; role: string; job_title?: string; company_id?: number }) => usersApi.create(values),
    onSuccess: () => { setCreateModal(false); createForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['users'] }); void message.success('User created'); },
    onError: (err: AxiosError<ErrorResponse>) => void message.error(err.response?.data?.message || 'Failed'),
  });

  const deactivateMut = useMutation({
    mutationFn: (id: number) => usersApi.deactivate(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['users'] }); void message.success('User deactivated'); },
  });

  const reactivateMut = useMutation({
    mutationFn: (id: number) => usersApi.reactivate(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['users'] }); void message.success('User reactivated'); },
  });

  const columns: ColumnsType<UserResponse> = [
    { title: 'Name', dataIndex: 'full_name', key: 'name' },
    { title: 'Email', dataIndex: 'email', key: 'email' },
    { title: 'Role', dataIndex: 'role', key: 'role', render: (r: string, record: UserResponse) => (
        <Space size={4}>
          <Tag color={r === 'admin' ? 'blue' : 'green'}>{r.toUpperCase()}</Tag>
          {r === 'admin' && record.is_superadmin && <Tag color="purple">SUPERADMIN</Tag>}
        </Space>
      ),
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'pending_activation' ? 'orange' : 'red'}>{s.replace(/_/g, ' ').toUpperCase()}</Tag> },
    { title: 'Company', dataIndex: 'company_name', key: 'company' },
    {
      title: 'Actions', key: 'actions', render: (_, record) => (
        <Space>
          {record.status === 'active' ? (
            <Popconfirm title="Deactivate?" onConfirm={() => deactivateMut.mutate(record.id)}>
              <Button type="link" danger size="small">Deactivate</Button>
            </Popconfirm>
          ) : record.status === 'inactive' ? (
            <Button type="link" size="small" onClick={() => reactivateMut.mutate(record.id)}>Reactivate</Button>
          ) : null}
        </Space>
      ),
    },
  ];

  if (error) return <Alert type="error" message="Failed to load users" showIcon />;

  return (
    <>
      <PageHeader
        title="Users"
        subtitle={`${data?.total ?? 0} total users`}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>Add User</Button>}
      />
      <Space style={{ marginBottom: 16 }}>
        <Input.Search placeholder="Search..." allowClear onSearch={setSearch} style={{ width: 300 }} prefix={<SearchOutlined />} />
        <Select placeholder="Role" allowClear style={{ width: 150 }} onChange={setRoleFilter}
          options={[{ value: 'admin', label: 'Admin' }, { value: 'partner', label: 'Partner' }]} />
      </Space>
      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }} />
        ) : <Empty description="No users found" />
      )}

      <Modal title="Create User" open={createModal} onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()} confirmLoading={createMut.isPending}>
        <Form form={createForm} layout="vertical" onFinish={createMut.mutate}>
          <Form.Item name="full_name" label="Full Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}><Input /></Form.Item>
          <Form.Item name="role" label="Role" rules={[{ required: true }]}
            extra="Admins can be assigned as Channel Managers when creating or editing a company.">
            <Select options={[{ value: 'admin', label: 'Admin' }, { value: 'partner', label: 'Partner' }]} />
          </Form.Item>
          <Form.Item name="job_title" label="Job Title"><Input /></Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.role !== curr.role}>
            {({ getFieldValue }) => getFieldValue('role') === 'partner' ? (
              <Form.Item name="company_id" label="Company" rules={[{ required: true }]}>
                <Select showSearch optionFilterProp="label"
                  options={companies?.items.map((c: { id: number; name: string }) => ({ value: c.id, label: c.name })) ?? []} />
              </Form.Item>
            ) : null}
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default UserListPage;

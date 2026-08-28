import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Tag, Space, Select, Skeleton, Alert, Empty, Modal, Form, message, Popconfirm } from 'antd';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi, companiesApi, mfaApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import HandoverModal from '@/components/users/HandoverModal';
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
  const [editUser, setEditUser] = useState<UserResponse | null>(null);
  const [editForm] = Form.useForm();
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Deep link from elsewhere in the app: /users?action=create&company_id=12
  // opens the create form with the partner + company already chosen. These
  // params were being ignored, so the link landed on a plain list and looked
  // like the click had done nothing.
  useEffect(() => {
    if (searchParams.get('action') !== 'create') return;
    const companyId = Number(searchParams.get('company_id'));
    setCreateModal(true);
    createForm.setFieldsValue(
      Number.isFinite(companyId) && companyId > 0
        ? { role: 'partner', company_id: companyId }
        : {},
    );
    // Consume them, so a refresh or a back-navigation doesn't reopen the form.
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams, createForm]);

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
    onSuccess: (res) => {
      setCreateModal(false); createForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      // Name the address the activation link went to — the account cannot be
      // used until that mail is acted on.
      void message.success(`User created — an activation email has been sent to ${res.data.email}`);
    },
    onError: (err: AxiosError<ErrorResponse>) => void message.error(err.response?.data?.message || 'Failed'),
  });

  const editMut = useMutation({
    mutationFn: (values: { full_name?: string; job_title?: string; phone?: string; status?: string }) =>
      usersApi.adminUpdate(editUser!.id, values),
    onSuccess: () => {
      setEditUser(null); editForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void message.success('User updated');
    },
    onError: (err: AxiosError<ErrorResponse>) => void message.error(err.response?.data?.message || 'Failed to update user'),
  });

  const openEdit = (u: UserResponse) => {
    setEditUser(u);
    editForm.setFieldsValue({
      full_name: u.full_name,
      job_title: u.job_title ?? undefined,
      phone: (u as unknown as { phone?: string }).phone ?? undefined,
      // Only active/inactive are settable (backend AdminUserUpdateRequest);
      // pending_activation isn't a manual choice.
      status: u.status === 'active' || u.status === 'inactive' ? u.status : undefined,
    });
  };

  const [handingOver, setHandingOver] = useState<UserResponse | null>(null);

  const deactivateMut = useMutation({
    mutationFn: (id: number) => usersApi.deactivate(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['users'] }); void message.success('User deactivated'); },
    onError: (e: unknown, id: number) => {
      const err = e as { response?: { status?: number; data?: { code?: string; message?: string } } };
      // The API refuses to switch off an account that still holds live work.
      // That is not a failure to report and forget — it is the moment to open
      // the handover, which is the thing the admin actually needs to do.
      if (err.response?.data?.code === 'HANDOVER_REQUIRED') {
        const target = data?.items.find((u) => u.id === id) ?? null;
        setHandingOver(target);
        void message.warning(err.response.data.message ?? 'Hand the work over first');
        return;
      }
      void message.error(err.response?.data?.message ?? 'Could not deactivate the user');
    },
  });

  const reactivateMut = useMutation({
    mutationFn: (id: number) => usersApi.reactivate(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['users'] }); void message.success('User reactivated'); },
  });

  // The lockout escape hatch: somebody has lost both their phone and their
  // recovery codes, and the alternative to this button is a database edit.
  const resetMfaMut = useMutation({
    mutationFn: (id: number) => mfaApi.resetForUser(id),
    onSuccess: (res) => void message.success(res.data.message),
    onError: (err: AxiosError<ErrorResponse>) =>
      void message.error(err.response?.data?.message || 'Could not reset two-factor authentication'),
  });

  const columns: ColumnsType<UserResponse> = [
    { title: 'Name', dataIndex: 'full_name', key: 'name' },
    { title: 'Email', dataIndex: 'email', key: 'email' },
    { title: 'Role', dataIndex: 'role', key: 'role', render: (r: string, record: UserResponse) => (
        <Space size={4}>
          <Tag color={r === 'admin' ? 'blue' : r === 'sales_rep' ? 'geekblue' : 'green'}>
            {r.replace(/_/g, ' ').toUpperCase()}
          </Tag>
          {r === 'admin' && record.is_superadmin && <Tag color="purple">SUPERADMIN</Tag>}
        </Space>
      ),
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'pending_activation' ? 'orange' : 'red'}>{s.replace(/_/g, ' ').toUpperCase()}</Tag> },
    { title: 'Company', dataIndex: 'company_name', key: 'company' },
    {
      title: 'Actions', key: 'actions', render: (_, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(record)}>Edit</Button>
          {record.status === 'active' && (
            <Button type="link" size="small" onClick={() => setHandingOver(record)}>
              Hand over
            </Button>
          )}
          {currentUser?.is_superadmin && (
            <Popconfirm
              title="Reset two-factor authentication?"
              description="They will sign in with their password alone until they set it up again."
              onConfirm={() => resetMfaMut.mutate(record.id)}
            >
              <Button type="link" size="small">Reset 2FA</Button>
            </Popconfirm>
          )}
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
          options={[
            { value: 'admin', label: 'Admin' },
            { value: 'sales_rep', label: 'Sales Rep' },
            { value: 'partner', label: 'Partner' },
          ]} />
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
            extra="Admins can be assigned as Channel Managers when creating or editing a company. Sales reps drive POC and deployment for the opportunities they're assigned to.">
            <Select options={[
              { value: 'admin', label: 'Admin' },
              { value: 'sales_rep', label: 'Sales Rep' },
              { value: 'partner', label: 'Partner' },
            ]} />
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

      <Modal
        title={`Edit User — ${editUser?.full_name ?? ''}`}
        open={!!editUser}
        onCancel={() => { setEditUser(null); editForm.resetFields(); }}
        onOk={() => editForm.submit()}
        confirmLoading={editMut.isPending}
        okText="Save"
      >
        <Form form={editForm} layout="vertical" onFinish={editMut.mutate}>
          <Form.Item name="full_name" label="Full Name" rules={[{ required: true, max: 255 }]}><Input /></Form.Item>
          <Form.Item name="job_title" label="Job Title"><Input maxLength={255} /></Form.Item>
          <Form.Item name="phone" label="Phone"><Input maxLength={50} /></Form.Item>
          <Form.Item name="status" label="Status" extra="Email and role are fixed after creation.">
            <Select
              allowClear
              options={[
                { value: 'active', label: 'Active' },
                { value: 'inactive', label: 'Inactive' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
      <HandoverModal
        user={handingOver}
        // Everyone on this page is a candidate; the API refuses one who
        // cannot hold what is being moved, and says why.
        candidates={data?.items ?? []}
        onClose={() => setHandingOver(null)}
      />
    </>
  );
};

export default UserListPage;

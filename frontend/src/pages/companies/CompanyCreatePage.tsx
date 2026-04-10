import React, { useState } from 'react';
import { Form, Input, Select, Button, Card, Alert, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { companiesApi, usersApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { CompanyCreateRequest } from '@/types';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const CompanyCreatePage: React.FC = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const { data: admins } = useQuery({
    queryKey: ['admins-list'],
    queryFn: async () => { const res = await usersApi.getAdmins(); return res.data; },
  });

  const mutation = useMutation({
    mutationFn: (data: CompanyCreateRequest) => companiesApi.create(data),
    onSuccess: (res) => { void message.success('Company created'); navigate(`/companies/${res.data.id}`); },
    onError: (err: AxiosError<ErrorResponse>) => setError(err.response?.data?.message || 'Failed to create company'),
  });

  return (
    <>
      <PageHeader title="Create Company" breadcrumbs={[{ label: 'Companies', path: '/companies' }, { label: 'Create' }]} />
      {error && <Alert message={error} type="error" showIcon closable onClose={() => setError(null)} style={{ marginBottom: 16 }} />}
      <Card style={{ maxWidth: 600 }}>
        <Form form={form} layout="vertical" onFinish={(values: CompanyCreateRequest) => mutation.mutate(values)}>
          <Form.Item name="name" label="Company Name" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Company name" maxLength={255} />
          </Form.Item>
          <Form.Item name="country" label="Country" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Country" maxLength={100} />
          </Form.Item>
          <Form.Item name="region" label="Region" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Region" maxLength={100} />
          </Form.Item>
          <Form.Item name="city" label="City" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="City" maxLength={100} />
          </Form.Item>
          <Form.Item name="industry" label="Industry" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Industry" maxLength={255} />
          </Form.Item>
          <Form.Item name="contact_email" label="Contact Email" rules={[{ required: true, type: 'email', message: 'Valid email required' }]}>
            <Input placeholder="contact@company.com" />
          </Form.Item>
          <Form.Item name="channel_manager_id" label="Channel Manager" rules={[{ required: true, message: 'Required' }]}>
            <Select placeholder="Select channel manager" showSearch optionFilterProp="label"
              options={admins?.map(a => ({ value: a.id, label: `${a.full_name} (${a.email})` })) ?? []} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={mutation.isPending} style={{ marginRight: 8 }}>Create Company</Button>
            <Button onClick={() => navigate('/companies')}>Cancel</Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default CompanyCreatePage;

import React, { useEffect, useState } from 'react';
import { Form, Input, Select, Button, Card, Alert, message, Skeleton } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { companiesApi, usersApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { CompanyUpdateRequest } from '@/types';
import { COMPANY_TYPE_OPTIONS } from '@/utils/companyType';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const CompanyEditPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const companyId = Number(id);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  // Company type governs what that company's users can reach, so only a
  // superadmin may re-classify — the API rejects it from anyone else.
  const canEditType = !!user?.is_superadmin;
  const [error, setError] = useState<string | null>(null);

  const { data: company, isLoading } = useQuery({
    queryKey: ['company', companyId],
    queryFn: async () => (await companiesApi.get(companyId)).data,
    enabled: !!companyId,
  });

  const { data: admins } = useQuery({
    queryKey: ['admins-list'],
    queryFn: async () => (await usersApi.getAdmins()).data,
  });

  // Hydrate the form once the company loads
  useEffect(() => {
    if (company) {
      form.setFieldsValue({
        name: company.name,
        country: company.country,
        region: company.region,
        city: company.city,
        industry: company.industry,
        contact_email: company.contact_email,
        channel_manager_id: company.channel_manager_id,
        company_type: company.company_type,
      });
    }
  }, [company, form]);

  const mutation = useMutation({
    mutationFn: (data: CompanyUpdateRequest) => companiesApi.update(companyId, data),
    onSuccess: () => {
      void message.success('Company updated');
      void queryClient.invalidateQueries({ queryKey: ['company', companyId] });
      void queryClient.invalidateQueries({ queryKey: ['companies'] });
      navigate(`/companies/${companyId}`);
    },
    onError: (err: AxiosError<ErrorResponse>) => {
      setError(err.response?.data?.message || 'Failed to update company');
    },
  });

  if (isLoading) return <Skeleton active paragraph={{ rows: 8 }} />;

  return (
    <>
      <PageHeader
        title={`Edit ${company?.name ?? 'Company'}`}
        breadcrumbs={[
          { label: 'Companies', path: '/companies' },
          { label: company?.name ?? 'Company', path: `/companies/${companyId}` },
          { label: 'Edit' },
        ]}
      />
      {error && (
        <Alert
          message={error}
          type="error"
          showIcon
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 16 }}
        />
      )}
      <Card style={{ maxWidth: 600 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={(values: CompanyUpdateRequest) => {
            // A disabled Select still submits its value, so a channel manager
            // saving an unrelated edit would send company_type and be refused
            // by the superadmin-only check. Drop it unless they may set it.
            const payload = { ...values };
            if (!canEditType) delete payload.company_type;
            mutation.mutate(payload);
          }}
        >
          <Form.Item name="name" label="Company Name" rules={[{ required: true }]}>
            <Input placeholder="Company name" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="company_type"
            label="Company Type"
            rules={[{ required: true }]}
            extra={
              canEditType
                ? 'Changing this changes what the company\u2019s users can reach — customers lose deal registration, commissions, scorecard and tier.'
                : 'Only a superadmin can change a company\u2019s type.'
            }
          >
            <Select
              disabled={!canEditType}
              placeholder="Select company type"
              options={COMPANY_TYPE_OPTIONS}
            />
          </Form.Item>
          <Form.Item name="country" label="Country" rules={[{ required: true }]}>
            <Input placeholder="Country" maxLength={100} />
          </Form.Item>
          <Form.Item name="region" label="Region" rules={[{ required: true }]}>
            <Input placeholder="Region" maxLength={100} />
          </Form.Item>
          <Form.Item name="city" label="City" rules={[{ required: true }]}>
            <Input placeholder="City" maxLength={100} />
          </Form.Item>
          <Form.Item name="industry" label="Industry" rules={[{ required: true }]}>
            <Input placeholder="Industry" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="contact_email"
            label="Contact Email"
            rules={[{ required: true, type: 'email' }]}
          >
            <Input placeholder="contact@company.com" />
          </Form.Item>
          <Form.Item
            name="channel_manager_id"
            label="Channel Manager"
            rules={[{ required: true, message: 'Required' }]}
            extra="Channel Managers are admin users. Create new admins from the Users page."
          >
            <Select
              placeholder="Select channel manager"
              showSearch
              optionFilterProp="label"
              options={admins?.map((a) => ({
                value: a.id,
                label: `${a.full_name} (${a.email})`,
              })) ?? []}
            />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={mutation.isPending}
              style={{ marginRight: 8 }}
            >
              Save Changes
            </Button>
            <Button onClick={() => navigate(`/companies/${companyId}`)}>Cancel</Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default CompanyEditPage;

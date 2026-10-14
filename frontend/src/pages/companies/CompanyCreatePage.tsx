import React, { useState } from 'react';
import { Form, Input, Select, Button, Card, Alert, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { companiesApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import ParentDistributorSelect from '@/components/companies/ParentDistributorSelect';
import ChannelManagersSelect from '@/components/companies/ChannelManagersSelect';
import type { CompanyCreateRequest } from '@/types';
import { COMPANY_TYPES } from '@/utils/companyType';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';

const CompanyCreatePage: React.FC = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  // A channel manager creating a company is always one of its managers (the
  // API adds them if left off), so start them on the list.
  const initialManagers = user && !user.is_superadmin ? [user.id] : [];

  const mutation = useMutation({
    mutationFn: (data: CompanyCreateRequest) => companiesApi.create(data),
    onSuccess: (res) => {
      // Creating the company also provisions its contact's account and mails
      // an activation link. Say which of those happened — the whole point of
      // the step is invisible otherwise.
      const email = res.data.contact_email;
      switch (res.data.contact_invite) {
        case 'sent':
          void message.success(`Company created — an activation email has been sent to ${email}`);
          break;
        case 'existing_user':
          void message.warning(`Company created. ${email} already has an account, so no invite was sent.`);
          break;
        case 'failed':
          void message.warning(
            `Company created and an account made for ${email}, but the invite email could not be sent — check the Email Log and re-send.`,
          );
          break;
        default:
          void message.success('Company created');
      }
      navigate(`/companies/${res.data.id}`);
    },
    onError: (err: AxiosError<ErrorResponse>) => setError(err.response?.data?.message || 'Failed to create company'),
  });

  return (
    <>
      <PageHeader title="Create Company" breadcrumbs={[{ label: 'Companies', path: '/companies' }, { label: 'Create' }]} />
      {error && <Alert message={error} type="error" showIcon closable onClose={() => setError(null)} style={{ marginBottom: 16 }} />}
      <Card style={{ maxWidth: 600 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ channel_manager_ids: initialManagers }}
          onFinish={(values: CompanyCreateRequest) => mutation.mutate(values)}
        >
          <Form.Item name="name" label="Company Name" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Company name" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="company_type"
            label="Company Type"
            rules={[{ required: true, message: 'Choose how this company is classified' }]}
            extra="Customers get no deal registration, commissions, scorecard or tier. Only a superadmin can change this later."
          >
            <Select
              placeholder="Select company type"
              options={COMPANY_TYPES.map((t) => ({
                value: t.value,
                label: t.label,
                title: t.description,
              }))}
              optionRender={(opt) => {
                const meta = COMPANY_TYPES.find((t) => t.value === opt.value);
                return (
                  <div>
                    <div style={{ fontWeight: 600 }}>{meta?.label}</div>
                    <div style={{ fontSize: 12, opacity: 0.65, whiteSpace: 'normal' }}>
                      {meta?.description}
                    </div>
                  </div>
                );
              }}
            />
          </Form.Item>
          {/* Only a partner can sit under a distributor, so the field appears
              only once that is the chosen type. Form.Item shouldRender via a
              function child so it re-reads company_type as it changes. */}
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.company_type !== cur.company_type}>
            {({ getFieldValue }) =>
              getFieldValue('company_type') === 'partner' ? (
                <Form.Item
                  name="parent_distributor_id"
                  label="Parent Distributor"
                  extra="Leave empty if this partner reports directly to Extravis. A distributor sees the pipeline of every partner underneath it."
                >
                  <ParentDistributorSelect />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="country" label="Country" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Country" maxLength={100} />
          </Form.Item>
          <Form.Item name="region" label="Region">
            <Input placeholder="Region (optional)" maxLength={100} />
          </Form.Item>
          <Form.Item name="city" label="City">
            <Input placeholder="City (optional)" maxLength={100} />
          </Form.Item>
          <Form.Item name="industry" label="Industry" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Industry" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="contact_email" label="Contact Email"
            rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
            extra="A portal account is created for this address and an activation link is emailed to it."
          >
            <Input placeholder="contact@company.com" />
          </Form.Item>
          <Form.Item
            name="contact_name"
            label="Contact Name"
            extra="Optional. Used to greet them in the activation email; the company name is used if left blank."
          >
            <Input placeholder="Primary contact's full name" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="channel_manager_ids"
            label="Channel Managers"
            rules={[{ required: true, type: 'array', min: 1, message: 'Choose at least one channel manager' }]}
            extra="Everyone chosen sees this company and its notifications. The first is the primary manager."
          >
            <ChannelManagersSelect />
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

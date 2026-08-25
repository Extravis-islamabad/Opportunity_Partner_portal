import React, { useEffect, useState } from 'react';
import {
  Form,
  Input,
  InputNumber,
  DatePicker,
  Button,
  Card,
  Alert,
  Skeleton,
  message,
  Select,
} from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { opportunitiesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { OpportunityCreateRequest, ErrorResponse } from '@/types';
import type { AxiosError } from 'axios';
import dayjs from 'dayjs';
import ProductLinesField from '@/components/opportunities/ProductLinesField';
import type { ProductLine } from '@/types';

const OpportunityEditPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const oppId = Number(id);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const { data: opp, isLoading, error: loadError } = useQuery({
    queryKey: ['opportunity', oppId],
    queryFn: async () => {
      const res = await opportunitiesApi.get(oppId);
      return res.data;
    },
  });

  useEffect(() => {
    if (!opp) return;
    form.setFieldsValue({
      name: opp.name,
      customer_name: opp.customer_name,
      region: opp.region,
      country: opp.country,
      city: opp.city,
      worth: Number(opp.worth),
      closing_date: opp.closing_date ? dayjs(opp.closing_date) : undefined,
      requirements: opp.requirements,
      industry: opp.industry || undefined,
      products: opp.products ?? [],
      stage_probability: opp.stage_probability != null ? Number(opp.stage_probability) : undefined,
      time_frame: opp.time_frame || undefined,
    });
  }, [opp, form]);

  const mutation = useMutation({
    mutationFn: (data: Partial<OpportunityCreateRequest>) => opportunitiesApi.update(oppId, data),
    onSuccess: () => {
      void message.success('Opportunity updated');
      navigate(`/opportunities/${oppId}`);
    },
    onError: (err: AxiosError<ErrorResponse>) => {
      setError(err.response?.data?.message || 'Failed to update opportunity');
    },
  });

  const onFinish = (values: Record<string, unknown>) => {
    const data: Partial<OpportunityCreateRequest> = {
      name: values['name'] as string,
      customer_name: values['customer_name'] as string,
      region: values['region'] as string,
      country: values['country'] as string,
      city: values['city'] as string,
      worth: values['worth'] as number,
      closing_date: (values['closing_date'] as dayjs.Dayjs).format('YYYY-MM-DD'),
      requirements: values['requirements'] as string,
      industry: (values['industry'] as string) || undefined,
      products: (values['products'] as ProductLine[] | undefined)?.filter((l) => l.product),
      stage_probability: typeof values['stage_probability'] === 'number'
        ? (values['stage_probability'] as number)
        : undefined,
      time_frame: (values['time_frame'] as string) || undefined,
    };
    mutation.mutate(data);
  };

  if (loadError) return <Alert type="error" message="Failed to load opportunity" showIcon />;
  if (isLoading || !opp) return <Skeleton active paragraph={{ rows: 10 }} />;

  const editable = opp.status === 'draft' || opp.status === 'rejected';

  return (
    <>
      <PageHeader
        title="Edit Opportunity"
        breadcrumbs={[
          { label: 'Opportunities', path: '/opportunities' },
          { label: opp.name, path: `/opportunities/${oppId}` },
          { label: 'Edit' },
        ]}
      />

      {!editable ? (
        <Card style={{ maxWidth: 700 }}>
          <Alert
            type="warning"
            showIcon
            message="Only draft or rejected opportunities can be edited"
            style={{ marginBottom: 16 }}
          />
          <Button onClick={() => navigate(`/opportunities/${oppId}`)}>Back to Opportunity</Button>
        </Card>
      ) : (
        <>
          {error && (
            <Alert
              message={error}
              type="error"
              showIcon
              closable
              onClose={() => setError(null)}
              style={{ marginBottom: 16, maxWidth: 700 }}
            />
          )}
          <Card style={{ maxWidth: 700 }}>
            <Form form={form} layout="vertical" onFinish={onFinish}>
              <Form.Item
                name="name"
                label="Opportunity Name"
                rules={[{ required: true, max: 200, message: 'Required (max 200 chars)' }]}
              >
                <Input placeholder="Opportunity name" />
              </Form.Item>
              <Form.Item
                name="customer_name"
                label="Customer Name"
                rules={[{ required: true, max: 200, message: 'Required' }]}
              >
                <Input placeholder="End customer name" />
              </Form.Item>
              <Form.Item name="region" label="Region" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="Geographic region" />
              </Form.Item>
              <Form.Item name="country" label="Country" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="Country" />
              </Form.Item>
              <Form.Item name="city" label="City" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="City" />
              </Form.Item>
              <Form.Item name="worth" label="Opportunity Worth (USD)" rules={[{ required: true, message: 'Required' }]}>
                <InputNumber style={{ width: '100%' }} min={0.01} precision={2} placeholder="0.00" prefix="$" />
              </Form.Item>
              <Form.Item name="industry" label="Customer Industry">
                <Select
                  allowClear
                  placeholder="Select industry"
                  options={[
                    { value: 'FSI', label: 'FSI' },
                    { value: 'Healthcare', label: 'Healthcare' },
                    { value: 'Telco / ISP', label: 'Telco / ISP' },
                    { value: 'Manufacturing', label: 'Manufacturing' },
                    { value: 'Oil & Gas/ Power', label: 'Oil & Gas / Power' },
                    { value: 'Education', label: 'Education' },
                    { value: 'Government', label: 'Government' },
                    { value: 'Retail', label: 'Retail' },
                    { value: 'IT Services', label: 'IT Services' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="products" label="Products & Sizing">
                <ProductLinesField />
              </Form.Item>
              <Form.Item name="stage_probability" label="Pipeline Stage">
                <Select
                  allowClear
                  placeholder="Select stage"
                  options={[
                    { value: 0.1, label: '0.10 — Raw Lead' },
                    { value: 0.3, label: '0.30 — POC Engaged / Tender Specs' },
                    { value: 0.6, label: '0.60 — POC Successful / Budget Approved' },
                    { value: 0.7, label: '0.70 — Price Submitted / Negotiation' },
                    { value: 0.9, label: '0.90 — PO Received' },
                    { value: 1.0, label: '1.00 — Payment Received' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="time_frame" label="Expected Time Frame">
                <Input placeholder="e.g. Q3 - 2027" />
              </Form.Item>
              <Form.Item name="closing_date" label="Expected Closing Date" rules={[{ required: true, message: 'Required' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="requirements"
                label="Detailed Requirements"
                rules={[{ required: true, message: 'Required' }]}
              >
                <Input.TextArea rows={4} placeholder="Describe the requirements..." />
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
                <Button onClick={() => navigate(`/opportunities/${oppId}`)}>Cancel</Button>
              </Form.Item>
            </Form>
          </Card>
        </>
      )}
    </>
  );
};

export default OpportunityEditPage;

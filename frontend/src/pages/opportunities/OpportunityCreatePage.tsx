import React, { useState } from 'react';
import { Form, Input, InputNumber, DatePicker, Button, Card, Alert, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { opportunitiesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { OpportunityCreateRequest } from '@/types';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';
import dayjs from 'dayjs';

const OpportunityCreatePage: React.FC = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (data: OpportunityCreateRequest) => opportunitiesApi.create(data),
    onSuccess: (res) => { void message.success('Opportunity created'); navigate(`/opportunities/${res.data.id}`); },
    onError: (err: AxiosError<ErrorResponse>) => setError(err.response?.data?.message || 'Failed'),
  });

  const onFinish = (values: Record<string, unknown>) => {
    const data: OpportunityCreateRequest = {
      name: values['name'] as string,
      customer_name: values['customer_name'] as string,
      region: values['region'] as string,
      country: values['country'] as string,
      city: values['city'] as string,
      worth: values['worth'] as number,
      closing_date: (values['closing_date'] as dayjs.Dayjs).format('YYYY-MM-DD'),
      requirements: values['requirements'] as string,
      status: values['submit'] ? 'pending_review' : 'draft',
    };
    mutation.mutate(data);
  };

  return (
    <>
      <PageHeader title="New Opportunity" breadcrumbs={[{ label: 'Opportunities', path: '/opportunities' }, { label: 'Create' }]} />
      {error && <Alert message={error} type="error" showIcon closable onClose={() => setError(null)} style={{ marginBottom: 16 }} />}
      <Card style={{ maxWidth: 700 }}>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="name" label="Opportunity Name" rules={[{ required: true, max: 200, message: 'Required (max 200 chars)' }]}>
            <Input placeholder="Opportunity name" />
          </Form.Item>
          <Form.Item name="customer_name" label="Customer Name" rules={[{ required: true, max: 200, message: 'Required' }]}>
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
          <Form.Item name="closing_date" label="Expected Closing Date" rules={[{ required: true, message: 'Required' }]}>
            <DatePicker style={{ width: '100%' }} disabledDate={(d) => d.isBefore(dayjs(), 'day')} />
          </Form.Item>
          <Form.Item name="requirements" label="Detailed Requirements" rules={[{ required: true, message: 'Required' }]}>
            <Input.TextArea rows={6} placeholder="Describe the requirements..." />
          </Form.Item>
          <Form.Item>
            <Button htmlType="submit" loading={mutation.isPending} style={{ marginRight: 8 }} onClick={() => form.setFieldsValue({ submit: false })}>
              Save as Draft
            </Button>
            <Button type="primary" htmlType="submit" loading={mutation.isPending} onClick={() => form.setFieldsValue({ submit: true })}>
              Submit for Review
            </Button>
            <Form.Item name="submit" hidden><Input /></Form.Item>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default OpportunityCreatePage;

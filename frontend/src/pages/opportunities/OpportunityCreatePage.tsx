import React, { useEffect, useState } from 'react';
import {
  Form,
  Input,
  InputNumber,
  DatePicker,
  Button,
  Card,
  Alert,
  message,
  Tag,
  Typography,
  Space,
  Spin,
} from 'antd';
import {
  WarningOutlined,
  StopOutlined,
  CheckCircleOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { opportunitiesApi, duplicatesApi } from '@/api/endpoints';
import type { DuplicateCheckResponse } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { OpportunityCreateRequest } from '@/types';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';
import dayjs from 'dayjs';

// ---------------------------------------------------------------------------
// Duplicate warning panel — renders the result of /opportunities/check-duplicate
// ---------------------------------------------------------------------------
const DuplicatePanel: React.FC<{ result: DuplicateCheckResponse | null; checking: boolean }> = ({
  result,
  checking,
}) => {
  if (checking) {
    return (
      <Alert
        type="info"
        showIcon
        icon={<Spin size="small" />}
        message="Checking for duplicates…"
        style={{ marginBottom: 16, borderRadius: 10 }}
      />
    );
  }
  if (!result) return null;

  if (result.severity === 'clear') {
    return (
      <Alert
        type="success"
        showIcon
        icon={<CheckCircleOutlined />}
        message="No duplicates detected"
        description="No matching opportunities found in the system. You're free to register this customer."
        style={{ marginBottom: 16, borderRadius: 10 }}
      />
    );
  }

  if (result.severity === 'block') {
    return (
      <Alert
        type="error"
        showIcon
        icon={<StopOutlined />}
        message="Registration blocked"
        description={
          <div>
            <p style={{ marginBottom: 8 }}>
              Another company has exclusivity / ownership on this customer:
            </p>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {result.messages.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
            {result.exclusivity_blocks.length > 0 && (
              <div style={{ marginTop: 10, padding: '10px 14px', background: '#fff1f0', borderRadius: 6 }}>
                <Typography.Text strong style={{ color: '#cf1322' }}>Active deal exclusivity:</Typography.Text>
                {result.exclusivity_blocks.map((b) => (
                  <div key={b.deal_id} style={{ marginTop: 4, fontSize: 13 }}>
                    {b.company_name} — exclusive on "{b.customer_name}" through {b.exclusivity_end}
                  </div>
                ))}
              </div>
            )}
          </div>
        }
        style={{ marginBottom: 16, borderRadius: 10 }}
      />
    );
  }

  // severity === 'warn'
  const allMatches = [...result.exact_matches, ...result.fuzzy_matches, ...result.domain_matches];
  return (
    <Alert
      type="warning"
      showIcon
      icon={<WarningOutlined />}
      message={`${allMatches.length} possible duplicate${allMatches.length === 1 ? '' : 's'} found`}
      description={
        <div>
          <p style={{ marginBottom: 8 }}>
            You can still proceed, but this opportunity will be flagged for admin review.
          </p>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {result.exact_matches.map((m) => (
              <div key={`e-${m.id}`} style={{ padding: '8px 12px', background: '#fff7e6', borderRadius: 6, border: '1px solid #ffd591' }}>
                <Tag color="orange" style={{ fontSize: 10 }}>EXACT</Tag>
                <Typography.Text strong> {m.customer_name}</Typography.Text>
                <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 8 }}>
                  by {m.company_name} • {m.status.replace(/_/g, ' ')} • {m.country}
                </span>
              </div>
            ))}
            {result.fuzzy_matches.map((m) => (
              <div key={`f-${m.id}`} style={{ padding: '8px 12px', background: '#fff7e6', borderRadius: 6, border: '1px solid #ffd591' }}>
                <Tag color="purple" style={{ fontSize: 10 }}>SIMILAR {Math.round((m.similarity ?? 0) * 100)}%</Tag>
                <Typography.Text strong> {m.customer_name}</Typography.Text>
                <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 8 }}>
                  by {m.company_name} • {m.status.replace(/_/g, ' ')} • {m.country}
                </span>
              </div>
            ))}
            {result.domain_matches.map((m) => (
              <div key={`d-${m.id}`} style={{ padding: '8px 12px', background: '#fff7e6', borderRadius: 6, border: '1px solid #ffd591' }}>
                <Tag color="blue" style={{ fontSize: 10 }}><RobotOutlined /> SAME DOMAIN</Tag>
                <Typography.Text strong> {m.customer_name}</Typography.Text>
                <span style={{ fontSize: 12, color: '#6b7280', marginLeft: 8 }}>
                  by {m.company_name}
                </span>
              </div>
            ))}
          </Space>
        </div>
      }
      style={{ marginBottom: 16, borderRadius: 10 }}
    />
  );
};

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------
function useDebounced<T>(value: T, delay = 600): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
const OpportunityCreatePage: React.FC = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  // Live duplicate check state
  const [customerName, setCustomerName] = useState('');
  const [country, setCountry] = useState('');
  const [dupResult, setDupResult] = useState<DuplicateCheckResponse | null>(null);
  const [dupChecking, setDupChecking] = useState(false);

  const debouncedCustomer = useDebounced(customerName, 600);
  const debouncedCountry = useDebounced(country, 600);

  // Fire the check whenever the debounced inputs are populated enough
  useEffect(() => {
    if (debouncedCustomer.trim().length < 2 || debouncedCountry.trim().length < 1) {
      setDupResult(null);
      return;
    }
    let cancelled = false;
    setDupChecking(true);
    duplicatesApi
      .checkDuplicate({
        customer_name: debouncedCustomer.trim(),
        country: debouncedCountry.trim(),
      })
      .then((res) => {
        if (!cancelled) setDupResult(res.data);
      })
      .catch(() => {
        if (!cancelled) setDupResult(null);
      })
      .finally(() => {
        if (!cancelled) setDupChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedCustomer, debouncedCountry]);

  const mutation = useMutation({
    mutationFn: (data: OpportunityCreateRequest) => opportunitiesApi.create(data),
    onSuccess: (res) => {
      void message.success('Opportunity created');
      navigate(`/opportunities/${res.data.id}`);
    },
    onError: (err: AxiosError<ErrorResponse>) => {
      const detail = err.response?.data;
      if (detail && typeof detail === 'object' && 'code' in detail && (detail as { code: string }).code === 'DUPLICATE_BLOCKED') {
        setError('Registration blocked: another company has exclusivity on this customer. See the warning panel above.');
      } else {
        setError((detail as { message?: string })?.message || 'Failed to create opportunity');
      }
    },
  });

  const onFinish = (values: Record<string, unknown>) => {
    // Hard-block on submit if the live check came back with severity=block
    if (dupResult?.severity === 'block') {
      void message.error('This opportunity is blocked due to existing exclusivity. See warning above.');
      return;
    }
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

  const submitDisabled = dupResult?.severity === 'block';

  return (
    <>
      <PageHeader
        title="New Opportunity"
        breadcrumbs={[{ label: 'Opportunities', path: '/opportunities' }, { label: 'Create' }]}
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

      {/* Live duplicate warning panel */}
      <div style={{ maxWidth: 700 }}>
        <DuplicatePanel result={dupResult} checking={dupChecking} />
      </div>

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
            extra="We'll check for duplicates as you type — the panel above updates within ~1 second."
            rules={[{ required: true, max: 200, message: 'Required' }]}
          >
            <Input placeholder="End customer name" onChange={(e) => setCustomerName(e.target.value)} />
          </Form.Item>
          <Form.Item name="region" label="Region" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Geographic region" />
          </Form.Item>
          <Form.Item name="country" label="Country" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Country" onChange={(e) => setCountry(e.target.value)} />
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
          <Form.Item
            name="requirements"
            label="Detailed Requirements"
            rules={[{ required: true, message: 'Required' }]}
          >
            <Input.TextArea rows={6} placeholder="Describe the requirements..." />
          </Form.Item>
          <Form.Item>
            <Button
              htmlType="submit"
              loading={mutation.isPending}
              disabled={submitDisabled}
              style={{ marginRight: 8 }}
              onClick={() => form.setFieldsValue({ submit: false })}
            >
              Save as Draft
            </Button>
            <Button
              type="primary"
              htmlType="submit"
              loading={mutation.isPending}
              disabled={submitDisabled}
              onClick={() => form.setFieldsValue({ submit: true })}
            >
              Submit for Review
            </Button>
            <Form.Item name="submit" hidden>
              <Input />
            </Form.Item>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
};

export default OpportunityCreatePage;

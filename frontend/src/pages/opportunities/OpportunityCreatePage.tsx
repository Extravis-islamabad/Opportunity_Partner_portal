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
  Select,
  AutoComplete,
} from 'antd';
import {
  WarningOutlined,
  StopOutlined,
  CheckCircleOutlined,
  RobotOutlined,
  BankOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { opportunitiesApi, duplicatesApi, currenciesApi } from '@/api/endpoints';
import type { DuplicateCheckResponse } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { OpportunityCreateRequest, KnownCustomerOption } from '@/types';
import { AxiosError } from 'axios';
import type { ErrorResponse } from '@/types';
import dayjs from 'dayjs';
import ProductLinesField from '@/components/opportunities/ProductLinesField';
import type { CurrencyCode, ProductLine } from '@/types';

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
  const { user } = useAuth();
  // A sales rep registers on a partner's behalf, so the form asks them which
  // partner holds the lock and offers the customers the portal already
  // knows. A partner registers for their own company and sees neither.
  const isSalesRep = user?.role === 'sales_rep';
  // The currency the form currently has, so the product lines can label their
  // values in it rather than always in dollars.
  const selectedCurrency = (Form.useWatch('currency', form) as string) || 'USD';
  const selectedCompanyId = Form.useWatch('company_id', form) as number | undefined;

  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  // Live duplicate check state
  const [customerName, setCustomerName] = useState('');
  const [country, setCountry] = useState('');
  const [dupResult, setDupResult] = useState<DuplicateCheckResponse | null>(null);
  const [dupChecking, setDupChecking] = useState(false);

  const debouncedCustomer = useDebounced(customerName, 600);
  const debouncedCountry = useDebounced(country, 600);

  // The pickers, fetched only for a rep — the endpoints are theirs and an
  // admin's, and a partner would just get a 403 for nothing.
  const { data: partnerCompanies, isLoading: partnersLoading } = useQuery({
    queryKey: ['partner-companies'],
    queryFn: async () => (await opportunitiesApi.partnerCompanies()).data,
    enabled: isSalesRep,
    staleTime: 5 * 60 * 1000,
  });
  const { data: knownCustomers } = useQuery({
    queryKey: ['known-customers', debouncedCustomer],
    queryFn: async () => (await opportunitiesApi.knownCustomers(debouncedCustomer || undefined)).data,
    enabled: isSalesRep,
    staleTime: 60 * 1000,
  });

  // Fire the check whenever the debounced inputs are populated enough. For a
  // rep the check is run as the chosen partner — the exclusivity block
  // depends on whose registration it would be, and a partner's own lock
  // never blocks them — so it re-runs when the partner changes.
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
        company_id: isSalesRep ? selectedCompanyId : undefined,
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
  }, [debouncedCustomer, debouncedCountry, isSalesRep, selectedCompanyId]);

  // Picking a known customer fills in where they are as well as who they are,
  // so the duplicate check and the record both get the same spelling.
  const applyKnownCustomer = (picked: KnownCustomerOption) => {
    form.setFieldsValue({
      customer_name: picked.customer_name,
      country: picked.country,
      ...(picked.city ? { city: picked.city } : {}),
      ...(picked.region ? { region: picked.region } : {}),
    });
    setCustomerName(picked.customer_name);
    setCountry(picked.country);
  };

  const { data: currencies } = useQuery({
    queryKey: ['currencies'],
    queryFn: async () => (await currenciesApi.list()).data,
    staleTime: Infinity,
  });

  const mutation = useMutation({
    mutationFn: (data: OpportunityCreateRequest) => opportunitiesApi.create(data),
    onSuccess: (res) => {
      void message.success('Opportunity created');
      navigate(`/opportunities/${res.data.id}`);
    },
    onError: (err: AxiosError<ErrorResponse>) => {
      const detail = err.response?.data;
      const code = detail && typeof detail === 'object' && 'code' in detail ? (detail as { code: string }).code : undefined;
      if (code === 'DUPLICATE_BLOCKED') {
        setError('Registration blocked: another company has exclusivity on this customer. See the warning panel above.');
      } else if (code === 'PARTNER_REQUIRED') {
        setError('Choose the partner this opportunity is registered for.');
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
      currency: (values['currency'] as CurrencyCode) || undefined,
      closing_date: (values['closing_date'] as dayjs.Dayjs).format('YYYY-MM-DD'),
      requirements: values['requirements'] as string,
      status: values['submit'] ? 'pending_review' : 'draft',
      industry: (values['industry'] as string) || undefined,
      products: (values['products'] as ProductLine[] | undefined)?.filter((l) => l.product),
      stage_probability: typeof values['stage_probability'] === 'number'
        ? (values['stage_probability'] as number)
        : undefined,
      time_frame: (values['time_frame'] as string) || undefined,
      // Only a rep names the partner; a partner's own company is implied
      // and the server refuses any other.
      company_id: isSalesRep ? (values['company_id'] as number) : undefined,
    };
    mutation.mutate(data);
  };

  const submitDisabled = dupResult?.severity === 'block';
  const chosenPartner = partnerCompanies?.find((c) => c.id === selectedCompanyId);

  // AutoComplete keys its options by value, and the value has to be the
  // customer name because that is what lands in the field — so one name gets
  // one option even when the portal knows it in two countries. The first
  // (most recently seen) wins; the country still comes along on selection.
  const customerOptions = (knownCustomers ?? []).filter(
    (c, i, all) => all.findIndex((o) => o.customer_name === c.customer_name) === i,
  );

  return (
    <>
      <PageHeader
        title={isSalesRep ? 'Lock an Opportunity for a Partner' : 'New Opportunity'}
        subtitle={
          isSalesRep
            ? 'Register the opportunity in the partner\'s name. Once approved, the customer is locked to that partner and the opportunity stays assigned to you.'
            : undefined
        }
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
          {isSalesRep && (
            <Form.Item
              name="company_id"
              label="Partner"
              tooltip="The partner company this opportunity is registered for. On approval the customer is locked to them, and the deal counts towards their tier and commission."
              extra={
                chosenPartner
                  ? `${chosenPartner.company_type === 'distributor' ? 'Distributor' : 'Partner'} · ${chosenPartner.country}${chosenPartner.tier ? ` · ${chosenPartner.tier} tier` : ''}`
                  : 'Only active partner and distributor companies can hold a registration.'
              }
              rules={[{ required: true, message: 'Choose the partner this opportunity is registered for' }]}
            >
              <Select
                showSearch
                loading={partnersLoading}
                placeholder="Select the partner"
                optionFilterProp="label"
                suffixIcon={<BankOutlined />}
                options={(partnerCompanies ?? []).map((c) => ({
                  value: c.id,
                  label: c.name,
                }))}
              />
            </Form.Item>
          )}
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
            extra={
              isSalesRep
                ? "Pick a customer the portal already knows, or type a new one. We'll check for duplicates and exclusivity as you type."
                : "We'll check for duplicates as you type — the panel above updates within ~1 second."
            }
            rules={[{ required: true, max: 200, message: 'Required' }]}
          >
            {isSalesRep ? (
              <AutoComplete
                placeholder="End customer name"
                onChange={(v) => setCustomerName(typeof v === 'string' ? v : '')}
                onSelect={(_v, option) => {
                  const picked = (option as { customer?: KnownCustomerOption }).customer;
                  if (picked) applyKnownCustomer(picked);
                }}
                options={customerOptions.map((c) => ({
                  value: c.customer_name,
                  customer: c,
                  label: (
                    <Space size={8}>
                      <span>{c.customer_name}</span>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {c.country}{c.city ? ` · ${c.city}` : ''}{c.company_name ? ` · via ${c.company_name}` : ''}
                      </Typography.Text>
                    </Space>
                  ),
                }))}
              />
            ) : (
              <Input placeholder="End customer name" onChange={(e) => setCustomerName(e.target.value)} />
            )}
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
          <Form.Item name="worth" label="Opportunity Worth" rules={[{ required: true, message: 'Required' }]}>
            <InputNumber style={{ width: '100%' }} min={0.01} precision={2} placeholder="0.00" />
          </Form.Item>
          <Form.Item
            name="currency"
            label="Currency"
            tooltip="The currency the customer actually pays in. Reports convert everything to USD at the rate on the day the deal is recorded."
          >
            <Select
              placeholder="USD"
              options={(currencies?.currencies ?? []).map((c) => ({
                value: c.currency,
                label: c.currency,
              }))}
            />
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
          <Form.Item
            name="products"
            label="Products & Sizing"
            tooltip="Device and node counts are what the quote is priced from, so they belong here rather than on the licence after the PO."
          >
            <ProductLinesField currency={selectedCurrency} />
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
            <Select
              allowClear
              placeholder="Select quarter"
              options={[
                { value: 'Q1 - 2027', label: 'Q1 - 2027' },
                { value: 'Q2 - 2027', label: 'Q2 - 2027' },
                { value: 'Q3 - 2027', label: 'Q3 - 2027' },
                { value: 'Q4 - 2027', label: 'Q4 - 2027' },
              ]}
            />
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

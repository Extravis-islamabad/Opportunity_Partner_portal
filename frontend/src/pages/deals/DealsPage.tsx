import React, { useState } from 'react';
import {
  Table, Button, Tag, Space, Alert, Modal, Form, Input, InputNumber, DatePicker,
  message, Radio, Select, Drawer, Descriptions, Divider, Typography,
} from 'antd';
import { PlusOutlined, CheckOutlined, CloseOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dashboardApi, exportsApi, opportunitiesApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import EmptyState from '@/components/common/EmptyState';
import TableSkeleton from '@/components/common/TableSkeleton';
import ExportMenu from '@/components/common/ExportMenu';
import type { DealRegistrationResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { formatMoney, reportingSuffix } from '@/utils/money';

const statusColors: Record<string, string> = { pending: 'orange', approved: 'green', rejected: 'red', expired: 'default' };

const yesNo = (v: boolean | null | undefined) => (v == null ? '—' : v ? 'Yes' : 'No');
const orDash = (v: string | null | undefined) => v || '—';

// The numbered section header the registration form and detail view share.
const SectionTitle: React.FC<{ n: number; title: string; subtitle?: string }> = ({ n, title, subtitle }) => (
  <div style={{ marginBottom: 12 }}>
    <Space size={8}>
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 22, height: 22, borderRadius: 6, background: '#eef0ff', color: '#4a54c4',
        fontWeight: 600, fontSize: 12,
      }}>{n}</span>
      <Typography.Text strong style={{ fontSize: 15 }}>{title}</Typography.Text>
    </Space>
    {subtitle && (
      <div style={{ color: '#8c8c8c', fontSize: 13, marginTop: 2 }}>{subtitle}</div>
    )}
  </div>
);

const DealsPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isPartner = user?.role === 'partner';
  const queryClient = useQueryClient();

  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const [approveModal, setApproveModal] = useState<number | null>(null);
  const [exclusivityDays, setExclusivityDays] = useState(90);
  const [rejectModal, setRejectModal] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [extendModal, setExtendModal] = useState<DealRegistrationResponse | null>(null);
  const [extendDays, setExtendDays] = useState(30);
  const [extendReason, setExtendReason] = useState('');
  const [viewDeal, setViewDeal] = useState<DealRegistrationResponse | null>(null);

  // Tender and non-tender ask for different supporting details.
  const opportunityType = (Form.useWatch('opportunity_type', createForm) as string) || 'non_tender';
  const isTender = opportunityType === 'tender';

  const { data: productCatalogue } = useQuery({
    queryKey: ['products'],
    queryFn: async () => (await opportunitiesApi.products()).data,
    enabled: isPartner,
    staleTime: Infinity,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['deals', page],
    queryFn: async () => { const res = await dashboardApi.listDeals({ page, page_size: 20 }); return res.data; },
  });

  const createMut = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      const tender = values['opportunity_type'] === 'tender';
      const data: Record<string, unknown> = {
        ...values,
        expected_close_date: (values['expected_close_date'] as dayjs.Dayjs).format('YYYY-MM-DD'),
        // Tender-only fields stay out of a non-tender payload entirely.
        tender_number: tender ? values['tender_number'] : undefined,
        tender_submission_date: tender && values['tender_submission_date']
          ? (values['tender_submission_date'] as dayjs.Dayjs).format('YYYY-MM-DD')
          : undefined,
        mal_maf_required: tender ? values['mal_maf_required'] : undefined,
      };
      return dashboardApi.createDeal(data);
    },
    onSuccess: () => { setCreateModal(false); createForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['deals'] }); void message.success('Deal registered'); },
  });

  const approveMut = useMutation({
    mutationFn: ({ id, days }: { id: number; days: number }) => dashboardApi.approveDeal(id, days),
    onSuccess: () => { setApproveModal(null); void queryClient.invalidateQueries({ queryKey: ['deals'] }); void message.success('Deal approved'); },
  });

  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => dashboardApi.rejectDeal(id, reason),
    onSuccess: () => { setRejectModal(null); setRejectReason(''); void queryClient.invalidateQueries({ queryKey: ['deals'] }); void message.success('Deal rejected'); },
  });

  const extendMut = useMutation({
    mutationFn: ({ id, days, reason }: { id: number; days: number; reason: string }) =>
      dashboardApi.requestExtension(id, days, reason.trim() || undefined),
    onSuccess: () => {
      setExtendModal(null);
      setExtendReason('');
      void queryClient.invalidateQueries({ queryKey: ['deals'] });
      void message.success('Extension requested — an admin will decide it');
    },
    onError: () => { void message.error('Could not request an extension'); },
  });

  const columns: ColumnsType<DealRegistrationResponse> = [
    {
      title: 'Customer', dataIndex: 'customer_name', key: 'customer',
      render: (name: string, r: DealRegistrationResponse) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => setViewDeal(r)}>{name}</Button>
      ),
    },
    ...(isAdmin ? [{ title: 'Company', dataIndex: 'company_name' as const, key: 'company' }] : []),
    {
      title: 'Value', dataIndex: 'estimated_value', key: 'value',
      render: (v: string, r: DealRegistrationResponse) => (
        <Space direction="vertical" size={0}>
          <span>{formatMoney(v, r.currency)}</span>
          {reportingSuffix(r.currency, r.estimated_value_usd) && (
            <span style={{ fontSize: 11, color: '#8c8c8c' }}>
              {reportingSuffix(r.currency, r.estimated_value_usd)}
            </span>
          )}
        </Space>
      ),
    },
    { title: 'Close Date', dataIndex: 'expected_close_date', key: 'date' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={statusColors[s] ?? 'default'}>{s.toUpperCase()}</Tag> },
    {
      title: 'Exclusivity',
      key: 'excl',
      render: (_, r) => {
        if (!r.exclusivity_end) return '-';
        // days_left is only set while the window is live, so a number here
        // always means protection that still applies.
        if (r.days_left === null) {
          return <span style={{ color: '#8c8c8c' }}>Ended {r.exclusivity_end}</span>;
        }
        const urgent = r.days_left <= 14;
        return (
          <Space size={4}>
            <span>Until {r.exclusivity_end}</span>
            <Tag color={urgent ? 'orange' : 'default'} icon={urgent ? <ClockCircleOutlined /> : undefined}>
              {r.days_left} {r.days_left === 1 ? 'day' : 'days'} left
            </Tag>
          </Space>
        );
      },
    },
    ...(isAdmin ? [{
      title: 'Actions' as const, key: 'actions' as const, render: (_: unknown, record: DealRegistrationResponse) => record.status === 'pending' ? (
        <Space>
          <Button type="link" icon={<CheckOutlined />} onClick={() => setApproveModal(record.id)}>Approve</Button>
          <Button type="link" danger icon={<CloseOutlined />} onClick={() => setRejectModal(record.id)}>Reject</Button>
        </Space>
      ) : null,
    }] : []),
    ...(isPartner ? [{
      title: 'Actions' as const, key: 'partner-actions' as const,
      render: (_: unknown, record: DealRegistrationResponse) => {
        // Only while the window is live: an expired registration has to be
        // registered again, and the API refuses an extension on one.
        if (record.status !== 'approved' || record.days_left === null) return null;
        if (record.extension_pending) return <Tag color="processing">Extension requested</Tag>;
        return (
          <Button type="link" onClick={() => setExtendModal(record)}>Request Extension</Button>
        );
      },
    }] : []),
  ];

  if (error) return <Alert type="error" message="Failed to load deals" showIcon />;

  return (
    <>
      <PageHeader
        title="Deal Registration"
        subtitle="Register and protect your deals"
        extra={
          <Space>
            <ExportMenu
              filenamePrefix="deals"
              pdf={() => exportsApi.dealsPdf()}
              xlsx={() => exportsApi.dealsXlsx()}
            />
            {isPartner && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
                Register Deal
              </Button>
            )}
          </Space>
        }
      />
      {isLoading ? <TableSkeleton /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }} />
        ) : (
          <EmptyState
            title="No deal registrations"
            description={isPartner
              ? 'Register a deal to protect your pipeline with exclusivity.'
              : 'No deal registrations have been submitted yet.'}
            action={isPartner && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
                Register Deal
              </Button>
            )}
          />
        )
      )}

      <Modal title="Register New Deal" open={createModal} onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()} confirmLoading={createMut.isPending} width={760}
        okText="Register Deal">
        <Form form={createForm} layout="vertical" onFinish={createMut.mutate}
          initialValues={{ opportunity_type: 'non_tender' }}>

          <SectionTitle n={1} title="Client Details" subtitle="Information about the end client for this opportunity." />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
            <Form.Item name="customer_name" label="Company Name" rules={[{ required: true, max: 200 }]}>
              <Input placeholder="End client company" />
            </Form.Item>
            <Form.Item name="client_email" label="Email" rules={[{ required: true, type: 'email' }]}>
              <Input placeholder="contact@client.com" maxLength={255} />
            </Form.Item>
            <Form.Item name="client_website" label="Website">
              <Input placeholder="https://client.com" maxLength={255} />
            </Form.Item>
            <Form.Item name="client_contact" label="Contact" rules={[{ required: true }]}>
              <Input placeholder="Phone number" maxLength={50} />
            </Form.Item>
            <Form.Item name="client_fax" label="Fax">
              <Input placeholder="Fax number" maxLength={50} />
            </Form.Item>
            <Form.Item name="client_address" label="Address" rules={[{ required: true }]}>
              <Input placeholder="Client address" maxLength={500} />
            </Form.Item>
            <Form.Item name="individual_name" label="Individual Name" rules={[{ required: true }]}>
              <Input placeholder="Person you are dealing with" maxLength={255} />
            </Form.Item>
            <Form.Item name="individual_department" label="Individual Department">
              <Input placeholder="e.g. Procurement" maxLength={255} />
            </Form.Item>
            <Form.Item name="individual_designation" label="Individual Designation">
              <Input placeholder="e.g. Procurement Manager" maxLength={255} />
            </Form.Item>
          </div>

          <Divider style={{ margin: '4px 0 16px' }} />
          <SectionTitle n={2} title="Opportunity Type" subtitle="Tender or non-tender opportunity, and the supporting details." />
          <Form.Item name="opportunity_type" rules={[{ required: true }]}>
            <Radio.Group optionType="button" buttonStyle="outline"
              options={[{ value: 'tender', label: 'Tender' }, { value: 'non_tender', label: 'Non-Tender' }]} />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
            <Form.Item name="opportunity_name" label="Opportunity Name" rules={[{ required: true, max: 200 }]}>
              <Input placeholder="Opportunity name" />
            </Form.Item>
            {isTender ? (
              <>
                <Form.Item name="tender_number" label="Tender Number" rules={[{ required: true, max: 100 }]}>
                  <Input placeholder="e.g. TND-2026-0472" />
                </Form.Item>
                <Form.Item name="tender_submission_date" label="Tender Submission Date" rules={[{ required: true }]}>
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="estimated_value" label="Client Budget (USD)" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0.01} precision={2} placeholder="0.00" />
                </Form.Item>
                <Form.Item name="mal_maf_required" label="MAL / MAF Required" rules={[{ required: true }]}>
                  <Select options={[{ value: true, label: 'Yes' }, { value: false, label: 'No' }]} placeholder="Select" />
                </Form.Item>
                <Form.Item name="poc_required" label="POC Required During Evaluation" rules={[{ required: true }]}>
                  <Select options={[{ value: true, label: 'Yes' }, { value: false, label: 'No' }]} placeholder="Select" />
                </Form.Item>
              </>
            ) : (
              <>
                <Form.Item name="estimated_value" label="Estimated Budget (USD)" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0.01} precision={2} placeholder="0.00" />
                </Form.Item>
                <Form.Item name="poc_required" label="POC Required" rules={[{ required: true }]}>
                  <Select options={[{ value: true, label: 'Yes' }, { value: false, label: 'No' }]} placeholder="Select" />
                </Form.Item>
              </>
            )}
            <Form.Item name="expected_close_date"
              label={isTender ? 'Expected Close Date' : 'Expected Closure Date'}
              rules={[{ required: true }]}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </div>

          <Form.Item name="products" label="Products">
            <Select mode="multiple" allowClear placeholder="Select products"
              options={(productCatalogue ?? []).map((o) => ({ value: o.value, label: o.label }))} />
          </Form.Item>
          <Form.Item name="deal_description" label="Note" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="Describe the deal — relationship, timeline, anything the reviewer should know." />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="Deal Registration Details"
        width={640}
        open={viewDeal !== null}
        onClose={() => setViewDeal(null)}
      >
        {viewDeal && (
          <>
            <div style={{ color: '#8c8c8c', marginBottom: 16 }}>
              {viewDeal.customer_name}
              {viewDeal.registered_by_name ? ` · submitted by ${viewDeal.registered_by_name}` : ''}
              {viewDeal.company_name ? ` (${viewDeal.company_name})` : ''}
            </div>
            <Space style={{ marginBottom: 16 }}>
              <Tag color={statusColors[viewDeal.status] ?? 'default'}>{viewDeal.status.toUpperCase()}</Tag>
              {viewDeal.opportunity_type && (
                <Tag color="blue">{viewDeal.opportunity_type === 'tender' ? 'Tender' : 'Non-Tender'}</Tag>
              )}
            </Space>

            <SectionTitle n={1} title="Client Details" subtitle="Information about the end client for this opportunity." />
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 20 }}>
              <Descriptions.Item label="Company Name">{viewDeal.customer_name}</Descriptions.Item>
              <Descriptions.Item label="Email">{orDash(viewDeal.client_email)}</Descriptions.Item>
              <Descriptions.Item label="Website">{orDash(viewDeal.client_website)}</Descriptions.Item>
              <Descriptions.Item label="Contact">{orDash(viewDeal.client_contact)}</Descriptions.Item>
              <Descriptions.Item label="Fax">{orDash(viewDeal.client_fax)}</Descriptions.Item>
              <Descriptions.Item label="Address">{orDash(viewDeal.client_address)}</Descriptions.Item>
              <Descriptions.Item label="Individual Name">{orDash(viewDeal.individual_name)}</Descriptions.Item>
              <Descriptions.Item label="Individual Department">{orDash(viewDeal.individual_department)}</Descriptions.Item>
              <Descriptions.Item label="Individual Designation">{orDash(viewDeal.individual_designation)}</Descriptions.Item>
            </Descriptions>

            <SectionTitle n={2} title="Opportunity Type" subtitle="Tender or non-tender opportunity, and the supporting details." />
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 20 }}>
              <Descriptions.Item label="Opportunity Name">{orDash(viewDeal.opportunity_name)}</Descriptions.Item>
              {viewDeal.opportunity_type === 'tender' ? (
                <>
                  <Descriptions.Item label="Tender Number">{orDash(viewDeal.tender_number)}</Descriptions.Item>
                  <Descriptions.Item label="Tender Submission Date">{orDash(viewDeal.tender_submission_date)}</Descriptions.Item>
                  <Descriptions.Item label="Client Budget">{formatMoney(viewDeal.estimated_value, viewDeal.currency)}</Descriptions.Item>
                  <Descriptions.Item label="MAL / MAF Required">{yesNo(viewDeal.mal_maf_required)}</Descriptions.Item>
                  <Descriptions.Item label="POC Required During Evaluation">{yesNo(viewDeal.poc_required)}</Descriptions.Item>
                </>
              ) : (
                <>
                  <Descriptions.Item label="Estimated Budget">{formatMoney(viewDeal.estimated_value, viewDeal.currency)}</Descriptions.Item>
                  <Descriptions.Item label="POC Required">{yesNo(viewDeal.poc_required)}</Descriptions.Item>
                </>
              )}
              <Descriptions.Item label="Expected Closure Date">{viewDeal.expected_close_date}</Descriptions.Item>
              <Descriptions.Item label="Products" span={2}>
                {viewDeal.products && viewDeal.products.length > 0
                  ? viewDeal.products.map((p) => <Tag key={p} color="geekblue">{p}</Tag>)
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Note" span={2}>{viewDeal.deal_description}</Descriptions.Item>
            </Descriptions>

            {viewDeal.exclusivity_end && (
              <Alert type="info" showIcon style={{ marginBottom: 8 }}
                message={viewDeal.days_left !== null
                  ? `Exclusivity until ${viewDeal.exclusivity_end} — ${viewDeal.days_left} day${viewDeal.days_left === 1 ? '' : 's'} left`
                  : `Exclusivity ended ${viewDeal.exclusivity_end}`} />
            )}
            {viewDeal.rejection_reason && (
              <Alert type="error" showIcon message="Rejected" description={viewDeal.rejection_reason} />
            )}
          </>
        )}
      </Drawer>

      <Modal
        title="Request Exclusivity Extension"
        open={extendModal !== null}
        onCancel={() => setExtendModal(null)}
        onOk={() => extendModal && extendMut.mutate({ id: extendModal.id, days: extendDays, reason: extendReason })}
        confirmLoading={extendMut.isPending}
        okText="Request"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <span>
            Exclusivity on {extendModal?.customer_name} ends {extendModal?.exclusivity_end}.
            An admin decides the request, and may grant fewer days than you ask for.
          </span>
          <InputNumber
            min={1}
            max={365}
            value={extendDays}
            onChange={(v) => setExtendDays(v ?? 30)}
            addonAfter="days"
            style={{ width: 180 }}
          />
          <Input.TextArea
            rows={3}
            placeholder="Why you need more time (optional)"
            value={extendReason}
            onChange={(e) => setExtendReason(e.target.value)}
            maxLength={2000}
          />
        </Space>
      </Modal>

      <Modal title="Approve Deal" open={approveModal !== null} onCancel={() => setApproveModal(null)}
        onOk={() => approveModal && approveMut.mutate({ id: approveModal, days: exclusivityDays })} confirmLoading={approveMut.isPending}>
        <p>Set exclusivity window (days):</p>
        <InputNumber min={1} max={365} value={exclusivityDays} onChange={(v) => setExclusivityDays(v ?? 90)} />
      </Modal>

      <Modal title="Reject Deal" open={rejectModal !== null} onCancel={() => { setRejectModal(null); setRejectReason(''); }}
        onOk={() => rejectModal && rejectMut.mutate({ id: rejectModal, reason: rejectReason })}
        confirmLoading={rejectMut.isPending} okButtonProps={{ disabled: !rejectReason.trim() }}>
        <Input.TextArea rows={3} placeholder="Rejection reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
      </Modal>
    </>
  );
};

export default DealsPage;

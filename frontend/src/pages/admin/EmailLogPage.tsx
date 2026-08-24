import React, { useState } from 'react';
import { Card, Table, Tag, Alert, Select, Space, Statistic, Row, Col, Typography, Tooltip } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { emailLogApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { EmailDeliveryItem, EmailStatus } from '@/types';
import dayjs from 'dayjs';

/**
 * What the system tried to email, and what happened.
 *
 * The distinction that matters is skipped vs failed: skipped means the send
 * was never attempted because SMTP is not configured — a deployment problem,
 * not a mail problem — while failed means the server was asked and said no.
 * Before this existed, both were a log line nobody read, and an activation
 * email that never arrived looked identical to one that did.
 */
const statusMeta: Record<EmailStatus, { color: string; help: string }> = {
  sent: { color: 'green', help: 'The SMTP server accepted the message.' },
  failed: { color: 'red', help: 'The send was attempted and the server refused it.' },
  skipped: { color: 'orange', help: 'Never attempted — SMTP is not configured.' },
};

const EmailLogPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [status, setStatus] = useState<string | undefined>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['email-log', page, pageSize, status],
    queryFn: async () => (await emailLogApi.list({ page, page_size: pageSize, status })).data,
  });

  if (error) return <Alert type="error" message="Failed to load the email log" showIcon />;

  const totals = data?.totals_by_status ?? {};

  const columns = [
    {
      title: 'When',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => dayjs(v).format('MMM D, YYYY HH:mm'),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 110,
      render: (s: EmailStatus) => (
        <Tooltip title={statusMeta[s]?.help}>
          <Tag color={statusMeta[s]?.color ?? 'default'}>{s.toUpperCase()}</Tag>
        </Tooltip>
      ),
    },
    { title: 'To', dataIndex: 'recipients', ellipsis: true },
    { title: 'Subject', dataIndex: 'subject', ellipsis: true },
    {
      title: 'Template',
      dataIndex: 'template',
      width: 160,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: 'Error',
      dataIndex: 'error',
      ellipsis: true,
      render: (v: string | null, row: EmailDeliveryItem) =>
        v ? <Tooltip title={v}><Typography.Text type={row.status === 'failed' ? 'danger' : undefined}>{v}</Typography.Text></Tooltip> : '—',
    },
  ];

  return (
    <>
      <PageHeader title="Email Log" breadcrumbs={[{ label: 'Email Log' }]} />

      {data && !data.email_configured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="SMTP is not configured, so nothing is being sent"
          description="Every message below is recorded as skipped rather than failed: it was never attempted. Set SMTP_HOST, SMTP_PASSWORD and SMTP_FROM_EMAIL — without them no user can be activated or notified by email."
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {(['sent', 'failed', 'skipped'] as EmailStatus[]).map((s) => (
          <Col xs={24} sm={8} key={s}>
            <Card>
              <Statistic
                title={s.charAt(0).toUpperCase() + s.slice(1)}
                value={totals[s] ?? 0}
                valueStyle={{ color: s === 'sent' ? '#52c41a' : s === 'failed' ? '#ff4d4f' : '#faad14' }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="Status"
          allowClear
          style={{ width: 160 }}
          value={status}
          onChange={(v) => { setStatus(v); setPage(1); }}
          options={[
            { value: 'sent', label: 'Sent' },
            { value: 'failed', label: 'Failed' },
            { value: 'skipped', label: 'Skipped' },
          ]}
        />
      </Space>

      <Card>
        <Table
          rowKey="id"
          loading={isLoading}
          dataSource={data?.items ?? []}
          columns={columns}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
        />
      </Card>
    </>
  );
};

export default EmailLogPage;

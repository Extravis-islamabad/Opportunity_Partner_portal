/**
 * POC tracking.
 *
 * Lists every POC with its customer, partner, country, dates, and the
 * five-stage checklist. Admins and sales reps drive the stages inline;
 * partners get the same view read-only.
 */
import React, { useState } from 'react';
import {
  Card, Table, Tag, Row, Col, Statistic, Select, Input, Space, Button, Modal,
  Form, DatePicker, Radio, message, Typography, Progress, Tooltip,
} from 'antd';
import {
  RocketOutlined, CheckCircleOutlined, CloseCircleOutlined,
  WarningOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { pocsApi, dashboardApi, exportsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import ExportMenu from '@/components/common/ExportMenu';
import { formatChartUsd } from '@/components/dashboard/BrandWidgets';
import { PocStageTracker, PocStatusTag, PocStageFunnel } from '@/components/dashboard/PocWidgets';
import type { PocResponse, PocStageState, PocStatus } from '@/types';

const { Title, Text } = Typography;

const PocListPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Only admins and sales reps drive POC progress; partners are read-only.
  const canEdit = user?.role === 'admin' || user?.role === 'sales_rep';

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<PocStatus | undefined>();
  const [search, setSearch] = useState('');
  const [closing, setClosing] = useState<PocResponse | null>(null);
  const [closeForm] = Form.useForm();

  const { data: list, isLoading } = useQuery({
    queryKey: ['pocs', page, status, search],
    queryFn: async () =>
      (await pocsApi.list({ page, page_size: 20, status, search: search || undefined })).data,
  });

  const { data: summary } = useQuery({
    queryKey: ['poc-summary'],
    queryFn: async () => (await dashboardApi.getPocSummary()).data,
    enabled: canEdit,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['pocs'] });
    queryClient.invalidateQueries({ queryKey: ['poc-summary'] });
  };

  const stageMutation = useMutation({
    mutationFn: ({ poc, stage }: { poc: PocResponse; stage: PocStageState }) =>
      // Toggle: completed stages clear, incomplete ones stamp today.
      pocsApi.setStage(poc.id, stage.key, stage.completed ? null : dayjs().format('YYYY-MM-DD')),
    onSuccess: (_res, vars) => {
      message.success(`${vars.stage.label} ${vars.stage.completed ? 'cleared' : 'marked complete'}`);
      invalidate();
    },
    onError: (e: { response?: { data?: { message?: string } } }) =>
      message.error(e.response?.data?.message ?? 'Could not update the stage'),
  });

  const closeMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: Record<string, unknown> }) =>
      pocsApi.close(id, values as never),
    onSuccess: () => {
      message.success('POC closed');
      setClosing(null);
      closeForm.resetFields();
      invalidate();
    },
    onError: (e: { response?: { data?: { message?: string } } }) =>
      message.error(e.response?.data?.message ?? 'Could not close the POC'),
  });

  const columns = [
    {
      title: 'Customer',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string, r: PocResponse) => (
        <div>
          <a onClick={() => navigate(`/opportunities/${r.opportunity_id}`)} style={{ fontWeight: 600 }}>
            {v}
          </a>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>{r.opportunity_name}</Text>
          </div>
        </div>
      ),
    },
    {
      title: 'Partner',
      dataIndex: 'company_name',
      key: 'company_name',
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: 'Country',
      dataIndex: 'country',
      key: 'country',
      render: (v: string | null, r: PocResponse) => (
        <div>
          <div>{v ?? '—'}</div>
          {r.city && <Text type="secondary" style={{ fontSize: 11 }}>{r.city}</Text>}
        </div>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: PocStatus, r: PocResponse) => (
        <Space direction="vertical" size={2}>
          <PocStatusTag status={v} />
          {r.is_overdue && (
            <Tag color="#f59e0b" style={{ border: 'none', fontSize: 10 }}>
              <WarningOutlined /> Overdue
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'Dates',
      key: 'dates',
      render: (_: unknown, r: PocResponse) => (
        <div style={{ fontSize: 11 }}>
          <div>Start: {r.start_date ?? '—'}</div>
          <div>End: {r.end_date ?? (r.target_end_date ? `${r.target_end_date} (target)` : '—')}</div>
          {r.days_running !== null && (
            <Text type="secondary"><ClockCircleOutlined /> {r.days_running}d</Text>
          )}
        </div>
      ),
    },
    {
      title: 'Progress',
      key: 'progress',
      width: 130,
      render: (_: unknown, r: PocResponse) => (
        <Tooltip title={r.current_stage_label ? `Now: ${r.current_stage_label}` : 'All stages complete'}>
          <Progress
            percent={Math.round((r.completed_stage_count / r.total_stage_count) * 100)}
            size="small"
            strokeColor="#3750ed"
            format={() => `${r.completed_stage_count}/${r.total_stage_count}`}
          />
        </Tooltip>
      ),
    },
    {
      title: 'Worth',
      dataIndex: 'worth',
      key: 'worth',
      render: (v: string | null) => (v ? formatChartUsd(Number(v)) : '—'),
    },
    ...(canEdit
      ? [{
          title: 'Actions',
          key: 'actions',
          render: (_: unknown, r: PocResponse) =>
            r.status === 'running' ? (
              <Button size="small" onClick={() => setClosing(r)}>Close</Button>
            ) : r.closed_at ? (
              <Button
                size="small"
                type="link"
                onClick={() =>
                  pocsApi.reopen(r.id).then(() => { message.success('POC reopened'); invalidate(); })
                }
              >
                Reopen
              </Button>
            ) : null,
        }]
      : []),
  ];

  const exportParams = { status, search: search || undefined };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            <RocketOutlined style={{ color: '#3750ed', marginRight: 8 }} />
            POC Tracking
          </Title>
          <Text type="secondary">
            A POC starts when the VM is allocated and runs through five stages. It stays running until
            someone closes it successful or unsuccessful.
          </Text>
        </div>
        <ExportMenu
          filenamePrefix="pocs"
          pdf={() => exportsApi.pocsPdf(exportParams)}
          xlsx={() => exportsApi.pocsXlsx(exportParams)}
        />
      </div>

      {summary && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={12} sm={8} lg={4}>
            <Card bordered={false} style={{ borderRadius: 12 }}>
              <Statistic title="Running" value={summary.running} valueStyle={{ color: '#3750ed' }} prefix={<RocketOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={8} lg={4}>
            <Card bordered={false} style={{ borderRadius: 12 }}>
              <Statistic title="Successful" value={summary.successful} valueStyle={{ color: '#10b981' }} prefix={<CheckCircleOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={8} lg={4}>
            <Card bordered={false} style={{ borderRadius: 12 }}>
              <Statistic title="Unsuccessful" value={summary.unsuccessful} valueStyle={{ color: '#ef4444' }} prefix={<CloseCircleOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={8} lg={4}>
            <Card bordered={false} style={{ borderRadius: 12 }}>
              <Statistic
                title="Success Rate"
                value={summary.success_rate ?? 0}
                suffix="%"
                precision={1}
                valueStyle={{ color: summary.success_rate === null ? '#94a3b8' : '#10b981' }}
              />
              <Text type="secondary" style={{ fontSize: 10 }}>of closed POCs</Text>
            </Card>
          </Col>
          <Col xs={12} sm={8} lg={4}>
            <Card bordered={false} style={{ borderRadius: 12 }}>
              <Statistic
                title="Avg Duration"
                value={summary.avg_duration_days ?? 0}
                suffix="d"
                precision={0}
                valueStyle={{ color: '#a064f3' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} lg={4}>
            <Card bordered={false} style={{ borderRadius: 12 }}>
              <Statistic
                title="Overdue"
                value={summary.overdue}
                valueStyle={{ color: summary.overdue > 0 ? '#f59e0b' : '#94a3b8' }}
                prefix={<WarningOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      {summary && summary.running > 0 && (
        <Card title="Stage funnel — running POCs" bordered={false} style={{ borderRadius: 12, marginTop: 16 }}>
          <PocStageFunnel data={summary.by_stage} />
        </Card>
      )}

      <Card bordered={false} style={{ borderRadius: 12, marginTop: 16 }}>
        <Space style={{ marginBottom: 16 }} wrap>
          <Input.Search
            placeholder="Search customer"
            allowClear
            style={{ width: 240 }}
            onSearch={(v) => { setSearch(v); setPage(1); }}
          />
          <Select
            placeholder="All statuses"
            allowClear
            style={{ width: 180 }}
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); }}
            options={[
              { value: 'not_started', label: 'Not Started' },
              { value: 'running', label: 'Running' },
              { value: 'successful', label: 'Successful' },
              { value: 'unsuccessful', label: 'Unsuccessful' },
            ]}
          />
        </Space>

        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={list?.items ?? []}
          scroll={{ x: 1100 }}
          expandable={{
            expandedRowRender: (r: PocResponse) => (
              <div style={{ padding: '16px 8px' }}>
                <PocStageTracker
                  stages={r.stages}
                  disabled={stageMutation.isPending || !!r.closed_at}
                  onToggle={
                    canEdit && !r.closed_at
                      ? (stage) => stageMutation.mutate({ poc: r, stage })
                      : undefined
                  }
                />
                {r.closed_at && (
                  <div style={{ marginTop: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      Closed {dayjs(r.closed_at).format('YYYY-MM-DD')}
                      {r.closed_by_name ? ` by ${r.closed_by_name}` : ''}
                      {r.failure_reason ? ` — ${r.failure_reason}` : ''}
                    </Text>
                    {r.outcome_notes && (
                      <div><Text style={{ fontSize: 12 }}>{r.outcome_notes}</Text></div>
                    )}
                  </div>
                )}
              </div>
            ),
          }}
          pagination={{
            current: page,
            pageSize: 20,
            total: list?.total ?? 0,
            onChange: setPage,
            showTotal: (t) => `${t} POC${t === 1 ? '' : 's'}`,
          }}
        />
      </Card>

      <Modal
        title={`Close POC — ${closing?.customer_name ?? ''}`}
        open={!!closing}
        onCancel={() => { setClosing(null); closeForm.resetFields(); }}
        onOk={() => closeForm.submit()}
        confirmLoading={closeMutation.isPending}
        okText="Close POC"
      >
        <Form
          form={closeForm}
          layout="vertical"
          initialValues={{ successful: true, end_date: dayjs() }}
          onFinish={(values) => {
            if (!closing) return;
            closeMutation.mutate({
              id: closing.id,
              values: {
                successful: values.successful,
                end_date: values.end_date ? values.end_date.format('YYYY-MM-DD') : null,
                outcome_notes: values.outcome_notes ?? null,
                failure_reason: values.successful ? null : (values.failure_reason ?? null),
              },
            });
          }}
        >
          <Form.Item name="successful" label="Outcome" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value={true}>Successful</Radio.Button>
              <Radio.Button value={false}>Unsuccessful</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="end_date" label="End date" rules={[{ required: true, message: 'Pick the end date' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          {/* failure_reason only applies to a lost POC */}
          <Form.Item noStyle shouldUpdate={(p, c) => p.successful !== c.successful}>
            {({ getFieldValue }) =>
              getFieldValue('successful') === false ? (
                <Form.Item name="failure_reason" label="Reason">
                  <Input placeholder="e.g. lost on latency benchmarks" maxLength={255} />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="outcome_notes" label="Notes">
            <Input.TextArea rows={3} placeholder="What happened?" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PocListPage;

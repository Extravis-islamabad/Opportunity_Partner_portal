/**
 * Sales rep dashboard.
 *
 * Scoped to the opportunities the rep is assigned to, plus every POC they are
 * on the team of (the backend ORs the two in poc_service.poc_access_clause —
 * nothing here is client-side filtering). Deliberately does not reuse
 * PartnerDashboard, which calls partner-only endpoints a rep is denied.
 */
import React from 'react';
import { Card, Row, Col, Statistic, Typography, Table, Empty, Tag, Progress, Space } from 'antd';
import {
  RocketOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined,
  FundProjectionScreenOutlined, DeploymentUnitOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { dashboardApi, opportunitiesApi, pocsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { formatChartUsd } from '@/components/dashboard/BrandWidgets';
import { PocStageFunnel, PocStatusTag } from '@/components/dashboard/PocWidgets';
import type { OpportunityListItem, PocResponse } from '@/types';

const { Title, Text } = Typography;

const SalesRepDashboard: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: poc, isLoading: pocLoading } = useQuery({
    queryKey: ['poc-summary'],
    queryFn: async () => (await dashboardApi.getPocSummary()).data,
  });

  const { data: deployment } = useQuery({
    queryKey: ['deployment-analytics'],
    queryFn: async () => (await dashboardApi.getDeploymentAnalytics(12)).data,
  });

  const { data: opps, isLoading: oppsLoading } = useQuery({
    queryKey: ['my-opportunities'],
    queryFn: async () => (await opportunitiesApi.list({ page: 1, page_size: 10 })).data,
  });

  // Includes POCs assigned via the team roster, not only those on
  // opportunities where this rep is the named owner.
  const { data: pocs, isLoading: pocsLoading } = useQuery({
    queryKey: ['my-pocs'],
    queryFn: async () => (await pocsApi.list({ page: 1, page_size: 10 })).data,
  });

  const myUserId = user?.id;
  const pocColumns = [
    {
      title: 'Customer',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string | null, r: PocResponse) => (
        <a
          onClick={() => navigate(`/opportunities/${r.opportunity_id}`)}
          style={{ fontWeight: 600 }}
        >
          {v ?? '—'}
        </a>
      ),
    },
    {
      title: 'My role',
      key: 'my_role',
      // Blank when this rep owns the opportunity rather than being staffed on
      // the POC — the two are different grounds for it appearing here, and
      // the column says which.
      render: (_: unknown, r: PocResponse) => {
        const mine = r.team.find((m) => m.user_id === myUserId);
        return mine ? (
          <Tag color="#3750ed" style={{ border: 'none' }}>{mine.role_label}</Tag>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>Opportunity owner</Text>
        );
      },
    },
    {
      title: 'Stage',
      key: 'stage',
      render: (_: unknown, r: PocResponse) => (
        <Text style={{ fontSize: 12 }}>
          {r.current_stage_label ?? 'All stages done'}
          <Text type="secondary">{` (${r.completed_stage_count}/${r.total_stage_count})`}</Text>
        </Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (_: unknown, r: PocResponse) => (
        <Space size={4}>
          <PocStatusTag status={r.status} />
          {r.is_overdue && <Tag color="#f59e0b" style={{ border: 'none' }}>Overdue</Tag>}
        </Space>
      ),
    },
    {
      title: 'Team',
      key: 'team',
      render: (_: unknown, r: PocResponse) =>
        r.team.length > 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {r.team.map((m) => m.user_name).filter(Boolean).join(', ')}
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ),
    },
  ];

  const columns = [
    {
      title: 'Customer',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string, r: OpportunityListItem) => (
        <a onClick={() => navigate(`/opportunities/${r.id}`)} style={{ fontWeight: 600 }}>{v}</a>
      ),
    },
    { title: 'Partner', dataIndex: 'company_name', key: 'company_name', render: (v: string | null) => v ?? '—' },
    { title: 'Country', dataIndex: 'country', key: 'country' },
    {
      title: 'Worth',
      dataIndex: 'worth',
      key: 'worth',
      render: (v: string) => formatChartUsd(Number(v)),
    },
    {
      title: 'Stage',
      dataIndex: 'stage_probability',
      key: 'stage_probability',
      render: (v: string | null) =>
        v ? <Tag color="#3750ed" style={{ border: 'none' }}>{(Number(v) * 100).toFixed(0)}%</Tag> : '—',
    },
    { title: 'Quarter', dataIndex: 'time_frame', key: 'time_frame', render: (v: string | null) => v ?? '—' },
  ];

  return (
    <div>
      <Title level={3} style={{ marginBottom: 4 }}>
        Welcome back, {user?.full_name?.split(' ')[0]}
      </Title>
      <Text type="secondary">Your assigned opportunities, POCs, and deployments.</Text>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={pocLoading}>
            <Statistic title="Running POCs" value={poc?.running ?? 0} prefix={<RocketOutlined />} valueStyle={{ color: '#3750ed' }} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={pocLoading}>
            <Statistic title="Successful" value={poc?.successful ?? 0} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={pocLoading}>
            <Statistic title="Unsuccessful" value={poc?.unsuccessful ?? 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#ef4444' }} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={pocLoading}>
            <Statistic
              title="Overdue POCs"
              value={poc?.overdue ?? 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: (poc?.overdue ?? 0) > 0 ? '#f59e0b' : '#94a3b8' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={pocLoading}>
            <Statistic
              title="POC Success Rate"
              value={poc?.success_rate ?? 0}
              suffix="%"
              precision={1}
              valueStyle={{ color: '#10b981' }}
            />
            <Progress percent={poc?.success_rate ?? 0} strokeColor="#10b981" showInfo={false} style={{ marginTop: 8 }} />
            <Text type="secondary" style={{ fontSize: 11 }}>across closed POCs</Text>
          </Card>
        </Col>
        <Col xs={12} lg={8}>
          <Card variant="borderless" style={{ borderRadius: 12 }}>
            <Statistic
              title="Devices Deployed"
              value={deployment?.total_devices ?? 0}
              prefix={<DeploymentUnitOutlined />}
              valueStyle={{ color: '#a064f3' }}
            />
          </Card>
        </Col>
        <Col xs={12} lg={8}>
          <Card variant="borderless" style={{ borderRadius: 12 }}>
            <Statistic
              title="Pipeline in POC"
              value={formatChartUsd(Number(poc?.running_worth ?? 0))}
              prefix={<FundProjectionScreenOutlined />}
              valueStyle={{ color: '#3750ed' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card title="My POC stage funnel" variant="borderless" style={{ borderRadius: 12 }} loading={pocLoading}>
            {poc ? <PocStageFunnel data={poc.by_stage} /> : null}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="My opportunities" variant="borderless" style={{ borderRadius: 12 }}>
            <Table
              rowKey="id"
              size="small"
              loading={oppsLoading}
              columns={columns}
              dataSource={opps?.items ?? []}
              pagination={false}
              scroll={{ x: 640 }}
              locale={{ emptyText: <Empty description="No opportunities assigned to you yet" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <Card title="POCs I'm working on" variant="borderless" style={{ borderRadius: 12 }}>
            <Table
              rowKey="id"
              size="small"
              loading={pocsLoading}
              columns={pocColumns}
              dataSource={pocs?.items ?? []}
              pagination={false}
              scroll={{ x: 720 }}
              locale={{
                emptyText: (
                  <Empty
                    description="No POCs assigned to you yet"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                ),
              }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default SalesRepDashboard;

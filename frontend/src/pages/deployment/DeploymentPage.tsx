/**
 * Deployment tab.
 *
 * Two halves of the same story:
 *   1. POC-side deployment activity — stage funnel and monthly throughput.
 *   2. Post-PO rollout — devices/nodes licensed, licence state, expiries.
 */
import React from 'react';
import {
  Card, Row, Col, Statistic, Table, Tag, Typography, Empty, Tooltip, Progress, Alert, Space,
} from 'antd';
import {
  DeploymentUnitOutlined, ClusterOutlined, SafetyCertificateOutlined,
  WarningOutlined, RocketOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { dashboardApi, exportsApi } from '@/api/endpoints';
import ExportMenu from '@/components/common/ExportMenu';
import { PocStageFunnel } from '@/components/dashboard/PocWidgets';
import type { ExpiringLicenseItem, LicenseStatusCount, DeploymentMonthPoint } from '@/types';

const { Title, Text } = Typography;

const LICENSE_COLORS: Record<string, string> = {
  pending_activation: '#94a3b8',
  active: '#10b981',
  expiring_soon: '#f59e0b',
  expired: '#ef4444',
};

// ---------------------------------------------------------------------------
// Monthly started-vs-completed bars
// ---------------------------------------------------------------------------
const MonthlyActivity: React.FC<{ data: DeploymentMonthPoint[] }> = ({ data }) => {
  const max = Math.max(...data.flatMap((d) => [d.started, d.completed]), 1);
  if (!data.some((d) => d.started || d.completed)) {
    return <Empty description="No POC activity yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  return (
    <div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
        <span style={{ fontSize: 11 }}>
          <span style={{ width: 10, height: 10, background: '#3750ed', display: 'inline-block', borderRadius: 2, marginRight: 4 }} />
          Started
        </span>
        <span style={{ fontSize: 11 }}>
          <span style={{ width: 10, height: 10, background: '#10b981', display: 'inline-block', borderRadius: 2, marginRight: 4 }} />
          Completed
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 180 }}>
        {data.map((d) => (
          <div key={d.month} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 150, width: '100%', justifyContent: 'center' }}>
              <Tooltip title={`${d.started} started`}>
                <div style={{ width: '40%', height: `${(d.started / max) * 100}%`, background: '#3750ed', borderRadius: '3px 3px 0 0', minHeight: d.started ? 3 : 0 }} />
              </Tooltip>
              <Tooltip title={`${d.completed} completed`}>
                <div style={{ width: '40%', height: `${(d.completed / max) * 100}%`, background: '#10b981', borderRadius: '3px 3px 0 0', minHeight: d.completed ? 3 : 0 }} />
              </Tooltip>
            </div>
            <Text type="secondary" style={{ fontSize: 9, marginTop: 4 }}>{d.month.slice(5)}</Text>
          </div>
        ))}
      </div>
    </div>
  );
};

const DeploymentPage: React.FC = () => {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['deployment-analytics'],
    queryFn: async () => (await dashboardApi.getDeploymentAnalytics(12)).data,
  });

  const expiringColumns = [
    {
      title: 'Customer',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (v: string, r: ExpiringLicenseItem) => (
        <a onClick={() => navigate(`/opportunities/${r.opportunity_id}`)} style={{ fontWeight: 600 }}>{v}</a>
      ),
    },
    { title: 'Partner', dataIndex: 'company_name', key: 'company_name', render: (v: string | null) => v ?? '—' },
    { title: 'Country', dataIndex: 'country', key: 'country', render: (v: string | null) => v ?? '—' },
    {
      title: 'Devices / Nodes',
      key: 'scale',
      render: (_: unknown, r: ExpiringLicenseItem) => `${r.device_count ?? 0} / ${r.node_count ?? 0}`,
    },
    { title: 'Expires', dataIndex: 'license_expires_at', key: 'license_expires_at' },
    {
      title: 'In',
      dataIndex: 'days_until_expiry',
      key: 'days_until_expiry',
      render: (d: number) => (
        <Tag color={d <= 30 ? '#ef4444' : '#f59e0b'} style={{ border: 'none', fontWeight: 600 }}>
          {d}d
        </Tag>
      ),
    },
  ];

  const totalLicensed = (data?.licenses_by_status ?? []).reduce((a, s) => a + s.count, 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            <DeploymentUnitOutlined style={{ color: '#3750ed', marginRight: 8 }} />
            Deployment
          </Title>
          <Text type="secondary">POC deployment activity, and device/node rollout once the PO lands.</Text>
        </div>
        <Space>
          <ExportMenu
            label="Export POCs"
            filenamePrefix="pocs"
            pdf={() => exportsApi.pocsPdf()}
            xlsx={() => exportsApi.pocsXlsx()}
          />
          <ExportMenu
            label="Export Licences"
            filenamePrefix="licenses"
            pdf={() => exportsApi.licensesPdf()}
            xlsx={() => exportsApi.licensesXlsx()}
          />
        </Space>
      </div>

      {data && data.expiring_soon.length > 0 && (
        <Alert
          style={{ marginTop: 16, borderRadius: 8 }}
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message={`${data.expiring_soon.length} licence${data.expiring_soon.length === 1 ? '' : 's'} expiring within 90 days`}
          description="Chase renewals before they lapse — see the table below."
        />
      )}

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            <Statistic title="Active POCs" value={data?.active_pocs ?? 0} prefix={<RocketOutlined />} valueStyle={{ color: '#3750ed' }} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            <Statistic title="Devices Deployed" value={data?.total_devices ?? 0} prefix={<ClusterOutlined />} valueStyle={{ color: '#a064f3' }} />
            <Text type="secondary" style={{ fontSize: 10 }}>across live licences</Text>
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            <Statistic title="Nodes Deployed" value={data?.total_nodes ?? 0} prefix={<ClusterOutlined />} valueStyle={{ color: '#7a2280' }} />
            <Text type="secondary" style={{ fontSize: 10 }}>across live licences</Text>
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            <Statistic title="Active Licences" value={data?.active_licenses ?? 0} prefix={<SafetyCertificateOutlined />} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="POC stage funnel" variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            {data ? <PocStageFunnel data={data.stage_funnel} /> : null}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="POC activity — started vs completed" variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            {data ? <MonthlyActivity data={data.monthly_activity} /> : null}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card title="Licences by status" variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            {totalLicensed === 0 ? (
              <Empty description="No licences recorded yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              (data?.licenses_by_status ?? []).map((s: LicenseStatusCount) => (
                <div key={s.status} style={{ marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ fontSize: 12, fontWeight: 600 }}>{s.label}</Text>
                    <Text style={{ fontSize: 12, fontWeight: 700, color: LICENSE_COLORS[s.status] }}>
                      {s.count}
                    </Text>
                  </div>
                  <Progress
                    percent={totalLicensed ? Math.round((s.count / totalLicensed) * 100) : 0}
                    strokeColor={LICENSE_COLORS[s.status]}
                    showInfo={false}
                    size="small"
                  />
                  <Text type="secondary" style={{ fontSize: 10 }}>
                    {s.device_count} devices · {s.node_count} nodes
                  </Text>
                </div>
              ))
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Licences expiring in the next 90 days" variant="borderless" style={{ borderRadius: 12 }} loading={isLoading}>
            <Table
              rowKey="opportunity_id"
              size="small"
              columns={expiringColumns}
              dataSource={data?.expiring_soon ?? []}
              pagination={false}
              scroll={{ x: 700 }}
              locale={{ emptyText: <Empty description="Nothing expiring soon" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DeploymentPage;

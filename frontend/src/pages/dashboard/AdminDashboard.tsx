import React from 'react';
import { Row, Col, Card, Statistic, Skeleton, Alert, Empty, Typography, Tag, Table, Progress, Badge, Button, Divider } from 'antd';
import {
  BankOutlined,
  TeamOutlined,
  FundProjectionScreenOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  WarningOutlined,
  FileTextOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/components/common/PageHeader';
import type { DashboardStats, OpportunityStatusBreakdown, MonthlyOpportunityData, OverdueOpportunityItem } from '@/types';

const statusColors: Record<string, string> = {
  approved: '#52c41a',
  rejected: '#f5222d',
  pending_review: '#fa8c16',
  under_review: '#1890ff',
  draft: '#d9d9d9',
  removed: '#8c8c8c',
};

const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['admin-dashboard-stats'],
    queryFn: async () => {
      const res = await dashboardApi.getAdminStats();
      return res.data;
    },
  });

  const { data: breakdown } = useQuery({
    queryKey: ['opportunity-breakdown'],
    queryFn: async () => {
      const res = await dashboardApi.getOpportunityBreakdown();
      return res.data;
    },
  });

  const { data: monthly } = useQuery({
    queryKey: ['monthly-data'],
    queryFn: async () => {
      const res = await dashboardApi.getMonthlyData(12);
      return res.data;
    },
  });

  if (error) {
    return <Alert type="error" message="Failed to load dashboard" description={String(error)} showIcon />;
  }

  const approvalRate = stats && stats.total_opportunities > 0
    ? Math.round((stats.total_approved / stats.total_opportunities) * 100)
    : 0;

  const overdueColumns = [
    { title: 'Opportunity', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: 'Company', dataIndex: 'company_name', key: 'company_name', ellipsis: true },
    {
      title: 'Closing Date',
      dataIndex: 'closing_date',
      key: 'closing_date',
      render: (d: string) => {
        const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400000);
        return <Typography.Text type="danger">{d} ({days}d overdue)</Typography.Text>;
      },
    },
    {
      title: 'Worth',
      dataIndex: 'worth',
      key: 'worth',
      render: (v: string) => `$${Number(v).toLocaleString()}`,
    },
    {
      title: '',
      key: 'action',
      render: (_: unknown, record: OverdueOpportunityItem) => (
        <Button type="link" size="small" onClick={() => navigate(`/opportunities/${record.id}`)}>View</Button>
      ),
    },
  ];

  const monthlyColumns = [
    { title: 'Month', dataIndex: 'month', key: 'month' },
    {
      title: 'Submitted',
      dataIndex: 'submitted',
      key: 'submitted',
      render: (v: number) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'Approved',
      dataIndex: 'approved',
      key: 'approved',
      render: (v: number) => <Tag color="green">{v}</Tag>,
    },
    {
      title: 'Rejected',
      dataIndex: 'rejected',
      key: 'rejected',
      render: (v: number) => <Tag color="red">{v}</Tag>,
    },
  ];

  return (
    <>
      <PageHeader title="Admin Dashboard" subtitle="Overview of partner portal activity" />

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 12 }} />
      ) : stats ? (
        <>
          {/* Overdue Alert Banner */}
          {stats.overdue_count > 0 && (
            <Alert
              type="error"
              showIcon
              icon={<WarningOutlined />}
              message={`${stats.overdue_count} opportunit${stats.overdue_count === 1 ? 'y has' : 'ies have'} passed their closing date and are still pending review`}
              style={{ marginBottom: 16 }}
              action={<Button size="small" danger onClick={() => navigate('/opportunities?status=pending_review')}>Review Now</Button>}
            />
          )}

          {/* Pending Doc Requests Banner */}
          {stats.pending_doc_requests > 0 && (
            <Alert
              type="warning"
              showIcon
              icon={<FileTextOutlined />}
              message={`${stats.pending_doc_requests} document request${stats.pending_doc_requests === 1 ? '' : 's'} awaiting action`}
              style={{ marginBottom: 16 }}
              action={<Button size="small" onClick={() => navigate('/doc-requests')}>Review</Button>}
            />
          )}

          {/* Row 1: Key Metrics */}
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} lg={6}>
              <Card hoverable onClick={() => navigate('/companies')}>
                <Statistic title="Total Companies" value={stats.total_companies} prefix={<BankOutlined style={{ color: '#1890ff' }} />} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card hoverable onClick={() => navigate('/users')}>
                <Statistic title="Total Partners" value={stats.total_partners} prefix={<TeamOutlined style={{ color: '#722ed1' }} />} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card hoverable onClick={() => navigate('/opportunities')}>
                <Statistic title="Total Opportunities" value={stats.total_opportunities} prefix={<FundProjectionScreenOutlined style={{ color: '#13c2c2' }} />} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic title="Pipeline Worth" value={Number(stats.total_worth)} prefix={<DollarOutlined style={{ color: '#faad14' }} />} precision={0} formatter={(v) => `$${Number(v).toLocaleString()}`} />
              </Card>
            </Col>
          </Row>

          {/* Row 2: Opportunity Status + Approval Rate */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} sm={8} lg={6}>
              <Card>
                <Statistic title="Approved" value={stats.total_approved} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
                <div style={{ marginTop: 8 }}>
                  <Typography.Text type="secondary">
                    Worth: ${Number(stats.approved_worth).toLocaleString()}
                  </Typography.Text>
                </div>
              </Card>
            </Col>
            <Col xs={24} sm={8} lg={6}>
              <Card>
                <Statistic title="Rejected" value={stats.total_rejected} valueStyle={{ color: '#f5222d' }} prefix={<CloseCircleOutlined />} />
              </Card>
            </Col>
            <Col xs={24} sm={8} lg={6}>
              <Card>
                <Statistic title="Pending Review" value={stats.total_pending} valueStyle={{ color: '#fa8c16' }} prefix={<ClockCircleOutlined />} />
                {stats.overdue_count > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <Badge status="error" text={<Typography.Text type="danger">{stats.overdue_count} overdue</Typography.Text>} />
                  </div>
                )}
              </Card>
            </Col>
            <Col xs={24} sm={24} lg={6}>
              <Card>
                <div style={{ textAlign: 'center' }}>
                  <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>Approval Rate</Typography.Text>
                  <Progress
                    type="circle"
                    percent={approvalRate}
                    size={80}
                    strokeColor={approvalRate >= 50 ? '#52c41a' : '#faad14'}
                  />
                </div>
              </Card>
            </Col>
          </Row>

          {/* Row 3: Status Breakdown + Monthly Trend */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={10}>
              <Card title="Opportunity Status Breakdown" style={{ height: '100%' }}>
                {breakdown && breakdown.length > 0 ? (
                  <div>
                    {breakdown.map((item: OpportunityStatusBreakdown) => {
                      const total = breakdown.reduce((s, b) => s + b.count, 0);
                      const pct = total > 0 ? Math.round((item.count / total) * 100) : 0;
                      return (
                        <div key={item.status} style={{ marginBottom: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <Tag color={statusColors[item.status] || 'default'}>
                              {item.status.replace(/_/g, ' ').toUpperCase()}
                            </Tag>
                            <Typography.Text strong>{item.count}</Typography.Text>
                          </div>
                          <Progress
                            percent={pct}
                            showInfo={false}
                            strokeColor={statusColors[item.status] || '#1890ff'}
                            size="small"
                          />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <Empty description="No data" />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card title="Monthly Trend (Last 12 Months)" style={{ height: '100%' }}>
                {monthly && monthly.length > 0 ? (
                  <Table
                    dataSource={monthly.map((m: MonthlyOpportunityData) => ({ ...m, key: m.month }))}
                    columns={monthlyColumns}
                    pagination={false}
                    size="small"
                    scroll={{ y: 280 }}
                  />
                ) : (
                  <Empty description="No data yet" />
                )}
              </Card>
            </Col>
          </Row>

          {/* Row 4: Overdue Opportunities */}
          {stats.overdue_opportunities.length > 0 && (
            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col span={24}>
                <Card
                  title={
                    <span>
                      <ExclamationCircleOutlined style={{ color: '#f5222d', marginRight: 8 }} />
                      Overdue Opportunities ({stats.overdue_count})
                    </span>
                  }
                >
                  <Table
                    dataSource={stats.overdue_opportunities.map((o: OverdueOpportunityItem) => ({ ...o, key: o.id }))}
                    columns={overdueColumns}
                    pagination={false}
                    size="small"
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* Row 5: Quick Actions */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} sm={8}>
              <Card hoverable onClick={() => navigate('/companies/new')} style={{ textAlign: 'center' }}>
                <BankOutlined style={{ fontSize: 28, color: '#1890ff', marginBottom: 8 }} />
                <div><Typography.Text strong>Add Company</Typography.Text></div>
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card hoverable onClick={() => navigate('/knowledge-base')} style={{ textAlign: 'center' }}>
                <FileTextOutlined style={{ fontSize: 28, color: '#52c41a', marginBottom: 8 }} />
                <div><Typography.Text strong>Knowledge Base</Typography.Text></div>
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card hoverable onClick={() => navigate('/lms')} style={{ textAlign: 'center' }}>
                <TeamOutlined style={{ fontSize: 28, color: '#722ed1', marginBottom: 8 }} />
                <div><Typography.Text strong>LMS / Training</Typography.Text></div>
              </Card>
            </Col>
          </Row>
        </>
      ) : (
        <Empty description="No dashboard data available" />
      )}
    </>
  );
};

export default AdminDashboard;

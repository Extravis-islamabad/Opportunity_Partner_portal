import React from 'react';
import { Row, Col, Card, Statistic, Skeleton, Alert, Empty, Tag, Progress, Typography, Button } from 'antd';
import {
  FundProjectionScreenOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ReadOutlined,
  TrophyOutlined,
  DollarOutlined,
  EditOutlined,
  ArrowRightOutlined,
  StarOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/components/common/PageHeader';

const tierColors: Record<string, string> = {
  silver: '#a0a0a0',
  gold: '#faad14',
  platinum: '#1890ff',
};

const tierLabels: Record<string, string> = {
  silver: 'Silver',
  gold: 'Gold',
  platinum: 'Platinum',
};

const PartnerDashboard: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['partner-dashboard-stats'],
    queryFn: async () => {
      const res = await dashboardApi.getPartnerStats();
      return res.data;
    },
  });

  if (error) {
    return <Alert type="error" message="Failed to load dashboard" showIcon />;
  }

  const winRate = stats && stats.my_opportunities > 0
    ? Math.round((stats.my_approved / stats.my_opportunities) * 100)
    : 0;

  const lmsRate = stats && stats.lms_courses_enrolled > 0
    ? Math.round((stats.lms_courses_completed / stats.lms_courses_enrolled) * 100)
    : 0;

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user?.full_name ?? ''}`}
        subtitle="Your partner dashboard overview"
        extra={
          stats && (
            <Tag
              color={tierColors[stats.company_tier] ?? 'default'}
              style={{ fontSize: 14, padding: '4px 16px', fontWeight: 600 }}
            >
              <StarOutlined style={{ marginRight: 4 }} />
              {(tierLabels[stats.company_tier] ?? stats.company_tier).toUpperCase()} TIER
            </Tag>
          )
        }
      />

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 10 }} />
      ) : stats ? (
        <>
          {/* Pending doc requests alert */}
          {stats.pending_doc_requests > 0 && (
            <Alert
              type="info"
              showIcon
              icon={<FileTextOutlined />}
              message={`You have ${stats.pending_doc_requests} pending document request${stats.pending_doc_requests === 1 ? '' : 's'}`}
              style={{ marginBottom: 16 }}
              action={<Button size="small" onClick={() => navigate('/doc-requests')}>View</Button>}
            />
          )}

          {/* Row 1: Opportunity Stats */}
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} lg={6}>
              <Card hoverable onClick={() => navigate('/opportunities')}>
                <Statistic
                  title="My Opportunities"
                  value={stats.my_opportunities}
                  prefix={<FundProjectionScreenOutlined style={{ color: '#1890ff' }} />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="Approved"
                  value={stats.my_approved}
                  valueStyle={{ color: '#52c41a' }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="Pending Review"
                  value={stats.my_pending}
                  valueStyle={{ color: '#fa8c16' }}
                  prefix={<ClockCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card hoverable onClick={() => navigate('/opportunities?status=draft')}>
                <Statistic
                  title="Drafts"
                  value={stats.my_drafts}
                  prefix={<EditOutlined style={{ color: '#8c8c8c' }} />}
                />
              </Card>
            </Col>
          </Row>

          {/* Row 2: Financial + Win Rate */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="Pipeline Worth"
                  value={Number(stats.my_total_worth)}
                  prefix={<DollarOutlined style={{ color: '#faad14' }} />}
                  precision={0}
                  formatter={(v) => `$${Number(v).toLocaleString()}`}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="Approved Worth"
                  value={Number(stats.my_approved_worth)}
                  prefix={<DollarOutlined style={{ color: '#52c41a' }} />}
                  precision={0}
                  valueStyle={{ color: '#52c41a' }}
                  formatter={(v) => `$${Number(v).toLocaleString()}`}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="Rejected"
                  value={stats.my_rejected}
                  valueStyle={{ color: '#f5222d' }}
                  prefix={<CloseCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <div style={{ textAlign: 'center' }}>
                  <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>Win Rate</Typography.Text>
                  <Progress
                    type="circle"
                    percent={winRate}
                    size={72}
                    strokeColor={winRate >= 50 ? '#52c41a' : '#faad14'}
                  />
                </div>
              </Card>
            </Col>
          </Row>

          {/* Row 3: LMS + Tier Progress */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={12}>
              <Card
                title={<><ReadOutlined style={{ marginRight: 8 }} />Training Progress</>}
                extra={<Button type="link" onClick={() => navigate('/lms')}>View Courses <ArrowRightOutlined /></Button>}
                style={{ height: '100%' }}
              >
                <Row gutter={[16, 16]}>
                  <Col span={8} style={{ textAlign: 'center' }}>
                    <Statistic title="Enrolled" value={stats.lms_courses_enrolled} />
                  </Col>
                  <Col span={8} style={{ textAlign: 'center' }}>
                    <Statistic title="Completed" value={stats.lms_courses_completed} valueStyle={{ color: '#52c41a' }} />
                  </Col>
                  <Col span={8} style={{ textAlign: 'center' }}>
                    <div>
                      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>Completion</Typography.Text>
                      <Progress
                        type="circle"
                        percent={lmsRate}
                        size={60}
                        strokeColor="#722ed1"
                      />
                    </div>
                  </Col>
                </Row>
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card
                title={<><TrophyOutlined style={{ marginRight: 8, color: tierColors[stats.company_tier] }} />Tier Progress</>}
                style={{ height: '100%' }}
              >
                {stats.tier_progress ? (
                  stats.tier_progress.next_tier ? (
                    <div>
                      <div style={{ marginBottom: 16 }}>
                        <Typography.Text>
                          Current: <Tag color={tierColors[stats.company_tier]}>{(tierLabels[stats.company_tier] ?? stats.company_tier).toUpperCase()}</Tag>
                          <ArrowRightOutlined style={{ margin: '0 8px', color: '#bbb' }} />
                          Next: <Tag color={tierColors[stats.tier_progress.next_tier]}>{(tierLabels[stats.tier_progress.next_tier] ?? stats.tier_progress.next_tier).toUpperCase()}</Tag>
                        </Typography.Text>
                      </div>
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Typography.Text type="secondary">Approved Opportunities</Typography.Text>
                          <Typography.Text strong>{stats.tier_progress.opps_current} / {stats.tier_progress.opps_required}</Typography.Text>
                        </div>
                        <Progress percent={stats.tier_progress.opps_progress_pct} strokeColor="#1890ff" />
                      </div>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Typography.Text type="secondary">Completed Courses</Typography.Text>
                          <Typography.Text strong>{stats.tier_progress.courses_current} / {stats.tier_progress.courses_required}</Typography.Text>
                        </div>
                        <Progress percent={stats.tier_progress.courses_progress_pct} strokeColor="#722ed1" />
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                      <TrophyOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 12 }} />
                      <div><Typography.Text strong style={{ fontSize: 16 }}>You've reached Platinum!</Typography.Text></div>
                      <Typography.Text type="secondary">Highest tier achieved</Typography.Text>
                    </div>
                  )
                ) : (
                  <Empty description="Tier info unavailable" />
                )}
              </Card>
            </Col>
          </Row>

          {/* Row 4: Quick Actions */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} sm={8}>
              <Card hoverable onClick={() => navigate('/opportunities/new')} style={{ textAlign: 'center' }}>
                <FundProjectionScreenOutlined style={{ fontSize: 28, color: '#1890ff', marginBottom: 8 }} />
                <div><Typography.Text strong>Submit Opportunity</Typography.Text></div>
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card hoverable onClick={() => navigate('/knowledge-base')} style={{ textAlign: 'center' }}>
                <FileTextOutlined style={{ fontSize: 28, color: '#52c41a', marginBottom: 8 }} />
                <div><Typography.Text strong>Knowledge Base</Typography.Text></div>
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card hoverable onClick={() => navigate('/doc-requests')} style={{ textAlign: 'center' }}>
                <FileTextOutlined style={{ fontSize: 28, color: '#fa8c16', marginBottom: 8 }} />
                <div><Typography.Text strong>Request Document</Typography.Text></div>
              </Card>
            </Col>
          </Row>
        </>
      ) : (
        <Empty description="No dashboard data" />
      )}
    </>
  );
};

export default PartnerDashboard;

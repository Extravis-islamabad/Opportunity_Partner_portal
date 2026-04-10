import React, { useMemo } from 'react';
import {
  Row,
  Col,
  Card,
  Skeleton,
  Alert,
  Empty,
  Tag,
  Progress,
  Typography,
  Button,
  Space,
  Avatar,
} from 'antd';
import {
  FundProjectionScreenOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ReadOutlined,
  TrophyOutlined,
  DollarOutlined,
  EditOutlined,
  ArrowRightOutlined,
  StarFilled,
  RiseOutlined,
  ThunderboltFilled,
  RocketOutlined,
  CrownOutlined,
  CloseCircleOutlined,
  CheckOutlined,
  FireOutlined,
  AreaChartOutlined,
} from '@ant-design/icons';
import { Column } from '@ant-design/plots';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/components/common/PageHeader';
import {
  BrandDonut,
  BrandGauge,
  BrandLiquid,
  BrandStatPill,
  BrandStackedBars,
  BrandTimelineMetric,
  BrandSparkCards,
  BrandRingGrid,
  AchievementBadge,
  formatChartUsd,
} from '@/components/dashboard/BrandWidgets';
import type { MonthlyOpportunityData } from '@/types';

const BRAND = {
  royal500: '#3750ed',
  royal400: '#4961f1',
  royal300: '#6b7bfe',
  royal200: '#8c93f1',
  royal100: '#b4b6f7',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  violet500: '#a064f3',
  violet400: '#b370fc',
  violet600: '#7a2280',
  violet700: '#5b1965',
  violet100: '#f0e6ff',
};

const tierColors: Record<string, string> = {
  silver: '#9ca3af',
  gold: '#f59e0b',
  platinum: BRAND.royal500,
};
const tierLabels: Record<string, string> = {
  silver: 'Silver',
  gold: 'Gold',
  platinum: 'Platinum',
};

// ---------------------------------------------------------------------------
// KPI hero card (same look as admin)
// ---------------------------------------------------------------------------
interface KpiCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  gradient: string;
  hint?: string;
  onClick?: () => void;
}

const KpiCard: React.FC<KpiCardProps> = ({ title, value, icon, gradient, hint, onClick }) => (
  <Card
    bordered={false}
    hoverable={!!onClick}
    onClick={onClick}
    style={{
      background: gradient,
      color: '#ffffff',
      borderRadius: 14,
      overflow: 'hidden',
      position: 'relative',
      cursor: onClick ? 'pointer' : 'default',
      boxShadow: '0 8px 24px rgba(28, 28, 58, 0.12)',
    }}
    styles={{ body: { padding: 22 } }}
  >
    <div style={{ position: 'absolute', top: -30, right: -30, width: 130, height: 130, borderRadius: '50%', background: 'rgba(255,255,255,0.1)' }} />
    <div style={{ position: 'relative', zIndex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <Typography.Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13, fontWeight: 500 }}>{title}</Typography.Text>
        <div style={{ width: 38, height: 38, borderRadius: 10, background: 'rgba(255,255,255,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: '#ffffff' }}>
          {icon}
        </div>
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, color: '#ffffff', lineHeight: 1.1, marginBottom: 4 }}>{value}</div>
      {hint && <Typography.Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>{hint}</Typography.Text>}
    </div>
  </Card>
);

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------
const PartnerDashboard: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['partner-dashboard-stats'],
    queryFn: async () => (await dashboardApi.getPartnerStats()).data,
  });

  const { data: timeline } = useQuery({
    queryKey: ['partner-timeline'],
    queryFn: async () => (await dashboardApi.getPartnerTimeline(6)).data,
  });

  if (error) return <Alert type="error" message="Failed to load dashboard" showIcon />;
  if (isLoading) {
    return (
      <>
        <PageHeader title="Welcome back" subtitle="Loading your dashboard…" />
        <Skeleton active paragraph={{ rows: 14 }} />
      </>
    );
  }
  if (!stats) return <Empty description="No dashboard data" />;

  const winRate = stats.my_opportunities > 0
    ? Math.round((stats.my_approved / stats.my_opportunities) * 100)
    : 0;
  const lmsRate = stats.lms_courses_enrolled > 0
    ? Math.round((stats.lms_courses_completed / stats.lms_courses_enrolled) * 100)
    : 0;

  // Pipeline target for liquid gauge (1M)
  const pipelineTarget = 1_000_000;
  const liquidPercent = Math.min(100, Math.round((Number(stats.my_total_worth) / pipelineTarget) * 100));

  // ---- Chart data ---------------------------------------------------------
  // Stacked bars data for partner pipeline (replaces Area chart)
  const stackedBarsData = useMemo(() => {
    if (!timeline || !Array.isArray(timeline)) return [];
    return (timeline as MonthlyOpportunityData[]).map((m) => ({
      label: m.month,
      values: [
        { name: 'Approved', value: m.approved, color: '#10b981' },
        { name: 'Submitted', value: Math.max(0, m.submitted - m.approved - m.rejected), color: BRAND.royal400 },
        { name: 'Rejected', value: m.rejected, color: '#ef4444' },
      ],
    }));
  }, [timeline]);

  // Timeline metric: monthly approvals with delta arrows
  const timelineData = useMemo(() => {
    if (!timeline || !Array.isArray(timeline)) return [];
    return (timeline as MonthlyOpportunityData[]).map((m) => ({
      label: m.month.slice(-2) + '/' + m.month.slice(2, 4),
      value: m.approved,
    }));
  }, [timeline]);

  // Spark cards: 4 per-partner KPI sparklines
  const sparkCardsData = useMemo(() => {
    if (!timeline || !Array.isArray(timeline) || timeline.length === 0) return [];
    const arr = timeline as MonthlyOpportunityData[];
    return [
      {
        label: 'My Submissions',
        value: arr.reduce((s, m) => s + m.submitted, 0),
        series: arr.map((m) => m.submitted),
        color: BRAND.royal500,
      },
      {
        label: 'My Approvals',
        value: arr.reduce((s, m) => s + m.approved, 0),
        series: arr.map((m) => m.approved),
        color: '#10b981',
      },
      {
        label: 'My Rejections',
        value: arr.reduce((s, m) => s + m.rejected, 0),
        series: arr.map((m) => m.rejected),
        color: '#ef4444',
      },
      {
        label: 'Active Months',
        value: arr.filter((m) => m.submitted > 0).length,
        series: arr.map((m) => m.submitted > 0 ? 1 : 0),
        color: BRAND.violet500,
      },
    ];
  }, [timeline]);

  // Ring grid: partner KPIs
  const ringGridData = useMemo(() => {
    const total = stats.my_opportunities || 1;
    return [
      { label: 'Win Rate', percent: winRate },
      { label: 'Approved %', percent: Math.round((stats.my_approved / total) * 100) },
      { label: 'Pending %', percent: Math.round((stats.my_pending / total) * 100) },
      { label: 'Training %', percent: lmsRate },
    ];
  }, [stats, winRate, lmsRate]);

  // Status breakdown column chart
  const statusColumnData = [
    { status: 'Approved', value: stats.my_approved, color: '#10b981' },
    { status: 'Pending', value: stats.my_pending, color: '#f59e0b' },
    { status: 'Rejected', value: stats.my_rejected, color: '#ef4444' },
    { status: 'Drafts', value: stats.my_drafts, color: '#9ca3af' },
  ];

  // LMS donut data
  const lmsDonutData = [
    {
      label: 'Completed',
      value: stats.lms_courses_completed,
      color: BRAND.violet500,
    },
    {
      label: 'In Progress',
      value: Math.max(0, stats.lms_courses_enrolled - stats.lms_courses_completed),
      color: BRAND.royal100,
    },
  ];

  // Status pie data
  const statusPieData = [
    { label: 'Approved', value: stats.my_approved, color: '#10b981' },
    { label: 'Pending', value: stats.my_pending, color: '#f59e0b' },
    { label: 'Rejected', value: stats.my_rejected, color: '#ef4444' },
    { label: 'Drafts', value: stats.my_drafts, color: '#9ca3af' },
  ].filter((d) => d.value > 0);

  // ---- Chart configs (v2) ------------------------------------------------
  const columnConfig = {
    data: statusColumnData,
    xField: 'status',
    yField: 'value',
    colorField: 'status',
    height: 260,
    style: { radiusTopLeft: 8, radiusTopRight: 8 },
    scale: { color: { range: ['#10b981', '#f59e0b', '#ef4444', '#9ca3af'] } },
    legend: false as const,
    label: {
      text: 'value',
      style: { fontWeight: 600 },
    },
  };

  // Achievements (calculated from real stats)
  const achievements = [
    {
      icon: <FireOutlined />,
      title: 'First Win',
      description: 'Got your first approved opportunity',
      unlocked: stats.my_approved >= 1,
    },
    {
      icon: <RiseOutlined />,
      title: 'Rising Star',
      description: '5 approved opportunities',
      unlocked: stats.my_approved >= 5,
    },
    {
      icon: <CrownOutlined />,
      title: 'Top Closer',
      description: '10 approved opportunities',
      unlocked: stats.my_approved >= 10,
    },
    {
      icon: <CheckOutlined />,
      title: 'Lifelong Learner',
      description: 'Completed 3 courses',
      unlocked: stats.lms_courses_completed >= 3,
    },
    {
      icon: <DollarOutlined />,
      title: 'Million Dollar',
      description: '$1M in pipeline',
      unlocked: Number(stats.my_total_worth) >= 1_000_000,
    },
    {
      icon: <TrophyOutlined />,
      title: 'Tier Climber',
      description: 'Reached Gold or Platinum',
      unlocked: stats.company_tier !== 'silver',
    },
  ];

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user?.full_name?.split(' ')[0] ?? ''}`}
        subtitle="Here's how your pipeline is performing today"
        extra={
          <Tag style={{
            fontSize: 13,
            padding: '6px 16px',
            borderRadius: 20,
            fontWeight: 600,
            background: stats.company_tier === 'platinum' ? BRAND.royal50 : BRAND.violet100,
            color: stats.company_tier === 'platinum' ? BRAND.royal500 : BRAND.violet700,
            border: 'none',
          }}>
            <StarFilled style={{ marginRight: 6 }} />
            {(tierLabels[stats.company_tier] ?? stats.company_tier).toUpperCase()} TIER
          </Tag>
        }
      />

      {stats.pending_doc_requests > 0 && (
        <Alert
          type="info"
          showIcon
          icon={<FileTextOutlined />}
          message={`You have ${stats.pending_doc_requests} pending document request${stats.pending_doc_requests === 1 ? '' : 's'}`}
          style={{ marginBottom: 16, borderRadius: 10 }}
          action={<Button size="small" onClick={() => navigate('/doc-requests')}>View</Button>}
        />
      )}

      {/* ---------------- Hero KPI row -------------------------------------- */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="My Opportunities"
            value={stats.my_opportunities}
            icon={<FundProjectionScreenOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.royal500} 0%, ${BRAND.royal400} 100%)`}
            hint={`${stats.my_pending} pending review`}
            onClick={() => navigate('/opportunities')}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Approved"
            value={stats.my_approved}
            icon={<CheckCircleOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.violet600} 0%, ${BRAND.violet500} 100%)`}
            hint={formatChartUsd(Number(stats.my_approved_worth))}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Pipeline Worth"
            value={formatChartUsd(Number(stats.my_total_worth))}
            icon={<DollarOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.navy} 0%, ${BRAND.royal500} 100%)`}
            hint="across all stages"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Drafts"
            value={stats.my_drafts}
            icon={<EditOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.violet700} 0%, ${BRAND.violet500} 100%)`}
            hint="ready to submit"
            onClick={() => navigate('/opportunities?status=draft')}
          />
        </Col>
      </Row>

      {/* ---------------- Brand stat pills row ------------------------------ */}
      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={12} sm={8} md={6}>
          <BrandStatPill icon={<CheckCircleOutlined />} label="Won" value={stats.my_approved} color="#10b981" />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <BrandStatPill icon={<ClockCircleOutlined />} label="Pending" value={stats.my_pending} color="#f59e0b" />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <BrandStatPill icon={<CloseCircleOutlined />} label="Rejected" value={stats.my_rejected} color="#ef4444" />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <BrandStatPill icon={<ReadOutlined />} label="Courses" value={stats.lms_courses_completed} color={BRAND.violet500} />
        </Col>
      </Row>

      {/* ---------------- Win rate gauge + Liquid + Status donut ------------ */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={8}>
          <Card
            title={<Space><RiseOutlined style={{ color: BRAND.royal500 }} /><span>Win Rate</span></Space>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            <div style={{ paddingTop: 16 }}>
              <BrandGauge percent={winRate} label={`${stats.my_approved} of ${stats.my_opportunities} approved`} size={220} />
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card
            title={<Space><ThunderboltFilled style={{ color: BRAND.violet500 }} /><span>Pipeline vs Target</span></Space>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 16 }}>
              <BrandLiquid
                percent={liquidPercent}
                centerText={formatChartUsd(Number(stats.my_total_worth))}
                label={`of ${formatChartUsd(pipelineTarget)}`}
                size={180}
              />
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card
            title={<Space><AreaChartOutlined style={{ color: BRAND.royal500 }} /><span>Opportunity Status</span></Space>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            <div style={{ paddingTop: 12 }}>
              {statusPieData.length > 0 ? (
                <BrandDonut
                  data={statusPieData}
                  size={180}
                  centerLabel="Total"
                  centerValue={stats.my_opportunities}
                />
              ) : (
                <Empty description="No data yet" />
              )}
            </div>
          </Card>
        </Col>
      </Row>

      {/* ---------------- Spark cards row ----------------------------------- */}
      {sparkCardsData.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <BrandSparkCards data={sparkCardsData} />
          </Col>
        </Row>
      )}

      {/* ---------------- Pipeline stacked bars + Status column ------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            title={<Space><AreaChartOutlined style={{ color: BRAND.royal500 }} /><span>My Pipeline Breakdown</span></Space>}
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>last 6 months • hover for details</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {stackedBarsData.length > 0 ? (
              <BrandStackedBars data={stackedBarsData} height={300} />
            ) : (
              <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Empty description="Submit opportunities to see your trend" />
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={<Space><FundProjectionScreenOutlined style={{ color: BRAND.violet500 }} /><span>Status Breakdown</span></Space>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            <Column {...columnConfig} />
          </Card>
        </Col>
      </Row>

      {/* ---------------- Approvals timeline + KPI rings -------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            title={<Space><RiseOutlined style={{ color: BRAND.royal500 }} /><span>Monthly Approvals — Trend</span></Space>}
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>month-over-month change</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {timelineData.length > 0 ? (
              <BrandTimelineMetric data={timelineData} />
            ) : (
              <Empty description="Submit deals to see your monthly trend" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={<Space><RiseOutlined style={{ color: BRAND.violet500 }} /><span>My KPIs</span></Space>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            <div style={{ paddingTop: 12 }}>
              <BrandRingGrid data={ringGridData} size={92} />
            </div>
          </Card>
        </Col>
      </Row>

      {/* ---------------- LMS donut + Tier progress ------------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card
            title={<Space><ReadOutlined style={{ color: BRAND.royal500 }} /><span>Training Progress</span></Space>}
            extra={<Button type="link" size="small" onClick={() => navigate('/lms')}>Courses <ArrowRightOutlined /></Button>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            {stats.lms_courses_enrolled > 0 ? (
              <div style={{ paddingTop: 16 }}>
                <BrandDonut
                  data={lmsDonutData}
                  size={180}
                  centerLabel="Completion"
                  centerValue={`${lmsRate}%`}
                />
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <ReadOutlined style={{ fontSize: 36, color: BRAND.royal200 }} />
                <div style={{ marginTop: 12 }}>
                  <Typography.Text type="secondary">No courses yet</Typography.Text>
                </div>
                <Button type="primary" size="small" style={{ marginTop: 12 }} onClick={() => navigate('/lms')}>
                  Browse courses
                </Button>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            title={<Space><TrophyOutlined style={{ color: tierColors[stats.company_tier] }} /><span>Tier Progress</span></Space>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            {stats.tier_progress?.next_tier ? (
              <div>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  marginBottom: 20,
                  background: `linear-gradient(90deg, ${BRAND.royal50} 0%, ${BRAND.violet100} 100%)`,
                  borderRadius: 10,
                }}>
                  <Space>
                    <Tag color={tierColors[stats.company_tier]} style={{ margin: 0, padding: '4px 12px', fontSize: 12, fontWeight: 600 }}>
                      {(tierLabels[stats.company_tier] ?? stats.company_tier).toUpperCase()}
                    </Tag>
                    <ArrowRightOutlined style={{ color: '#6b7280' }} />
                    <Tag color={tierColors[stats.tier_progress.next_tier]} style={{ margin: 0, padding: '4px 12px', fontSize: 12, fontWeight: 600 }}>
                      {(tierLabels[stats.tier_progress.next_tier] ?? stats.tier_progress.next_tier).toUpperCase()}
                    </Tag>
                  </Space>
                  <Typography.Text strong style={{ color: BRAND.navy }}>Next promotion</Typography.Text>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Typography.Text style={{ fontWeight: 500 }}>Approved Opportunities</Typography.Text>
                    <Typography.Text strong style={{ color: BRAND.navy }}>
                      {stats.tier_progress.opps_current} / {stats.tier_progress.opps_required}
                    </Typography.Text>
                  </div>
                  <Progress
                    percent={stats.tier_progress.opps_progress_pct}
                    strokeColor={{ '0%': BRAND.royal400, '100%': BRAND.royal500 }}
                    strokeWidth={10}
                    showInfo={false}
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Typography.Text style={{ fontWeight: 500 }}>Completed Courses</Typography.Text>
                    <Typography.Text strong style={{ color: BRAND.navy }}>
                      {stats.tier_progress.courses_current} / {stats.tier_progress.courses_required}
                    </Typography.Text>
                  </div>
                  <Progress
                    percent={stats.tier_progress.courses_progress_pct}
                    strokeColor={{ '0%': BRAND.violet400, '100%': BRAND.violet600 }}
                    strokeWidth={10}
                    showInfo={false}
                  />
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <CrownOutlined style={{ fontSize: 56, color: BRAND.royal500, marginBottom: 16 }} />
                <div>
                  <Typography.Text strong style={{ fontSize: 18, color: BRAND.navy }}>You've reached Platinum</Typography.Text>
                </div>
                <Typography.Text type="secondary">Highest tier achieved</Typography.Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------------- Achievements row ---------------------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card
            title={<Space><TrophyOutlined style={{ color: BRAND.violet500 }} /><span>Achievements</span></Space>}
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>{achievements.filter((a) => a.unlocked).length} / {achievements.length} unlocked</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            <Row gutter={[12, 12]}>
              {achievements.map((a) => (
                <Col xs={12} sm={8} md={4} key={a.title}>
                  <AchievementBadge {...a} />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>

      {/* ---------------- Quick actions ------------------------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card
            title="Quick Actions"
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            <Row gutter={[12, 12]}>
              <Col xs={12} sm={6}>
                <Card
                  hoverable
                  bordered={false}
                  onClick={() => navigate('/opportunities/new')}
                  style={{
                    background: `linear-gradient(135deg, ${BRAND.royal50} 0%, ${BRAND.violet100} 100%)`,
                    borderRadius: 10,
                    textAlign: 'center',
                  }}
                  styles={{ body: { padding: 18 } }}
                >
                  <Avatar size={48} style={{ background: `linear-gradient(135deg, ${BRAND.royal500}, ${BRAND.violet500})`, color: '#fff' }} icon={<RocketOutlined />} />
                  <div style={{ marginTop: 10 }}>
                    <Typography.Text strong style={{ fontSize: 13, color: BRAND.navy }}>New Opportunity</Typography.Text>
                  </div>
                </Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card
                  hoverable
                  bordered={false}
                  onClick={() => navigate('/deals')}
                  style={{
                    background: `linear-gradient(135deg, ${BRAND.violet100} 0%, ${BRAND.royal50} 100%)`,
                    borderRadius: 10,
                    textAlign: 'center',
                  }}
                  styles={{ body: { padding: 18 } }}
                >
                  <Avatar size={48} style={{ background: `linear-gradient(135deg, ${BRAND.violet600}, ${BRAND.violet500})`, color: '#fff' }} icon={<CheckCircleOutlined />} />
                  <div style={{ marginTop: 10 }}>
                    <Typography.Text strong style={{ fontSize: 13, color: BRAND.navy }}>Register Deal</Typography.Text>
                  </div>
                </Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card
                  hoverable
                  bordered={false}
                  onClick={() => navigate('/knowledge-base')}
                  style={{
                    background: `linear-gradient(135deg, ${BRAND.royal50} 0%, ${BRAND.violet100} 100%)`,
                    borderRadius: 10,
                    textAlign: 'center',
                  }}
                  styles={{ body: { padding: 18 } }}
                >
                  <Avatar size={48} style={{ background: `linear-gradient(135deg, ${BRAND.royal400}, ${BRAND.royal500})`, color: '#fff' }} icon={<FileTextOutlined />} />
                  <div style={{ marginTop: 10 }}>
                    <Typography.Text strong style={{ fontSize: 13, color: BRAND.navy }}>Knowledge Base</Typography.Text>
                  </div>
                </Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card
                  hoverable
                  bordered={false}
                  onClick={() => navigate('/doc-requests')}
                  style={{
                    background: `linear-gradient(135deg, ${BRAND.violet100} 0%, ${BRAND.royal50} 100%)`,
                    borderRadius: 10,
                    textAlign: 'center',
                  }}
                  styles={{ body: { padding: 18 } }}
                >
                  <Avatar size={48} style={{ background: `linear-gradient(135deg, ${BRAND.violet500}, ${BRAND.violet600})`, color: '#fff' }} icon={<ClockCircleOutlined />} />
                  <div style={{ marginTop: 10 }}>
                    <Typography.Text strong style={{ fontSize: 13, color: BRAND.navy }}>Request Doc</Typography.Text>
                  </div>
                </Card>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </>
  );
};

export default PartnerDashboard;

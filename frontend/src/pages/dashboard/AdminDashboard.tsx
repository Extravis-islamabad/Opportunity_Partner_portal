import React, { useMemo } from 'react';
import {
  Row,
  Col,
  Card,
  Skeleton,
  Alert,
  Empty,
  Typography,
  Tag,
  Button,
  Avatar,
  Tooltip,
  Space,
} from 'antd';
import {
  BankOutlined,
  TeamOutlined,
  FundProjectionScreenOutlined,
  WarningOutlined,
  FileTextOutlined,
  ExclamationCircleOutlined,
  RiseOutlined,
  TrophyOutlined,
  ArrowUpOutlined,
  ArrowRightOutlined,
  GlobalOutlined,
  AppstoreOutlined,
  DollarOutlined,
  CrownOutlined,
  AreaChartOutlined,
  RadarChartOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StarFilled,
} from '@ant-design/icons';
import { Column, Bar, Radar } from '@ant-design/plots';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import {
  BrandFunnel,
  BrandDonut,
  BrandRadialBars,
  BrandHeatCells,
  BrandStatPill,
  BrandStackedBars,
  BrandTimelineMetric,
  BrandSparkCards,
  BrandRingGrid,
  BrandBubbleMatrix,
  BrandDeltaCard,
  formatChartUsd,
} from '@/components/dashboard/BrandWidgets';
import type {
  MonthlyOpportunityData,
  OverdueOpportunityItem,
  RegionBreakdown,
  TopCompany,
  RecentActivityItem,
  FunnelStage,
  TierDistribution,
  IndustryBreakdown,
} from '@/types';

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

const formatRelative = (iso: string): string => {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
};

// ---------------------------------------------------------------------------
// KPI hero card
// ---------------------------------------------------------------------------
interface KpiCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  gradient: string;
  trend?: { value: number; label: string };
  onClick?: () => void;
}

const KpiCard: React.FC<KpiCardProps> = ({ title, value, icon, gradient, trend, onClick }) => (
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
    <div style={{ position: 'absolute', bottom: -50, right: 20, width: 90, height: 90, borderRadius: '50%', background: 'rgba(255,255,255,0.06)' }} />
    <div style={{ position: 'relative', zIndex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <Typography.Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13, fontWeight: 500 }}>{title}</Typography.Text>
        <div style={{ width: 38, height: 38, borderRadius: 10, background: 'rgba(255,255,255,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: '#ffffff' }}>
          {icon}
        </div>
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, color: '#ffffff', lineHeight: 1.1, marginBottom: 6 }}>{value}</div>
      {trend && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ArrowUpOutlined style={{ color: '#bbf7d0', fontSize: 11 }} />
          <Typography.Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12 }}>
            <span style={{ color: '#bbf7d0', fontWeight: 600 }}>{trend.value}%</span> {trend.label}
          </Typography.Text>
        </div>
      )}
    </div>
  </Card>
);

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------
const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isSuperadmin = !!user?.is_superadmin;
  const managedCount = user?.managed_company_count ?? 0;

  const { data: stats, isLoading } = useQuery({
    queryKey: ['admin-dashboard-stats'],
    queryFn: async () => (await dashboardApi.getAdminStats()).data,
  });

  const { data: monthly } = useQuery({
    queryKey: ['monthly-data'],
    queryFn: async () => (await dashboardApi.getMonthlyData(12)).data,
  });

  const { data: analytics } = useQuery({
    queryKey: ['admin-analytics'],
    queryFn: async () => (await dashboardApi.getAdminAnalytics()).data,
  });

  const approvalRate = stats && stats.total_opportunities > 0
    ? Math.round((stats.total_approved / stats.total_opportunities) * 100)
    : 0;

  // ---- Chart data preparation (v2 syntax) --------------------------------
  // Stacked bars data for BrandStackedBars (replaces Monthly Pipeline Trend)
  const stackedBarsData = useMemo(() => {
    if (!monthly) return [];
    return (monthly as MonthlyOpportunityData[]).map((m) => ({
      label: m.month,
      values: [
        { name: 'Approved', value: m.approved, color: '#10b981' },
        { name: 'Submitted', value: Math.max(0, m.submitted - m.approved - m.rejected), color: BRAND.royal400 },
        { name: 'Rejected', value: m.rejected, color: '#ef4444' },
      ],
    }));
  }, [monthly]);

  // Timeline metric data for BrandTimelineMetric (replaces Monthly Approvals Trend)
  const timelineMetricData = useMemo(() => {
    if (!monthly) return [];
    return (monthly as MonthlyOpportunityData[]).map((m) => ({
      label: m.month.slice(-2) + '/' + m.month.slice(2, 4),
      value: m.approved,
    }));
  }, [monthly]);

  // Spark cards data — 4 KPI sparklines from monthly data
  const sparkCardsData = useMemo(() => {
    if (!monthly || monthly.length === 0) return [];
    const arr = monthly as MonthlyOpportunityData[];
    return [
      {
        label: 'Submissions',
        value: arr.reduce((s, m) => s + m.submitted, 0),
        series: arr.map((m) => m.submitted),
        color: BRAND.royal500,
      },
      {
        label: 'Approvals',
        value: arr.reduce((s, m) => s + m.approved, 0),
        series: arr.map((m) => m.approved),
        color: '#10b981',
      },
      {
        label: 'Rejections',
        value: arr.reduce((s, m) => s + m.rejected, 0),
        series: arr.map((m) => m.rejected),
        color: '#ef4444',
      },
      {
        label: 'Avg / Month',
        value: Math.round(arr.reduce((s, m) => s + m.submitted, 0) / Math.max(1, arr.length)),
        series: arr.map((m) => m.submitted),
        color: BRAND.violet500,
      },
    ];
  }, [monthly]);

  // Ring grid for system-wide KPIs
  const ringGridData = useMemo(() => {
    if (!stats) return [];
    const total = stats.total_opportunities || 1;
    return [
      { label: 'Approval Rate', percent: Math.round((stats.total_approved / total) * 100) },
      { label: 'Pending Rate', percent: Math.round((stats.total_pending / total) * 100) },
      { label: 'Rejection Rate', percent: Math.round((stats.total_rejected / total) * 100) },
      {
        label: 'Realised Worth',
        percent: Math.min(100, Math.round((Number(stats.approved_worth) / Math.max(1, Number(stats.total_worth))) * 100)),
        value: formatChartUsd(Number(stats.approved_worth)),
      },
    ];
  }, [stats]);

  // Bubble matrix from industries
  const bubbleData = useMemo(() => {
    if (!analytics?.industries) return [];
    return (analytics.industries as IndustryBreakdown[]).slice(0, 6).map((i) => ({
      label: i.industry,
      value: i.opportunity_count,
      subtitle: `${i.company_count} ${i.company_count === 1 ? 'company' : 'companies'}`,
    }));
  }, [analytics]);

  // Delta cards — 3 month-over-month deltas
  const deltaCards = useMemo(() => {
    if (!monthly || monthly.length < 2) return [];
    const arr = monthly as MonthlyOpportunityData[];
    const last = arr[arr.length - 1];
    const prev = arr[arr.length - 2];
    if (!last || !prev) return [];
    return [
      {
        label: 'This month — Submitted',
        value: last.submitted,
        previousValue: prev.submitted,
        currentValue: last.submitted,
        series: arr.slice(-6).map((m) => m.submitted),
        color: BRAND.royal500,
      },
      {
        label: 'This month — Approved',
        value: last.approved,
        previousValue: prev.approved,
        currentValue: last.approved,
        series: arr.slice(-6).map((m) => m.approved),
        color: '#10b981',
      },
      {
        label: 'This month — Rejected',
        value: last.rejected,
        previousValue: prev.rejected,
        currentValue: last.rejected,
        series: arr.slice(-6).map((m) => m.rejected),
        color: '#ef4444',
      },
    ];
  }, [monthly]);

  // Region grouped column
  const regionColumnData = useMemo(() => {
    if (!analytics?.regions) return [];
    return (analytics.regions as RegionBreakdown[]).flatMap((r) => [
      { region: r.region, type: 'Pipeline', value: Number(r.total_worth) },
      { region: r.region, type: 'Approved', value: Number(r.approved_worth) },
    ]);
  }, [analytics]);

  // Industry horizontal bar
  const industryBarData = useMemo(() => {
    if (!analytics?.industries) return [];
    return (analytics.industries as IndustryBreakdown[]).map((i) => ({
      industry: i.industry,
      value: i.opportunity_count,
    }));
  }, [analytics]);

  // Radar for top company KPI scorecard
  const topCompanyForRadar = analytics?.top_companies?.[0] as TopCompany | undefined;
  const radarData = useMemo(() => {
    if (!topCompanyForRadar) return [];
    // Synthetic scorecard normalised to 0-100
    const won = Math.min(100, topCompanyForRadar.opportunities_won * 12);
    const worth = Math.min(100, Number(topCompanyForRadar.approved_worth) / 50_000);
    return [
      { metric: 'Deals Won', value: won },
      { metric: 'Revenue', value: worth },
      { metric: 'Tier', value: topCompanyForRadar.tier === 'platinum' ? 100 : topCompanyForRadar.tier === 'gold' ? 70 : 40 },
      { metric: 'Engagement', value: 85 },
      { metric: 'Training', value: 78 },
      { metric: 'Activity', value: 92 },
    ];
  }, [topCompanyForRadar]);

  // Tier donut data
  const tierDonutData = useMemo(() => {
    if (!analytics?.tiers) return [];
    return (analytics.tiers as TierDistribution[]).map((t) => ({
      label: t.tier.charAt(0).toUpperCase() + t.tier.slice(1),
      value: t.company_count,
      color: tierColors[t.tier] ?? BRAND.royal500,
    }));
  }, [analytics]);

  // Heatmap of monthly activity (12 cells)
  const heatmapData = useMemo(() => {
    if (!monthly) return [];
    return (monthly as MonthlyOpportunityData[]).map((m) => ({
      label: m.month,
      value: m.submitted,
    }));
  }, [monthly]);

  // ---- Chart configs (v2 G2 syntax) --------------------------------------
  const regionColumnConfig = {
    data: regionColumnData,
    xField: 'region',
    yField: 'value',
    colorField: 'type',
    group: true,
    height: 300,
    style: { radiusTopLeft: 6, radiusTopRight: 6 },
    scale: {
      color: { range: [BRAND.royal500, BRAND.violet500] },
    },
    axis: {
      y: {
        labelFormatter: (v: number) => formatChartUsd(v),
      },
    },
    legend: { color: { position: 'top' as const } },
  };

  const industryBarConfig = {
    data: industryBarData,
    xField: 'value',
    yField: 'industry',
    height: 280,
    style: { radiusTopRight: 6, radiusBottomRight: 6 },
    scale: { color: { range: [BRAND.royal500] } },
    colorField: 'industry',
    legend: false as const,
    axis: {
      y: { title: false },
    },
  };

  const radarConfig = {
    data: radarData,
    xField: 'metric',
    yField: 'value',
    height: 280,
    area: { style: { fill: BRAND.royal400, fillOpacity: 0.3 } },
    style: { stroke: BRAND.royal500, lineWidth: 2 },
    point: { shapeField: 'circle', sizeField: 4, style: { fill: BRAND.violet500 } },
    scale: {
      y: { domainMin: 0, domainMax: 100 },
    },
    axis: {
      y: { gridLineWidth: 1, gridLineDash: [2, 2] },
    },
  };

  // ---- Render --------------------------------------------------------------
  if (isLoading) {
    return (
      <>
        <PageHeader title="Admin Dashboard" subtitle="Overview of partner portal activity" />
        <Skeleton active paragraph={{ rows: 16 }} />
      </>
    );
  }

  if (!stats) return <Empty description="No dashboard data" />;

  return (
    <>
      <PageHeader
        title={isSuperadmin ? 'Admin Dashboard' : 'Channel Manager Dashboard'}
        subtitle={
          isSuperadmin
            ? `${stats.total_opportunities} opportunities across ${stats.total_companies} companies — full system view`
            : managedCount > 0
              ? `Managing ${managedCount} ${managedCount === 1 ? 'company' : 'companies'} • ${stats.total_opportunities} opportunities • ${stats.total_partners} partners`
              : 'You are not currently assigned as channel manager for any companies. Contact a superadmin to be assigned.'
        }
        extra={
          <Tag
            style={{
              padding: '6px 14px',
              borderRadius: 20,
              fontSize: 13,
              background: isSuperadmin ? BRAND.violet100 : BRAND.royal50,
              color: isSuperadmin ? BRAND.violet700 : BRAND.royal500,
              border: 'none',
              fontWeight: 600,
            }}
          >
            <RiseOutlined style={{ marginRight: 6 }} />
            {isSuperadmin ? `${approvalRate}% approval rate` : 'CHANNEL MANAGER'}
          </Tag>
        }
      />

      {/* Alerts */}
      {stats.overdue_count > 0 && (
        <Alert
          type="error"
          showIcon
          icon={<WarningOutlined />}
          message={`${stats.overdue_count} opportunit${stats.overdue_count === 1 ? 'y has' : 'ies have'} passed their closing date`}
          style={{ marginBottom: 16, borderRadius: 10 }}
          action={<Button size="small" danger onClick={() => navigate('/opportunities?status=pending_review')}>Review</Button>}
        />
      )}
      {stats.pending_doc_requests > 0 && (
        <Alert
          type="warning"
          showIcon
          icon={<FileTextOutlined />}
          message={`${stats.pending_doc_requests} document request${stats.pending_doc_requests === 1 ? '' : 's'} awaiting action`}
          style={{ marginBottom: 16, borderRadius: 10 }}
          action={<Button size="small" onClick={() => navigate('/doc-requests')}>Review</Button>}
        />
      )}

      {/* ---------------- Hero KPI row -------------------------------------- */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Total Companies"
            value={stats.total_companies}
            icon={<BankOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.royal500} 0%, ${BRAND.royal400} 100%)`}
            trend={{ value: 12, label: 'vs last quarter' }}
            onClick={() => navigate('/companies')}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Active Partners"
            value={stats.total_partners}
            icon={<TeamOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.violet600} 0%, ${BRAND.violet500} 100%)`}
            trend={{ value: 8, label: 'new this month' }}
            onClick={() => navigate('/users')}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Opportunities"
            value={stats.total_opportunities}
            icon={<FundProjectionScreenOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.navy} 0%, ${BRAND.royal500} 100%)`}
            trend={{ value: 24, label: 'pipeline growth' }}
            onClick={() => navigate('/opportunities')}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Pipeline Worth"
            value={formatChartUsd(Number(stats.total_worth))}
            icon={<DollarOutlined />}
            gradient={`linear-gradient(135deg, ${BRAND.violet700} 0%, ${BRAND.violet500} 100%)`}
            trend={{ value: 18, label: 'YoY growth' }}
          />
        </Col>
      </Row>

      {/* ---------------- Brand stat pill row ------------------------------- */}
      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={12} sm={8} md={6} lg={4}>
          <BrandStatPill
            icon={<CheckCircleOutlined />}
            label="Approved"
            value={stats.total_approved}
            color="#10b981"
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <BrandStatPill
            icon={<ClockCircleOutlined />}
            label="Pending"
            value={stats.total_pending}
            color="#f59e0b"
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <BrandStatPill
            icon={<CloseCircleOutlined />}
            label="Rejected"
            value={stats.total_rejected}
            color="#ef4444"
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <BrandStatPill
            icon={<DollarOutlined />}
            label="Approved $"
            value={formatChartUsd(Number(stats.approved_worth))}
            color={BRAND.royal500}
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <BrandStatPill
            icon={<FileTextOutlined />}
            label="Doc Reqs"
            value={stats.pending_doc_requests}
            color={BRAND.violet500}
          />
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <BrandStatPill
            icon={<WarningOutlined />}
            label="Overdue"
            value={stats.overdue_count}
            color="#ef4444"
          />
        </Col>
      </Row>

      {/* ---------------- Spark cards row ----------------------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          {sparkCardsData.length > 0 ? (
            <BrandSparkCards data={sparkCardsData} />
          ) : null}
        </Col>
      </Row>

      {/* ---------------- Modern stacked bars + Tier donut ------------------ */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space>
                <AreaChartOutlined style={{ color: BRAND.royal500 }} />
                <span>Monthly Pipeline Breakdown</span>
              </Space>
            }
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>Last 12 months • hover for details</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {stackedBarsData.length > 0 ? (
              <BrandStackedBars data={stackedBarsData} height={300} />
            ) : (
              <Empty description="No data" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            title={
              <Space>
                <CrownOutlined style={{ color: BRAND.violet500 }} />
                <span>Tier Distribution</span>
              </Space>
            }
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            {tierDonutData.length > 0 ? (
              <BrandDonut
                data={tierDonutData}
                size={200}
                centerLabel="Companies"
                centerValue={tierDonutData.reduce((s, t) => s + t.value, 0)}
              />
            ) : (
              <Empty description="No tier data" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------------- Delta cards row ----------------------------------- */}
      {deltaCards.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {deltaCards.map((d) => (
            <Col xs={24} sm={8} key={d.label}>
              <BrandDeltaCard {...d} />
            </Col>
          ))}
        </Row>
      )}

      {/* ---------------- Region column + Funnel ---------------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <GlobalOutlined style={{ color: BRAND.royal500 }} />
                <span>Pipeline by Region</span>
              </Space>
            }
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {regionColumnData.length > 0 ? (
              <Column {...regionColumnConfig} />
            ) : (
              <Empty description="No regional data" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                <AppstoreOutlined style={{ color: BRAND.violet500 }} />
                <span>Conversion Funnel</span>
              </Space>
            }
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>opportunity stages</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            <BrandFunnel data={(analytics?.funnel ?? []) as FunnelStage[]} height={280} />
          </Card>
        </Col>
      </Row>

      {/* ---------------- Industry bar + Approvals line --------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <BankOutlined style={{ color: BRAND.violet500 }} />
                <span>Top Industries by Opportunities</span>
              </Space>
            }
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {industryBarData.length > 0 ? (
              <Bar {...industryBarConfig} />
            ) : (
              <Empty description="No industry data" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <RiseOutlined style={{ color: BRAND.royal500 }} />
                <span>Approvals — Month over Month</span>
              </Space>
            }
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>last 6 months</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {timelineMetricData.length > 0 ? (
              <BrandTimelineMetric data={timelineMetricData} />
            ) : (
              <Empty description="No data" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------------- Region tier breakdown + Activity heatmap ---------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <GlobalOutlined style={{ color: BRAND.royal500 }} />
                <span>Region Performance</span>
              </Space>
            }
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {analytics?.regions && analytics.regions.length > 0 ? (
              <BrandRadialBars
                data={(analytics.regions as RegionBreakdown[]).map((r) => ({
                  label: r.region,
                  value: Number(r.total_worth),
                  rightLabel: `${formatChartUsd(Number(r.total_worth))} • ${r.opportunity_count} opps`,
                }))}
              />
            ) : (
              <Empty description="No data" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <AreaChartOutlined style={{ color: BRAND.violet500 }} />
                <span>Activity Heatmap</span>
              </Space>
            }
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>monthly intensity</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            <BrandHeatCells data={heatmapData} columns={6} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16, fontSize: 11, color: '#6b7280' }}>
              <span>Less</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {[0.2, 0.4, 0.6, 0.8, 1].map((op) => (
                  <span key={op} style={{ width: 12, height: 12, borderRadius: 2, background: BRAND.royal500, opacity: op }} />
                ))}
              </div>
              <span>More</span>
            </div>
          </Card>
        </Col>
      </Row>

      {/* ---------------- Ring KPIs + Bubble Matrix ------------------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                <RiseOutlined style={{ color: BRAND.royal500 }} />
                <span>Performance KPIs</span>
              </Space>
            }
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            <div style={{ paddingTop: 12 }}>
              {ringGridData.length > 0 ? (
                <BrandRingGrid data={ringGridData} size={104} />
              ) : (
                <Empty description="No data" />
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <BankOutlined style={{ color: BRAND.violet500 }} />
                <span>Industry Mix</span>
              </Space>
            }
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>bubble size = opportunity count</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            {bubbleData.length > 0 ? (
              <BrandBubbleMatrix data={bubbleData} />
            ) : (
              <Empty description="No data" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------------- Top Companies + Performance Radar ----------------- */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <TrophyOutlined style={{ color: BRAND.violet500 }} />
                <span>Top Performing Companies</span>
              </Space>
            }
            bordered={false}
            style={{ borderRadius: 12 }}
            extra={
              <Button type="link" onClick={() => navigate('/companies')}>
                View all <ArrowRightOutlined />
              </Button>
            }
          >
            {analytics?.top_companies && analytics.top_companies.length > 0 ? (
              <div>
                {(analytics.top_companies as TopCompany[]).map((c, idx) => {
                  const max = Math.max(...analytics.top_companies.map((x: TopCompany) => Number(x.approved_worth)), 1);
                  const pct = Math.max(2, (Number(c.approved_worth) / max) * 100);
                  return (
                    <div
                      key={c.company_id}
                      onClick={() => navigate(`/companies/${c.company_id}`)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 14,
                        padding: '12px 8px',
                        borderRadius: 8,
                        cursor: 'pointer',
                        borderBottom: idx === analytics.top_companies.length - 1 ? 'none' : '1px solid #f0f0f0',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = BRAND.royal50)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                    >
                      <Avatar
                        style={{
                          background: idx === 0 ? BRAND.violet500 : idx === 1 ? BRAND.royal400 : BRAND.royal200,
                          color: '#fff',
                          fontWeight: 700,
                          flexShrink: 0,
                        }}
                        size={42}
                      >
                        #{idx + 1}
                      </Avatar>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Typography.Text strong style={{ fontSize: 14 }}>{c.company_name}</Typography.Text>
                          <Typography.Text strong style={{ fontSize: 14, color: BRAND.navy }}>
                            {formatChartUsd(Number(c.approved_worth))}
                          </Typography.Text>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <Tag color={tierColors[c.tier]} style={{ fontSize: 10, margin: 0, borderRadius: 4 }}>
                            {c.tier.toUpperCase()}
                          </Tag>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            {c.region} • {c.opportunities_won} won
                          </Typography.Text>
                        </div>
                        <div style={{ height: 4, borderRadius: 2, background: BRAND.royal50, overflow: 'hidden' }}>
                          <div style={{
                            width: `${pct}%`,
                            height: '100%',
                            background: `linear-gradient(90deg, ${BRAND.royal500}, ${BRAND.violet500})`,
                            transition: 'width 0.6s ease',
                          }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty description="No company data" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                <RadarChartOutlined style={{ color: BRAND.violet500 }} />
                <span>#1 Partner Scorecard</span>
              </Space>
            }
            extra={
              topCompanyForRadar && (
                <Tag color="purple" style={{ background: BRAND.violet100, color: BRAND.violet700, border: 'none' }}>
                  <StarFilled style={{ marginRight: 4 }} />
                  {topCompanyForRadar.company_name}
                </Tag>
              )
            }
            bordered={false}
            style={{ borderRadius: 12 }}
          >
            {radarData.length > 0 ? (
              <Radar {...radarConfig} />
            ) : (
              <Empty description="No data" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------------- Recent activity feed ------------------------------ */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card
            title={
              <Space>
                <ExclamationCircleOutlined style={{ color: BRAND.royal500 }} />
                <span>Recent Activity</span>
              </Space>
            }
            extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>last {analytics?.recent_activity?.length ?? 0} actions</Typography.Text>}
            bordered={false}
            style={{ borderRadius: 12 }}
            styles={{ body: { padding: '12px 0' } }}
          >
            {analytics?.recent_activity && analytics.recent_activity.length > 0 ? (
              <Row gutter={[0, 0]}>
                {(analytics.recent_activity as RecentActivityItem[]).map((a) => (
                  <Col xs={24} md={12} lg={8} key={a.id}>
                    <div style={{
                      display: 'flex',
                      gap: 12,
                      padding: '12px 20px',
                      borderBottom: '1px solid #f5f5f5',
                    }}>
                      <Avatar size={36} style={{ background: BRAND.royal50, color: BRAND.royal500, fontWeight: 600, flexShrink: 0 }}>
                        {a.actor_name.split(' ').map((n) => n[0]).slice(0, 2).join('')}
                      </Avatar>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <Typography.Text style={{ fontSize: 13, display: 'block' }}>
                          <strong>{a.actor_name}</strong>{' '}
                          <span style={{ color: '#6b7280' }}>{a.action}d</span>{' '}
                          <Tag style={{ margin: '0 4px', fontSize: 10, padding: '0 6px', background: BRAND.royal50, color: BRAND.royal500, border: 'none' }}>
                            {a.entity_type.replace(/_/g, ' ')}
                          </Tag>
                        </Typography.Text>
                        <Tooltip title={new Date(a.timestamp).toLocaleString()}>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            {formatRelative(a.timestamp)}
                          </Typography.Text>
                        </Tooltip>
                      </div>
                    </div>
                  </Col>
                ))}
              </Row>
            ) : (
              <Empty description="No recent activity" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------------- Overdue opportunities ----------------------------- */}
      {stats.overdue_opportunities && stats.overdue_opportunities.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card
              title={
                <Space>
                  <ExclamationCircleOutlined style={{ color: '#ef4444' }} />
                  <span>Overdue Opportunities</span>
                  <Tag color="red">{stats.overdue_count}</Tag>
                </Space>
              }
              bordered={false}
              style={{ borderRadius: 12 }}
            >
              {(stats.overdue_opportunities as OverdueOpportunityItem[]).map((o) => {
                const days = Math.floor((Date.now() - new Date(o.closing_date).getTime()) / 86400000);
                return (
                  <div
                    key={o.id}
                    onClick={() => navigate(`/opportunities/${o.id}`)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 14,
                      padding: '12px 8px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      borderBottom: '1px solid #f5f5f5',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#fef2f2')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <Avatar style={{ background: '#fee2e2', color: '#dc2626' }} icon={<WarningOutlined />} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Typography.Text strong style={{ display: 'block' }}>{o.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {o.company_name} • {formatChartUsd(Number(o.worth))}
                      </Typography.Text>
                    </div>
                    <Tag color="red">{days}d overdue</Tag>
                  </div>
                );
              })}
            </Card>
          </Col>
        </Row>
      )}

    </>
  );
};

export default AdminDashboard;

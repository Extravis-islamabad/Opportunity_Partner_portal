import React from 'react';
import { Card, Col, Row, Progress, Statistic, Tag, Space, Alert, Tooltip, Empty, Typography } from 'antd';
import { TrophyOutlined, StarFilled, DollarOutlined, RiseOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Line } from '@ant-design/charts';
import { scorecardApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import TableSkeleton from '@/components/common/TableSkeleton';
import EmptyState from '@/components/common/EmptyState';
import { useAppTheme } from '@/contexts/ThemeContext';

const tierColors: Record<string, string> = {
  silver: '#9e9e9e',
  gold: '#faad14',
  platinum: '#1a237e',
};

const fmtUsd = (value: string | number) =>
  `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

const ScorecardPage: React.FC = () => {
  const { isDark } = useAppTheme();

  const { data, isLoading, error } = useQuery({
    queryKey: ['scorecard', 'me'],
    queryFn: async () => {
      const res = await scorecardApi.me();
      return res.data;
    },
  });

  if (isLoading) return <TableSkeleton />;
  if (error)
    return (
      <Alert type="error" message="Failed to load scorecard" showIcon />
    );
  if (!data)
    return <EmptyState title="No scorecard data" description="Register deals to start tracking your progress." />;

  const tierColor = tierColors[data.tier] ?? '#1a237e';

  const chartConfig = {
    data: data.monthly_commission.map((p) => ({
      month: p.month,
      amount: Number(p.amount),
    })),
    xField: 'month',
    yField: 'amount',
    smooth: true,
    height: 200,
    theme: isDark ? 'dark' : 'default',
    color: tierColor,
    point: { size: 4, shape: 'circle' },
    yAxis: { label: { formatter: (v: string) => `$${Number(v).toLocaleString()}` } },
  };

  return (
    <>
      <PageHeader
        title="Partner Scorecard"
        subtitle={`${data.company_name} · ${data.tier.toUpperCase()} tier`}
      />

      <Row gutter={[16, 16]}>
        {/* Tier progress hero card */}
        <Col xs={24} md={10}>
          <Card>
            <Space align="start" size={24}>
              <Progress
                type="circle"
                percent={Math.round(data.tier_progress_pct)}
                strokeColor={tierColor}
                size={140}
                format={(pct) => (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: tierColor }}>{pct}%</div>
                    <div style={{ fontSize: 11, opacity: 0.7 }}>to {data.next_tier?.toUpperCase() ?? 'MAX'}</div>
                  </div>
                )}
              />
              <div>
                <Typography.Title level={4} style={{ marginBottom: 4 }}>
                  <TrophyOutlined style={{ color: tierColor }} /> {data.tier.toUpperCase()}
                </Typography.Title>
                <Typography.Text type="secondary">Current tier</Typography.Text>
                {data.rank && (
                  <div style={{ marginTop: 12 }}>
                    <Tag color="blue" icon={<StarFilled />}>
                      Rank #{data.rank} YTD
                    </Tag>
                  </div>
                )}
              </div>
            </Space>
          </Card>
        </Col>

        {/* Key stats */}
        <Col xs={24} md={14}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={12}>
              <Card>
                <Statistic
                  title="Approved Deals"
                  value={data.total_approved_deals}
                  prefix={<RiseOutlined />}
                />
              </Card>
            </Col>
            <Col xs={12} md={12}>
              <Card>
                <Statistic
                  title="Total Closed Value"
                  value={fmtUsd(data.total_closed_value)}
                />
              </Card>
            </Col>
            <Col xs={12} md={12}>
              <Card>
                <Statistic
                  title="YTD Commission"
                  value={fmtUsd(data.ytd_commission)}
                  prefix={<DollarOutlined style={{ color: '#52c41a' }} />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col xs={12} md={12}>
              <Card>
                <Statistic
                  title="Lifetime Commission"
                  value={fmtUsd(data.lifetime_commission)}
                />
              </Card>
            </Col>
          </Row>
        </Col>

        {/* Monthly commission sparkline */}
        <Col xs={24}>
          <Card title="Monthly Commission">
            {data.monthly_commission.length > 0 ? (
              <Line {...chartConfig} />
            ) : (
              <Empty description="No commission data yet" />
            )}
          </Card>
        </Col>

        {/* Badges */}
        <Col xs={24}>
          <Card title="Achievements">
            {data.badges.length > 0 ? (
              <Space wrap size={[12, 12]}>
                {data.badges.map((b) => (
                  <Tooltip key={b.key} title={b.description}>
                    <Tag
                      color="gold"
                      icon={<TrophyOutlined />}
                      style={{ fontSize: 14, padding: '6px 12px' }}
                    >
                      {b.label}
                    </Tag>
                  </Tooltip>
                ))}
              </Space>
            ) : (
              <Typography.Text type="secondary">
                Register deals and reach milestones to earn badges.
              </Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </>
  );
};

export default ScorecardPage;

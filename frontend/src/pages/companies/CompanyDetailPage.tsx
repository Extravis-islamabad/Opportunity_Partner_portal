import React from 'react';
import { Descriptions, Card, Table, Tag, Skeleton, Alert, Empty, Button, Space, Row, Col, Statistic, Progress, Tooltip, Typography } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { companiesApi, dashboardApi, scorecardApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { PartnerAccountBrief, ScorecardRead } from '@/types';
import { companyTypeMeta, isChannelCompanyType } from '@/utils/companyType';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined, TrophyOutlined, StarFilled, DollarOutlined, RiseOutlined } from '@ant-design/icons';

const tierColors: Record<string, string> = { silver: 'default', gold: 'gold', platinum: 'blue' };

const scorecardTierColors: Record<string, string> = { silver: '#9e9e9e', gold: '#faad14', platinum: '#3750ed' };

const fmtUsd = (value: string | number) =>
  `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

const CompanyDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const companyId = Number(id);

  const { data: company, isLoading, error } = useQuery({
    queryKey: ['company', companyId],
    queryFn: async () => { const res = await companiesApi.get(companyId); return res.data; },
  });

  const { data: performance } = useQuery({
    queryKey: ['company-performance', companyId],
    queryFn: async () => { const res = await dashboardApi.getCompanyPerformance(companyId); return res.data; },
    enabled: !!company,
  });

  // Customer companies have no partner scorecard — the endpoint refuses them,
  // so don't ask for one.
  const isChannel = isChannelCompanyType(company?.company_type);

  const { data: scorecard, isError: scorecardError } = useQuery<ScorecardRead>({
    queryKey: ['company-scorecard', companyId],
    queryFn: async () => { const res = await scorecardApi.company(companyId); return res.data; },
    enabled: Number.isFinite(companyId) && companyId > 0 && isChannel,
    retry: false,
  });

  if (error) return <Alert type="error" message="Failed to load company" showIcon />;
  if (isLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
  if (!company) return <Empty description="Company not found" />;

  const partnerColumns: ColumnsType<PartnerAccountBrief> = [
    { title: 'Name', dataIndex: 'full_name', key: 'name' },
    { title: 'Email', dataIndex: 'email', key: 'email' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'pending_activation' ? 'orange' : 'red'}>{s.toUpperCase()}</Tag> },
    { title: 'Job Title', dataIndex: 'job_title', key: 'job' },
  ];

  return (
    <>
      <PageHeader
        title={company.name}
        breadcrumbs={[{ label: 'Companies', path: '/companies' }, { label: company.name }]}
        extra={
          <Space>
            <Button icon={<EditOutlined />} onClick={() => navigate(`/companies/${companyId}/edit`)}>Edit</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/users?action=create&company_id=${companyId}`)}>Add Partner</Button>
          </Space>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="Company Information">
            <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
              <Descriptions.Item label="Country">{company.country}</Descriptions.Item>
              <Descriptions.Item label="Region">{company.region}</Descriptions.Item>
              <Descriptions.Item label="City">{company.city}</Descriptions.Item>
              <Descriptions.Item label="Industry">{company.industry}</Descriptions.Item>
              <Descriptions.Item label="Contact Email">{company.contact_email}</Descriptions.Item>
              <Descriptions.Item label="Channel Manager">{company.channel_manager_name}</Descriptions.Item>
              <Descriptions.Item label="Status"><Tag color={company.status === 'active' ? 'green' : 'red'}>{company.status.toUpperCase()}</Tag></Descriptions.Item>
              <Descriptions.Item label="Type">
                {(() => {
                  const meta = companyTypeMeta(company.company_type);
                  return meta ? (
                    <Tooltip title={meta.description}>
                      <Tag color={meta.color}>{meta.label.toUpperCase()}</Tag>
                    </Tooltip>
                  ) : '—';
                })()}
              </Descriptions.Item>
              {/* Tier is a partner-programme concept; a customer has none. */}
              {company.tier && (
                <Descriptions.Item label="Tier"><Tag color={tierColors[company.tier] ?? 'default'}>{company.tier.toUpperCase()}</Tag></Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          {performance && (
            <Card title="Performance">
              <Statistic title="Opportunities Submitted" value={performance.opportunities_submitted} />
              <Statistic title="Won" value={performance.opportunities_won} valueStyle={{ color: '#3f8600' }} style={{ marginTop: 8 }} />
              <Statistic title="Lost" value={performance.opportunities_lost} valueStyle={{ color: '#cf1322' }} style={{ marginTop: 8 }} />
              <Statistic title="LMS Completion" value={performance.lms_completion_rate} suffix="%" style={{ marginTop: 8 }} />
            </Card>
          )}
        </Col>
      </Row>

      {isChannel && (
      <Card title="Partner Scorecard" style={{ marginTop: 16 }}>
        {scorecardError || !scorecard ? (
          <Empty description="No scorecard data yet" />
        ) : (
          (() => {
            const tierColor = scorecardTierColors[scorecard.tier] ?? '#3750ed';
            return (
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}>
                  <Space align="start" size={20}>
                    <Progress
                      type="circle"
                      percent={Math.round(scorecard.tier_progress_pct)}
                      strokeColor={tierColor}
                      size={120}
                      format={(pct) => (
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 20, fontWeight: 700, color: tierColor }}>{pct}%</div>
                          <div style={{ fontSize: 11, opacity: 0.7 }}>to {scorecard.next_tier?.toUpperCase() ?? 'MAX'}</div>
                        </div>
                      )}
                    />
                    <div>
                      <Typography.Title level={4} style={{ marginBottom: 4 }}>
                        <TrophyOutlined style={{ color: tierColor }} /> {scorecard.tier.toUpperCase()}
                      </Typography.Title>
                      <Typography.Text type="secondary">Current tier</Typography.Text>
                      {scorecard.rank != null && (
                        <div style={{ marginTop: 12 }}>
                          <Tag color="blue" icon={<StarFilled />}>Rank #{scorecard.rank} YTD</Tag>
                        </div>
                      )}
                    </div>
                  </Space>
                </Col>
                <Col xs={24} md={16}>
                  <Row gutter={[12, 12]}>
                    <Col xs={12} md={6}>
                      <Statistic title="Approved Deals" value={scorecard.total_approved_deals} prefix={<RiseOutlined />} />
                    </Col>
                    <Col xs={12} md={6}>
                      <Statistic title="Closed Value" value={fmtUsd(scorecard.total_closed_value)} />
                    </Col>
                    <Col xs={12} md={6}>
                      <Statistic title="YTD Commission" value={fmtUsd(scorecard.ytd_commission)} prefix={<DollarOutlined style={{ color: '#52c41a' }} />} valueStyle={{ color: '#52c41a' }} />
                    </Col>
                    <Col xs={12} md={6}>
                      <Statistic title="Lifetime Commission" value={fmtUsd(scorecard.lifetime_commission)} />
                    </Col>
                  </Row>
                </Col>
                <Col xs={24}>
                  <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>Achievements</Typography.Text>
                  {scorecard.badges.length > 0 ? (
                    <Space wrap size={[8, 8]}>
                      {scorecard.badges.map((b) => (
                        <Tooltip key={b.key} title={b.description}>
                          <Tag color="gold" icon={<TrophyOutlined />} style={{ padding: '4px 10px' }}>{b.label}</Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  ) : (
                    <Typography.Text type="secondary">No badges earned yet.</Typography.Text>
                  )}
                </Col>
              </Row>
            );
          })()
        )}
      </Card>
      )}

      <Card title={`Partner Accounts (${company.partners.length})`} style={{ marginTop: 16 }}>
        {company.partners.length > 0 ? (
          <Table columns={partnerColumns} dataSource={company.partners} rowKey="id" pagination={false} />
        ) : (
          <Empty description="No partner accounts" />
        )}
      </Card>
    </>
  );
};

export default CompanyDetailPage;

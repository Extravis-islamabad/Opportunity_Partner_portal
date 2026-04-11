import React from 'react';
import {
  Card,
  Row,
  Col,
  Tag,
  Empty,
  Skeleton,
  Alert,
  Typography,
  Space,
  Button,
  Pagination,
} from 'antd';
import {
  WarningOutlined,
  RobotOutlined,
  ExclamationCircleOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { duplicatesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { DuplicateReviewItem, DuplicateOppSummary } from '@/api/endpoints';

const BRAND = {
  royal500: '#3750ed',
  royal100: '#b4b6f7',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  violet500: '#a064f3',
  violet600: '#7a2280',
  violet100: '#f0e6ff',
};

const formatUsd = (v: string | null): string => {
  if (!v) return '—';
  const n = Number(v);
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};

const statusColors: Record<string, string> = {
  draft: '#9ca3af',
  pending_review: '#f59e0b',
  under_review: BRAND.royal500,
  approved: '#10b981',
  rejected: '#ef4444',
  multi_partner_flagged: BRAND.violet500,
};

const OppCard: React.FC<{ opp: DuplicateOppSummary; label: string; color: string }> = ({ opp, label, color }) => {
  const navigate = useNavigate();
  return (
    <Card
      bordered={false}
      hoverable
      onClick={() => navigate(`/opportunities/${opp.id}`)}
      style={{
        borderRadius: 12,
        border: `2px solid ${color}`,
        background: '#ffffff',
      }}
      styles={{ body: { padding: 18 } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <Tag color={color} style={{ fontWeight: 600, border: 'none' }}>{label}</Tag>
        <Tag color={statusColors[opp.status] ?? 'default'} style={{ fontSize: 10 }}>
          {opp.status.replace(/_/g, ' ').toUpperCase()}
        </Tag>
      </div>
      <Typography.Title level={5} style={{ margin: '4px 0', color: BRAND.navy }}>
        {opp.name}
      </Typography.Title>
      <div style={{ marginBottom: 6 }}>
        <Typography.Text strong>{opp.customer_name}</Typography.Text>
      </div>
      <Space size={[8, 4]} wrap>
        <Tag style={{ background: BRAND.royal50, color: BRAND.royal500, border: 'none' }}>
          {opp.company_name ?? 'Unknown company'}
        </Tag>
        <Tag>{opp.country}{opp.city ? ` • ${opp.city}` : ''}</Tag>
        <Tag color="blue">{formatUsd(opp.worth)}</Tag>
        {opp.similarity !== null && opp.similarity !== undefined && (
          <Tag color="purple">similarity {Math.round(opp.similarity * 100)}%</Tag>
        )}
      </Space>
      <div style={{ marginTop: 10, fontSize: 11, color: '#6b7280' }}>
        Created {opp.created_at ? new Date(opp.created_at).toLocaleDateString() : '—'}
      </div>
    </Card>
  );
};

const DuplicateReviewPage: React.FC = () => {
  const [page, setPage] = React.useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ['duplicate-review', page],
    queryFn: async () => (await duplicatesApi.listReviewQueue({ page, page_size: 10 })).data,
  });

  if (error) return <Alert type="error" message="Failed to load review queue" showIcon />;

  return (
    <>
      <PageHeader
        title="Duplicate Review Queue"
        subtitle={data ? `${data.total} possible duplicates flagged for review` : 'Loading…'}
        extra={
          <Tag
            style={{
              padding: '6px 14px',
              borderRadius: 20,
              background: BRAND.violet100,
              color: BRAND.violet600,
              border: 'none',
              fontWeight: 600,
            }}
          >
            <WarningOutlined style={{ marginRight: 6 }} />
            Channel Manager + Admin
          </Tag>
        }
      />

      <Alert
        type="info"
        showIcon
        icon={<ExclamationCircleOutlined />}
        message="About this queue"
        description={
          <span>
            Opportunities appear here when our duplicate-detection system or the AI duplicate scorer flags them as a possible match for an existing opportunity. Click any pair to open both for side-by-side review and decide which one to approve.
          </span>
        }
        style={{ marginBottom: 16, borderRadius: 10 }}
      />

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 12 }} />
      ) : data && data.items.length > 0 ? (
        <>
          <Space direction="vertical" size={20} style={{ width: '100%' }}>
            {data.items.map((item: DuplicateReviewItem) => (
              <Card
                key={item.opportunity.id}
                bordered={false}
                style={{
                  borderRadius: 14,
                  background: `linear-gradient(135deg, ${BRAND.royal50} 0%, ${BRAND.violet100} 100%)`,
                  padding: 4,
                }}
                styles={{ body: { padding: 16 } }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Typography.Text style={{ fontSize: 12, color: BRAND.navy, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {item.flagged_by === 'ai' ? (
                      <><RobotOutlined style={{ marginRight: 6 }} /> Flagged by AI</>
                    ) : (
                      <><WarningOutlined style={{ marginRight: 6 }} /> Flagged by system</>
                    )}
                  </Typography.Text>
                  <Tag color="purple" style={{ fontSize: 11 }}>NEEDS REVIEW</Tag>
                </div>

                <Row gutter={[16, 16]} align="middle">
                  <Col xs={24} md={11}>
                    <OppCard opp={item.opportunity} label="NEW" color={BRAND.royal500} />
                  </Col>
                  <Col xs={24} md={2} style={{ textAlign: 'center' }}>
                    <ArrowRightOutlined style={{ fontSize: 24, color: BRAND.violet500 }} />
                  </Col>
                  <Col xs={24} md={11}>
                    {item.matched_against ? (
                      <OppCard opp={item.matched_against} label="POSSIBLE MATCH" color={BRAND.violet500} />
                    ) : (
                      <Card
                        bordered={false}
                        style={{ borderRadius: 12, border: `2px dashed ${BRAND.violet500}`, background: '#ffffff' }}
                        styles={{ body: { padding: 30, textAlign: 'center' } }}
                      >
                        <Typography.Text type="secondary">
                          AI flagged this opportunity but the matched record is no longer available.
                        </Typography.Text>
                      </Card>
                    )}
                  </Col>
                </Row>
              </Card>
            ))}
          </Space>

          {data.total > 10 && (
            <div style={{ textAlign: 'center', marginTop: 24 }}>
              <Pagination current={page} total={data.total} pageSize={10} onChange={setPage} />
            </div>
          )}
        </>
      ) : (
        <Empty
          description="No duplicates flagged — your pipeline is clean"
          style={{ marginTop: 60 }}
        />
      )}
    </>
  );
};

export default DuplicateReviewPage;

import React, { useState } from 'react';
import { Card, Table, Tag, Select, Space, Alert, Typography } from 'antd';
import { TrophyOutlined, CrownOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { scorecardApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import TableSkeleton from '@/components/common/TableSkeleton';
import EmptyState from '@/components/common/EmptyState';
import type { LeaderboardEntry } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const tierColors: Record<string, string> = { silver: 'default', gold: 'gold', platinum: 'blue' };

const fmtUsd = (value: string | number) =>
  `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const rankIcon = (rank: number): React.ReactNode => {
  if (rank === 1) return <CrownOutlined style={{ color: '#faad14', fontSize: 20 }} />;
  if (rank === 2) return <TrophyOutlined style={{ color: '#bfbfbf', fontSize: 18 }} />;
  if (rank === 3) return <TrophyOutlined style={{ color: '#d4a373', fontSize: 18 }} />;
  return <span style={{ display: 'inline-block', minWidth: 20, textAlign: 'center' }}>{rank}</span>;
};

const LeaderboardPage: React.FC = () => {
  const [period, setPeriod] = useState<'ytd' | '30d' | 'all'>('ytd');

  const { data, isLoading, error } = useQuery({
    queryKey: ['leaderboard', period],
    queryFn: async () => {
      const res = await scorecardApi.leaderboard({ period });
      return res.data;
    },
  });

  const columns: ColumnsType<LeaderboardEntry> = [
    {
      title: '#',
      dataIndex: 'rank',
      key: 'rank',
      width: 60,
      render: (r: number) => rankIcon(r),
    },
    { title: 'Company', dataIndex: 'company_name', key: 'company_name' },
    {
      title: 'Tier',
      dataIndex: 'tier',
      key: 'tier',
      render: (t: string) => <Tag color={tierColors[t] ?? 'default'}>{t.toUpperCase()}</Tag>,
    },
    { title: 'Deals', dataIndex: 'deal_count', key: 'deal_count' },
    {
      title: 'Commission Total',
      dataIndex: 'total_amount',
      key: 'total_amount',
      render: (v: string) => <strong>{fmtUsd(v)}</strong>,
    },
  ];

  if (error) return <Alert type="error" message="Failed to load leaderboard" showIcon />;

  return (
    <>
      <PageHeader
        title="Partner Leaderboard"
        subtitle="Top partners by commission earned"
        extra={
          <Select
            value={period}
            style={{ width: 160 }}
            onChange={(v) => setPeriod(v)}
            options={[
              { value: 'ytd', label: 'Year to Date' },
              { value: '30d', label: 'This Month' },
              { value: 'all', label: 'All Time' },
            ]}
          />
        }
      />
      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : data && data.entries.length > 0 ? (
          <Table
            columns={columns}
            dataSource={data.entries}
            rowKey="company_id"
            pagination={false}
          />
        ) : (
          <EmptyState
            title="No leaderboard data yet"
            description="The leaderboard populates as partners close deals and earn commissions."
          />
        )}
      </Card>
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
        <Space size={4}>
          Rankings update in real time based on approved and paid commissions.
        </Space>
      </Typography.Paragraph>
    </>
  );
};

export default LeaderboardPage;

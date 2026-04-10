import React from 'react';
import { Card, List, Tag, Avatar, Typography, Space } from 'antd';
import { TrophyOutlined, CrownOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { scorecardApi } from '@/api/endpoints';

const tierColors: Record<string, string> = { silver: 'default', gold: 'gold', platinum: 'blue' };

const fmtUsd = (value: string | number) =>
  `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const rankAvatar = (rank: number): React.ReactNode => {
  if (rank === 1) return <Avatar style={{ backgroundColor: '#faad14' }} icon={<CrownOutlined />} />;
  if (rank === 2) return <Avatar style={{ backgroundColor: '#bfbfbf' }} icon={<TrophyOutlined />} />;
  if (rank === 3) return <Avatar style={{ backgroundColor: '#d4a373' }} icon={<TrophyOutlined />} />;
  return <Avatar>{rank}</Avatar>;
};

const LeaderboardWidget: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard-widget'],
    queryFn: async () => {
      const res = await scorecardApi.leaderboard({ period: 'ytd', limit: 5 });
      return res.data;
    },
  });

  return (
    <Card
      title={
        <Space>
          <TrophyOutlined style={{ color: '#faad14' }} />
          <span>Top Partners (YTD)</span>
        </Space>
      }
      extra={<Link to="/leaderboard">View all</Link>}
      loading={isLoading}
    >
      {data && data.entries.length > 0 ? (
        <List
          dataSource={data.entries}
          renderItem={(entry) => (
            <List.Item>
              <List.Item.Meta
                avatar={rankAvatar(entry.rank)}
                title={entry.company_name}
                description={
                  <Space size={4}>
                    <Tag color={tierColors[entry.tier] ?? 'default'}>{entry.tier.toUpperCase()}</Tag>
                    <Typography.Text type="secondary">{entry.deal_count} deals</Typography.Text>
                  </Space>
                }
              />
              <Typography.Text strong>{fmtUsd(entry.total_amount)}</Typography.Text>
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">No data yet</Typography.Text>
      )}
    </Card>
  );
};

export default LeaderboardWidget;

import React from 'react';
import { Card, Timeline, Tag, Typography, Empty, Skeleton, Space } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, HistoryOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '@/api/endpoints';
import type { TierHistoryEntry } from '@/types';
import dayjs from 'dayjs';

/**
 * Why a company's tier moved, newest first.
 *
 * Shared by the partner's own scorecard and the admin company page on purpose:
 * a demotion nobody can explain later is a support ticket, and both sides
 * should be reading the same reason rather than one being told a summary.
 */
const tierColors: Record<string, string> = {
  silver: 'default',
  gold: 'gold',
  platinum: 'purple',
};

const TierHistoryCard: React.FC<{ companyId: number }> = ({ companyId }) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['tier-history', companyId],
    queryFn: async () => (await companiesApi.tierHistory(companyId)).data,
  });

  // A tier that has never moved is the common case for a new partner, and an
  // error here should not take the surrounding page down with it.
  if (error) return null;

  return (
    <Card
      title={<Space><HistoryOutlined />Tier History</Space>}
      style={{ marginTop: 16 }}
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : (data ?? []).length === 0 ? (
        <Empty description="This company's tier has not changed yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Timeline
          items={(data as TierHistoryEntry[]).map((entry) => ({
            color: entry.direction === 'down' ? 'red' : 'green',
            dot: entry.direction === 'down' ? <ArrowDownOutlined /> : <ArrowUpOutlined />,
            children: (
              <div>
                <Space size={6} wrap>
                  {entry.previous_tier && (
                    <>
                      <Tag color={tierColors[entry.previous_tier] ?? 'default'}>
                        {entry.previous_tier.toUpperCase()}
                      </Tag>
                      <span>→</span>
                    </>
                  )}
                  <Tag color={tierColors[entry.new_tier] ?? 'default'}>
                    {entry.new_tier.toUpperCase()}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {dayjs(entry.changed_at).format('MMM D, YYYY')}
                  </Typography.Text>
                </Space>
                {entry.reason && (
                  <div>
                    <Typography.Text style={{ fontSize: 13 }}>{entry.reason}</Typography.Text>
                  </div>
                )}
                {entry.changed_by_name && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    by {entry.changed_by_name}
                  </Typography.Text>
                )}
              </div>
            ),
          }))}
        />
      )}
    </Card>
  );
};

export default TierHistoryCard;

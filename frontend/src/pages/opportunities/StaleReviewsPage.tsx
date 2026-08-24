import React, { useState } from 'react';
import { Card, Table, Tag, Alert, Button, Space, Modal, Input, Typography, message, Empty } from 'antd';
import { ClockCircleOutlined, AlertOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { opportunitiesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { StaleReview } from '@/types';
import dayjs from 'dayjs';

/**
 * Reviews that were claimed and then stopped moving.
 *
 * Claiming an opportunity for review freezes it: the partner cannot edit or
 * withdraw it. That is fine while somebody is reviewing, and invisible the
 * moment they are not — which is what this page exists to make visible.
 * Releasing a claim puts the opportunity back in the queue and unfreezes the
 * partner, deliberately without requiring the original reviewer to do it.
 */
const StaleReviewsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [releasing, setReleasing] = useState<StaleReview | null>(null);
  const [reason, setReason] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['stale-reviews'],
    queryFn: async () => (await opportunitiesApi.staleReviews()).data,
  });

  const releaseMut = useMutation({
    mutationFn: (id: number) => opportunitiesApi.releaseReview(id, reason.trim() || undefined),
    onSuccess: () => {
      setReleasing(null);
      setReason('');
      void queryClient.invalidateQueries({ queryKey: ['stale-reviews'] });
      void message.success('Review released — the opportunity is back in the queue');
    },
    onError: () => { void message.error('Could not release the review'); },
  });

  if (error) return <Alert type="error" message="Failed to load stale reviews" showIcon />;

  const rows = data ?? [];

  const columns = [
    {
      title: 'Opportunity',
      dataIndex: 'name',
      render: (_: string, row: StaleReview) => (
        <a onClick={() => navigate(`/opportunities/${row.id}`)}>
          {row.name}
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>{row.customer_name}</div>
        </a>
      ),
    },
    { title: 'Partner', dataIndex: 'company_name', render: (v: string | null) => v ?? '—' },
    { title: 'Reviewer', dataIndex: 'reviewer_name', render: (v: string | null) => v ?? 'Unassigned' },
    {
      title: 'Claimed',
      dataIndex: 'claimed_at',
      render: (v: string) => dayjs(v).format('MMM D, YYYY'),
    },
    {
      title: 'Waiting',
      dataIndex: 'days_claimed',
      sorter: (a: StaleReview, b: StaleReview) => a.days_claimed - b.days_claimed,
      render: (days: number, row: StaleReview) => (
        <Tag
          color={row.escalated ? 'red' : 'orange'}
          icon={row.escalated ? <AlertOutlined /> : <ClockCircleOutlined />}
        >
          {days} {days === 1 ? 'day' : 'days'}{row.escalated ? ' · escalated' : ''}
        </Tag>
      ),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, row: StaleReview) => (
        <Button size="small" onClick={() => setReleasing(row)}>Release</Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Stuck Reviews"
        breadcrumbs={[{ label: 'Opportunities', path: '/opportunities' }, { label: 'Stuck Reviews' }]}
      />

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Claimed reviews that have stopped moving"
        description="While an opportunity is under review the partner cannot edit or withdraw it. Releasing a claim returns it to the queue for another reviewer and unfreezes the partner."
      />

      <Card>
        <Table
          rowKey="id"
          loading={isLoading}
          dataSource={rows}
          columns={columns}
          pagination={false}
          locale={{
            emptyText: <Empty description="No review has been sitting long enough to worry about" />,
          }}
        />
      </Card>

      <Modal
        title="Release Review"
        open={releasing !== null}
        onCancel={() => { setReleasing(null); setReason(''); }}
        onOk={() => releasing && releaseMut.mutate(releasing.id)}
        confirmLoading={releaseMut.isPending}
        okText="Release"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            {releasing?.name} goes back to pending review and loses its reviewer, so
            anyone can pick it up — and the partner can edit it again.
          </Typography.Paragraph>
          <Input.TextArea
            rows={3}
            placeholder="Reason (optional — shown to the previous reviewer)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        </Space>
      </Modal>
    </>
  );
};

export default StaleReviewsPage;

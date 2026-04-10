import React, { useState } from 'react';
import { List, Button, Tag, Skeleton, Alert, Empty, Space, Typography, Badge, message } from 'antd';
import { BellOutlined, CheckOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationsApi } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/components/common/PageHeader';
import type { NotificationResponse } from '@/types';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const NotificationsPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['notifications', page],
    queryFn: async () => {
      const res = await notificationsApi.list({ page, page_size: 20 });
      return res.data;
    },
  });

  const markReadMut = useMutation({
    mutationFn: (ids: number[]) => notificationsApi.markRead(ids),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['notifications'] }); void queryClient.invalidateQueries({ queryKey: ['notification-count'] }); },
  });

  const markAllMut = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notification-count'] });
      void message.success('All marked as read');
    },
  });

  const handleClick = (notif: NotificationResponse) => {
    if (!notif.read) {
      markReadMut.mutate([notif.id]);
    }
    if (notif.entity_type && notif.entity_id) {
      const routes: Record<string, string> = {
        opportunity: `/opportunities/${notif.entity_id}`,
        company: `/companies/${notif.entity_id}`,
        doc_request: `/doc-requests`,
        enrollment: `/lms`,
      };
      const route = routes[notif.entity_type];
      if (route) navigate(route);
    }
  };

  if (error) return <Alert type="error" message="Failed to load notifications" showIcon />;

  return (
    <>
      <PageHeader
        title="Notifications"
        extra={<Button icon={<CheckOutlined />} onClick={() => markAllMut.mutate()} loading={markAllMut.isPending}>Mark All Read</Button>}
      />
      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <List
            itemLayout="horizontal"
            dataSource={data.items}
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage }}
            renderItem={(item: NotificationResponse) => (
              <List.Item
                onClick={() => handleClick(item)}
                style={{ cursor: 'pointer', background: item.read ? 'transparent' : '#e7e7f1', padding: '12px 16px', borderRadius: 8, marginBottom: 4 }}
              >
                <List.Item.Meta
                  avatar={<Badge dot={!item.read}><BellOutlined style={{ fontSize: 20 }} /></Badge>}
                  title={<Space><Typography.Text strong={!item.read}>{item.title}</Typography.Text><Tag>{item.type.replace(/_/g, ' ')}</Tag></Space>}
                  description={
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{item.message}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{dayjs(item.created_at).fromNow()}</Typography.Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        ) : <Empty description="No notifications" />
      )}
    </>
  );
};

export default NotificationsPage;

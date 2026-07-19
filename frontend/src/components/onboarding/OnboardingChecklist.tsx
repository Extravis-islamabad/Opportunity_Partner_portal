import React from 'react';
import { Card, List, Progress, Button, Typography, Space } from 'antd';
import { CheckCircleFilled, ClockCircleOutlined, RocketOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import { onboardingApi } from '@/api/endpoints';
import type { OnboardingChecklist as OnboardingChecklistData } from '@/types';

const BRAND = {
  royal500: '#3750ed',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  green: '#10b981',
};

const OnboardingChecklist: React.FC = () => {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['onboarding-checklist'],
    queryFn: async () => (await onboardingApi.getChecklist()).data as OnboardingChecklistData,
  });

  const completeMut = useMutation({
    mutationFn: async () => (await onboardingApi.complete()).data,
    onSuccess: () => {
      message.success('Onboarding dismissed');
      queryClient.invalidateQueries({ queryKey: ['onboarding-checklist'] });
    },
    onError: () => {
      message.error('Could not dismiss onboarding');
    },
  });

  // Supplementary card: render nothing while loading or once completed.
  if (isLoading || !data) return null;
  if (data.has_completed_onboarding) return null;

  const items = data.items ?? [];
  const total = items.length;
  const completed = items.filter((i) => i.completed).length;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <Card
      title={
        <Space>
          <RocketOutlined style={{ color: BRAND.royal500 }} />
          <span>Getting Started</span>
        </Space>
      }
      bordered={false}
      style={{ borderRadius: 12 }}
      styles={{ header: { borderBottom: `1px solid ${BRAND.royal50}` } }}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        Complete these steps to get the most out of the partner portal.
      </Typography.Paragraph>

      <Progress
        percent={percent}
        strokeColor={{ '0%': BRAND.royal500, '100%': BRAND.green }}
        strokeWidth={10}
        style={{ marginBottom: 8 }}
      />

      <List
        itemLayout="horizontal"
        dataSource={items}
        renderItem={(item) => (
          <List.Item key={item.key} style={{ paddingLeft: 0, paddingRight: 0 }}>
            <Space align="start">
              {item.completed ? (
                <CheckCircleFilled style={{ color: BRAND.green, fontSize: 18 }} />
              ) : (
                <ClockCircleOutlined style={{ color: '#9ca3af', fontSize: 18 }} />
              )}
              <Typography.Text
                delete={item.completed}
                type={item.completed ? 'secondary' : undefined}
                style={{ color: item.completed ? undefined : BRAND.navy }}
              >
                {item.label}
              </Typography.Text>
            </Space>
          </List.Item>
        )}
      />

      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Button
          onClick={() => completeMut.mutate()}
          loading={completeMut.isPending}
        >
          Got it, hide this
        </Button>
      </div>
    </Card>
  );
};

export default OnboardingChecklist;

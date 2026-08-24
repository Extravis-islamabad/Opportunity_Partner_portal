/**
 * What was actually done on this POC, and by whom.
 *
 * The team roster above says who is *assigned*. This says who has *logged
 * work*, which is a different and often more interesting question — a person
 * on the team with zero activities is exactly the thing this view exists to
 * make visible, so they appear with a zero rather than being left out.
 *
 * Internal only. The API refuses partners, who see the roster and their roles
 * and nothing behind it; the parent only mounts this for staff.
 */
import React from 'react';
import { Card, Table, Tag, Typography, Empty, Space, Tooltip, Skeleton, Alert } from 'antd';
import { HistoryOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { pocsApi } from '@/api/endpoints';
import type { PocActivityEntry, PocActivityPerson } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

/** "95" → "1h 35m". Minutes alone stop being readable past an hour or so. */
const formatMinutes = (total: number): string => {
  if (total === 0) return '—';
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (!hours) return `${minutes}m`;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
};

interface Props {
  pocId: number;
}

const PocActivityPanel: React.FC<Props> = ({ pocId }) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['poc-activities', pocId],
    queryFn: async () => (await pocsApi.activities(pocId)).data,
  });

  const personColumns: ColumnsType<PocActivityPerson> = [
    {
      title: 'Person',
      dataIndex: 'user_name',
      key: 'user_name',
      render: (name: string | null, record) => (
        <Space size={6}>
          <Text strong={record.activity_count > 0}>{name ?? 'Unknown'}</Text>
          {!record.on_team && (
            <Tooltip title="Logged work on this POC but is no longer on the team">
              <Tag>past member</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'POC Role',
      dataIndex: 'poc_role_label',
      key: 'poc_role_label',
      render: (label: string | null) =>
        label ?? <Text type="secondary" style={{ fontSize: 12 }}>—</Text>,
    },
    {
      title: 'Activities',
      dataIndex: 'activity_count',
      key: 'activity_count',
      align: 'right',
      render: (count: number) =>
        count > 0 ? (
          <Text strong>{count}</Text>
        ) : (
          // Called out rather than shown as a bare 0: "assigned but nothing
          // recorded" is a finding, not a blank.
          <Text type="secondary" style={{ fontSize: 12 }}>none logged</Text>
        ),
    },
    {
      title: 'Time',
      dataIndex: 'total_duration_minutes',
      key: 'total_duration_minutes',
      align: 'right',
      render: (mins: number) => <Text>{formatMinutes(mins)}</Text>,
    },
  ];

  const entryColumns: ColumnsType<PocActivityEntry> = [
    {
      title: 'Date',
      dataIndex: 'activity_date',
      key: 'activity_date',
      width: 110,
    },
    { title: 'Who', dataIndex: 'user_name', key: 'user_name' },
    {
      title: 'Type',
      dataIndex: 'activity_type_label',
      key: 'activity_type_label',
      render: (label: string) => <Tag color="#3750ed" style={{ border: 'none' }}>{label}</Tag>,
    },
    {
      title: 'Duration',
      dataIndex: 'duration_minutes',
      key: 'duration_minutes',
      render: (mins: number | null) => (mins ? formatMinutes(mins) : '—'),
    },
    {
      title: 'Logged against',
      dataIndex: 'linked_via',
      key: 'linked_via',
      // The two links are not the same claim: one says "this was POC work",
      // the other says "this was work on the deal this POC belongs to".
      render: (via: 'poc' | 'opportunity') =>
        via === 'poc' ? (
          <Tag color="cyan">POC</Tag>
        ) : (
          <Tooltip title="Logged against the opportunity this POC belongs to, not the POC itself">
            <Tag>Opportunity</Tag>
          </Tooltip>
        ),
    },
    {
      title: 'Notes',
      dataIndex: 'notes',
      key: 'notes',
      render: (notes: string | null) =>
        notes ? (
          <Text style={{ fontSize: 12 }}>{notes}</Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <HistoryOutlined />
          <span>
            Activity on this POC
            {data && data.total_activities > 0 ? ` (${data.total_activities})` : ''}
          </span>
        </Space>
      }
      style={{ marginTop: 16 }}
      extra={
        data && data.total_duration_minutes > 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatMinutes(data.total_duration_minutes)} logged in total
          </Text>
        ) : null
      }
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : error ? (
        <Alert type="error" showIcon message="Could not load the activity log" />
      ) : (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Per person
          </Text>
          <Table
            rowKey="user_id"
            size="small"
            style={{ marginTop: 8, marginBottom: 20 }}
            columns={personColumns}
            dataSource={data?.by_person ?? []}
            pagination={false}
            locale={{
              emptyText: (
                <Empty
                  description="Nobody on the team yet"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ),
            }}
          />

          <Text type="secondary" style={{ fontSize: 12 }}>
            Every activity
          </Text>
          <Table
            rowKey="id"
            size="small"
            style={{ marginTop: 8 }}
            columns={entryColumns}
            dataSource={data?.items ?? []}
            pagination={
              (data?.items.length ?? 0) > 10 ? { pageSize: 10, size: 'small' } : false
            }
            scroll={{ x: 720 }}
            locale={{
              emptyText: (
                <Empty
                  description="No activity logged against this POC yet"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ),
            }}
          />
        </>
      )}
    </Card>
  );
};

export default PocActivityPanel;

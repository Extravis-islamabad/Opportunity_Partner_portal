import React, { useState } from 'react';
import { Table, Input, Tag, Space, Select, Skeleton, Alert, Empty, Popover, Button, DatePicker } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs, { Dayjs } from 'dayjs';
import { auditLogsApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { AuditLogItem } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const { RangePicker } = DatePicker;

const ENTITY_TYPES = [
  'user',
  'company',
  'opportunity',
  'poc',
  'customer_license',
  'deal_registration',
  'doc_request',
  'kb_document',
  'commission',
  'course',
  'enrollment',
];

const titleCase = (s: string) =>
  s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const actionColor = (action: string): string => {
  const a = (action || '').toUpperCase();
  if (a.includes('CREATE')) return 'green';
  if (a.includes('UPDATE')) return 'blue';
  if (a.includes('DELETE') || a.includes('REMOVE')) return 'red';
  if (a.includes('LOGIN') || a.includes('LOGOUT')) return 'default';
  if (a.includes('APPROVE')) return 'green';
  if (a.includes('REJECT')) return 'red';
  return 'purple';
};

const AuditLogsPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<string>('');
  const [entityType, setEntityType] = useState<string | undefined>();
  const [dateFrom, setDateFrom] = useState<string | undefined>();
  const [dateTo, setDateTo] = useState<string | undefined>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['audit-logs', page, action, entityType, dateFrom, dateTo],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 50 };
      if (action) params['action'] = action;
      if (entityType) params['entity_type'] = entityType;
      if (dateFrom) params['date_from'] = dateFrom;
      if (dateTo) params['date_to'] = dateTo;
      const res = await auditLogsApi.list(params);
      return res.data;
    },
  });

  const handleActionChange = (value: string) => {
    setAction(value);
    setPage(1);
  };

  const handleEntityTypeChange = (value: string | undefined) => {
    setEntityType(value);
    setPage(1);
  };

  const handleRangeChange = (range: [Dayjs | null, Dayjs | null] | null) => {
    if (range && range[0] && range[1]) {
      setDateFrom(range[0].startOf('day').toISOString());
      setDateTo(range[1].endOf('day').toISOString());
    } else {
      setDateFrom(undefined);
      setDateTo(undefined);
    }
    setPage(1);
  };

  const columns: ColumnsType<AuditLogItem> = [
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'),
    },
    { title: 'User', dataIndex: 'user_full_name', key: 'user' },
    {
      title: 'Action',
      dataIndex: 'action',
      key: 'action',
      render: (a: string) => <Tag color={actionColor(a)}>{a}</Tag>,
    },
    {
      title: 'Entity',
      key: 'entity',
      render: (_, record) => `${record.entity_type} #${record.entity_id}`,
    },
    {
      title: 'Details',
      key: 'details',
      render: (_, record) =>
        record.metadata_json ? (
          <Popover
            trigger="click"
            content={
              <pre style={{ maxWidth: 480, maxHeight: 400, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(record.metadata_json, null, 2)}
              </pre>
            }
          >
            <Button type="link" size="small">View</Button>
          </Popover>
        ) : (
          '—'
        ),
    },
  ];

  if (error) return <Alert type="error" message="Failed to load audit logs" showIcon />;

  return (
    <>
      <PageHeader title="Audit Logs" subtitle={`${data?.total ?? 0} total entries`} />
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="Action"
          allowClear
          style={{ width: 200 }}
          value={action}
          onChange={(e) => handleActionChange(e.target.value)}
        />
        <Select
          placeholder="Entity type"
          allowClear
          style={{ width: 200 }}
          value={entityType}
          onChange={handleEntityTypeChange}
          options={ENTITY_TYPES.map((t) => ({ value: t, label: titleCase(t) }))}
        />
        <RangePicker onChange={handleRangeChange} />
      </Space>
      {isLoading ? (
        <Skeleton active />
      ) : data && data.items.length > 0 ? (
        <Table
          columns={columns}
          dataSource={data.items}
          rowKey="id"
          pagination={{
            current: page,
            pageSize: 50,
            total: data.total,
            onChange: setPage,
            showSizeChanger: false,
            showTotal: (total) => `${total} total entries`,
          }}
        />
      ) : (
        <Empty description="No audit logs found" />
      )}
    </>
  );
};

export default AuditLogsPage;

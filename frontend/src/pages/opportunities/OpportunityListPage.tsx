import React, { useState } from 'react';
import { Table, Button, Input, Tag, Space, Select, Skeleton, Alert, Empty, message } from 'antd';
import { PlusOutlined, SearchOutlined, EyeOutlined, StarFilled, WarningOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { opportunitiesApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { OpportunityListItem } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

const statusColors: Record<string, string> = {
  draft: 'default', pending_review: 'orange', under_review: 'processing',
  approved: 'green', rejected: 'red', removed: 'default', multi_partner_flagged: 'warning',
};

const OpportunityListPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { data, isLoading, error } = useQuery({
    queryKey: ['opportunities', page, search, statusFilter],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (search) params['search'] = search;
      if (statusFilter) params['status'] = statusFilter;
      const res = await opportunitiesApi.list(params);
      return res.data;
    },
  });

  const columns: ColumnsType<OpportunityListItem> = [
    {
      title: 'Opportunity', dataIndex: 'name', key: 'name',
      render: (name: string, record) => (
        <Space>
          {name}
          {record.preferred_partner && <StarFilled style={{ color: '#faad14' }} />}
          {record.multi_partner_alert && <WarningOutlined style={{ color: '#ff4d4f' }} />}
        </Space>
      ),
    },
    { title: 'Customer', dataIndex: 'customer_name', key: 'customer' },
    ...(isAdmin ? [{ title: 'Company', dataIndex: 'company_name' as const, key: 'company' }] : []),
    { title: 'Worth (USD)', dataIndex: 'worth', key: 'worth', render: (v: string) => `$${Number(v).toLocaleString()}` },
    { title: 'Closing Date', dataIndex: 'closing_date', key: 'date', render: (d: string) => dayjs(d).format('MMM D, YYYY') },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColors[s] ?? 'default'}>{s.replace(/_/g, ' ').toUpperCase()}</Tag>,
    },
    {
      title: 'Actions', key: 'actions',
      render: (_, record) => <Button type="link" icon={<EyeOutlined />} onClick={() => navigate(`/opportunities/${record.id}`)}>View</Button>,
    },
  ];

  if (error) return <Alert type="error" message="Failed to load opportunities" showIcon />;

  return (
    <>
      <PageHeader
        title={isAdmin ? 'All Opportunities' : 'My Opportunities'}
        subtitle={`${data?.total ?? 0} total`}
        extra={!isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/opportunities/create')}>New Opportunity</Button>}
      />
      <Space style={{ marginBottom: 16 }}>
        <Input.Search placeholder="Search..." allowClear onSearch={setSearch} style={{ width: 300 }} prefix={<SearchOutlined />} />
        <Select placeholder="Status" allowClear style={{ width: 180 }} onChange={setStatusFilter}
          options={[
            { value: 'draft', label: 'Draft' }, { value: 'pending_review', label: 'Pending Review' },
            { value: 'under_review', label: 'Under Review' }, { value: 'approved', label: 'Approved' },
            { value: 'rejected', label: 'Rejected' },
          ]}
        />
      </Space>
      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <Table columns={columns} dataSource={data.items} rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage, showTotal: (t) => `Total ${t}` }} />
        ) : <Empty description="No opportunities found" />
      )}
    </>
  );
};

export default OpportunityListPage;

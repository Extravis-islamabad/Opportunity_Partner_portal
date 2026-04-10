import React, { useState } from 'react';
import { Table, Button, Input, Tag, Space, Skeleton, Alert, Empty, Popconfirm, message } from 'antd';
import { PlusOutlined, SearchOutlined, EyeOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { companiesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { CompanyResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const tierColors: Record<string, string> = { silver: 'default', gold: 'gold', platinum: 'blue' };

const CompanyListPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['companies', page, search],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (search) params['search'] = search;
      const res = await companiesApi.list(params);
      return res.data;
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => companiesApi.deactivate(id),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['companies'] }); void message.success('Company deactivated'); },
  });

  const columns: ColumnsType<CompanyResponse> = [
    { title: 'Name', dataIndex: 'name', key: 'name', sorter: true },
    { title: 'Country', dataIndex: 'country', key: 'country' },
    { title: 'Industry', dataIndex: 'industry', key: 'industry' },
    { title: 'Tier', dataIndex: 'tier', key: 'tier', render: (tier: string) => <Tag color={tierColors[tier] ?? 'default'}>{tier.toUpperCase()}</Tag> },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s.toUpperCase()}</Tag> },
    { title: 'Channel Manager', dataIndex: 'channel_manager_name', key: 'cm' },
    { title: 'Partners', dataIndex: 'partner_count', key: 'partners' },
    {
      title: 'Actions', key: 'actions', render: (_, record) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => navigate(`/companies/${record.id}`)}>View</Button>
          <Popconfirm title="Deactivate this company?" onConfirm={() => deactivateMutation.mutate(record.id)} okText="Yes" cancelText="No">
            <Button type="link" danger icon={<DeleteOutlined />}>Deactivate</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (error) return <Alert type="error" message="Failed to load companies" showIcon />;

  return (
    <>
      <PageHeader
        title="Partner Companies"
        subtitle={`${data?.total ?? 0} total companies`}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/companies/create')}>Add Company</Button>}
      />
      <Input.Search
        placeholder="Search companies..."
        allowClear
        prefix={<SearchOutlined />}
        onSearch={setSearch}
        style={{ marginBottom: 16, maxWidth: 400 }}
      />
      {isLoading ? <Skeleton active /> : (
        data && data.items.length > 0 ? (
          <Table
            columns={columns}
            dataSource={data.items}
            rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage, showTotal: (t) => `Total ${t} companies` }}
          />
        ) : <Empty description="No companies found" />
      )}
    </>
  );
};

export default CompanyListPage;

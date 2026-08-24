import React, { useState } from 'react';
import { Table, Button, Input, Tag, Space, Alert, Popconfirm, Select, message } from 'antd';
import { PlusOutlined, SearchOutlined, EyeOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { companiesApi, exportsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import EmptyState from '@/components/common/EmptyState';
import TableSkeleton from '@/components/common/TableSkeleton';
import ExportMenu from '@/components/common/ExportMenu';
import type { CompanyResponse, CompanyType } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import { COMPANY_TYPE_OPTIONS, companyTypeMeta } from '@/utils/companyType';

const tierColors: Record<string, string> = { silver: 'default', gold: 'gold', platinum: 'blue' };

const CompanyListPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [companyType, setCompanyType] = useState<CompanyType | undefined>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isSuperadmin = !!user?.is_superadmin;

  const { data, isLoading, error } = useQuery({
    queryKey: ['companies', page, search, companyType],
    queryFn: async () => {
      const params: Record<string, string | number | undefined> = { page, page_size: 20 };
      if (search) params['search'] = search;
      if (companyType) params['company_type'] = companyType;
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
    {
      title: 'Type', dataIndex: 'company_type', key: 'company_type',
      render: (type: CompanyType) => {
        const meta = companyTypeMeta(type);
        return meta ? <Tag color={meta.color}>{meta.label.toUpperCase()}</Tag> : '—';
      },
    },
    {
      title: 'Parent Distributor',
      dataIndex: 'parent_distributor_name',
      key: 'parent_distributor',
      // Blank for most companies — they report directly to Extravis.
      render: (name: string | null) =>
        name ?? <span style={{ opacity: 0.45 }}>—</span>,
    },
    { title: 'Country', dataIndex: 'country', key: 'country' },
    { title: 'Industry', dataIndex: 'industry', key: 'industry' },
    {
      title: 'Tier', dataIndex: 'tier', key: 'tier',
      // Null for a customer company — tier is a partner-programme concept.
      render: (tier: string | null) =>
        tier ? <Tag color={tierColors[tier] ?? 'default'}>{tier.toUpperCase()}</Tag> : <span style={{ opacity: 0.45 }}>—</span>,
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s.toUpperCase()}</Tag> },
    { title: 'Channel Manager', dataIndex: 'channel_manager_name', key: 'cm' },
    { title: 'Partners', dataIndex: 'partner_count', key: 'partners' },
    {
      title: 'Actions', key: 'actions', render: (_, record) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => navigate(`/companies/${record.id}`)}>View</Button>
          {isSuperadmin && (
            <Popconfirm title="Deactivate this company?" onConfirm={() => deactivateMutation.mutate(record.id)} okText="Yes" cancelText="No">
              <Button type="link" danger icon={<DeleteOutlined />}>Deactivate</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  if (error) return <Alert type="error" message="Failed to load companies" showIcon />;

  const exportParams: Record<string, string | number | undefined> = {};
  if (search) exportParams['search'] = search;
  if (companyType) exportParams['company_type'] = companyType;

  return (
    <>
      <PageHeader
        title={isSuperadmin ? 'Partner Companies' : 'My Partner Companies'}
        subtitle={
          isSuperadmin
            ? `${data?.total ?? 0} total companies`
            : `${data?.total ?? 0} ${(data?.total ?? 0) === 1 ? 'company' : 'companies'} you channel-manage`
        }
        extra={
          <Space>
            <ExportMenu
              filenamePrefix="companies"
              pdf={() => exportsApi.companiesPdf(exportParams)}
              xlsx={() => exportsApi.companiesXlsx(exportParams)}
            />
            {isSuperadmin && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/companies/create')}>
                Add Company
              </Button>
            )}
          </Space>
        }
      />
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="Search companies..."
          allowClear
          prefix={<SearchOutlined />}
          onSearch={(v) => { setSearch(v); setPage(1); }}
          style={{ width: 320 }}
        />
        <Select
          placeholder="All types"
          allowClear
          style={{ width: 180 }}
          value={companyType}
          onChange={(v) => { setCompanyType(v); setPage(1); }}
          options={COMPANY_TYPE_OPTIONS}
        />
      </Space>
      {isLoading ? <TableSkeleton /> : (
        data && data.items.length > 0 ? (
          <Table
            columns={columns}
            dataSource={data.items}
            rowKey="id"
            pagination={{ current: page, total: data.total, pageSize: 20, onChange: setPage, showTotal: (t) => `Total ${t} companies` }}
          />
        ) : (
          <EmptyState
            title={isSuperadmin ? 'No companies found' : 'No companies assigned to you'}
            description={
              isSuperadmin
                ? 'Add a partner company to start tracking opportunities and deals.'
                : 'You are not currently assigned as channel manager for any companies. Contact a superadmin to be assigned.'
            }
            action={
              isSuperadmin ? (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/companies/create')}>
                  Add Company
                </Button>
              ) : null
            }
          />
        )
      )}
    </>
  );
};

export default CompanyListPage;

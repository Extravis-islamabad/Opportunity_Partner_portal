import React from 'react';
import { Descriptions, Card, Table, Tag, Skeleton, Alert, Empty, Button, Space, Row, Col, Statistic } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { companiesApi, dashboardApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { PartnerAccountBrief } from '@/types';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined } from '@ant-design/icons';

const tierColors: Record<string, string> = { silver: 'default', gold: 'gold', platinum: 'blue' };

const CompanyDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const companyId = Number(id);

  const { data: company, isLoading, error } = useQuery({
    queryKey: ['company', companyId],
    queryFn: async () => { const res = await companiesApi.get(companyId); return res.data; },
  });

  const { data: performance } = useQuery({
    queryKey: ['company-performance', companyId],
    queryFn: async () => { const res = await dashboardApi.getCompanyPerformance(companyId); return res.data; },
    enabled: !!company,
  });

  if (error) return <Alert type="error" message="Failed to load company" showIcon />;
  if (isLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
  if (!company) return <Empty description="Company not found" />;

  const partnerColumns: ColumnsType<PartnerAccountBrief> = [
    { title: 'Name', dataIndex: 'full_name', key: 'name' },
    { title: 'Email', dataIndex: 'email', key: 'email' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'pending_activation' ? 'orange' : 'red'}>{s.toUpperCase()}</Tag> },
    { title: 'Job Title', dataIndex: 'job_title', key: 'job' },
  ];

  return (
    <>
      <PageHeader
        title={company.name}
        breadcrumbs={[{ label: 'Companies', path: '/companies' }, { label: company.name }]}
        extra={
          <Space>
            <Button icon={<EditOutlined />} onClick={() => navigate(`/companies/${companyId}/edit`)}>Edit</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/users?action=create&company_id=${companyId}`)}>Add Partner</Button>
          </Space>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="Company Information">
            <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
              <Descriptions.Item label="Country">{company.country}</Descriptions.Item>
              <Descriptions.Item label="Region">{company.region}</Descriptions.Item>
              <Descriptions.Item label="City">{company.city}</Descriptions.Item>
              <Descriptions.Item label="Industry">{company.industry}</Descriptions.Item>
              <Descriptions.Item label="Contact Email">{company.contact_email}</Descriptions.Item>
              <Descriptions.Item label="Channel Manager">{company.channel_manager_name}</Descriptions.Item>
              <Descriptions.Item label="Status"><Tag color={company.status === 'active' ? 'green' : 'red'}>{company.status.toUpperCase()}</Tag></Descriptions.Item>
              <Descriptions.Item label="Tier"><Tag color={tierColors[company.tier] ?? 'default'}>{company.tier.toUpperCase()}</Tag></Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          {performance && (
            <Card title="Performance">
              <Statistic title="Opportunities Submitted" value={performance.opportunities_submitted} />
              <Statistic title="Won" value={performance.opportunities_won} valueStyle={{ color: '#3f8600' }} style={{ marginTop: 8 }} />
              <Statistic title="Lost" value={performance.opportunities_lost} valueStyle={{ color: '#cf1322' }} style={{ marginTop: 8 }} />
              <Statistic title="LMS Completion" value={performance.lms_completion_rate} suffix="%" style={{ marginTop: 8 }} />
            </Card>
          )}
        </Col>
      </Row>

      <Card title={`Partner Accounts (${company.partners.length})`} style={{ marginTop: 16 }}>
        {company.partners.length > 0 ? (
          <Table columns={partnerColumns} dataSource={company.partners} rowKey="id" pagination={false} />
        ) : (
          <Empty description="No partner accounts" />
        )}
      </Card>
    </>
  );
};

export default CompanyDetailPage;

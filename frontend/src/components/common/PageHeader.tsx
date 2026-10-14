import React, { useEffect } from 'react';
import { Typography, Space, Breadcrumb } from 'antd';
import { Link } from 'react-router-dom';
import { HomeOutlined } from '@ant-design/icons';
import { useBreadcrumbOwnership } from '@/contexts/BreadcrumbContext';

const { Title } = Typography;

interface BreadcrumbItem {
  label: string;
  path?: string;
}

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  breadcrumbs?: BreadcrumbItem[];
  extra?: React.ReactNode;
}

const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, breadcrumbs, extra }) => {
  const hasCrumbs = !!breadcrumbs && breadcrumbs.length > 0;
  const { setPageOwnsCrumbs } = useBreadcrumbOwnership();
  // Tell the layout to hide its route-derived trail while this one shows.
  useEffect(() => {
    if (!hasCrumbs) return undefined;
    setPageOwnsCrumbs((n) => n + 1);
    return () => setPageOwnsCrumbs((n) => n - 1);
  }, [hasCrumbs, setPageOwnsCrumbs]);

  return (
    <div style={{ marginBottom: 24 }}>
      {hasCrumbs && (
        <Breadcrumb
          style={{ marginBottom: 12 }}
          items={[
            { title: <Link to="/dashboard" aria-label="Dashboard"><HomeOutlined /></Link> },
            ...breadcrumbs.map((item) => ({
              title: item.path ? <Link to={item.path}>{item.label}</Link> : item.label,
            })),
          ]}
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space direction="vertical" size={0}>
          <Title level={3} style={{ margin: 0 }}>{title}</Title>
          {subtitle && (
            <Typography.Text type="secondary">{subtitle}</Typography.Text>
          )}
        </Space>
        {extra && <div>{extra}</div>}
      </div>
    </div>
  );
};

export default PageHeader;

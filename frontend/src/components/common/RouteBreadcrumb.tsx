import React from 'react';
import { Breadcrumb } from 'antd';
import { Link, useLocation } from 'react-router-dom';
import { HomeOutlined } from '@ant-design/icons';
import { buildCrumbs } from '@/routes/routeConfig';

const RouteBreadcrumb: React.FC = () => {
  const location = useLocation();
  const crumbs = buildCrumbs(location.pathname);

  // On the dashboard there's nothing useful to show
  if (crumbs.length === 0 || location.pathname === '/dashboard') return null;

  const items = [
    {
      key: 'home',
      title: (
        <Link to="/dashboard">
          <HomeOutlined />
        </Link>
      ),
    },
    ...crumbs.map((c, idx) => ({
      key: `${c.label}-${idx}`,
      title: c.path ? <Link to={c.path}>{c.label}</Link> : <span>{c.label}</span>,
    })),
  ];

  return <Breadcrumb items={items} style={{ marginBottom: 12 }} />;
};

export default RouteBreadcrumb;

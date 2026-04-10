import React, { useState } from 'react';
import { Layout, Menu, Avatar, Dropdown, Badge, Space, Typography } from 'antd';
import {
  DashboardOutlined,
  BankOutlined,
  TeamOutlined,
  FundProjectionScreenOutlined,
  BookOutlined,
  ReadOutlined,
  FileTextOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TrophyOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useQuery } from '@tanstack/react-query';
import { notificationsApi } from '@/api/endpoints';
import type { MenuProps } from 'antd';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const AppLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { data: notifCount } = useQuery({
    queryKey: ['notification-count'],
    queryFn: async () => {
      const res = await notificationsApi.getCount();
      return res.data;
    },
    refetchInterval: 30000,
  });

  const adminMenuItems: MenuProps['items'] = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
    { key: '/companies', icon: <BankOutlined />, label: 'Companies' },
    { key: '/users', icon: <TeamOutlined />, label: 'Users' },
    { key: '/opportunities', icon: <FundProjectionScreenOutlined />, label: 'Opportunities' },
    { key: '/knowledge-base', icon: <BookOutlined />, label: 'Knowledge Base' },
    { key: '/lms', icon: <ReadOutlined />, label: 'LMS / Training' },
    { key: '/doc-requests', icon: <FileTextOutlined />, label: 'Document Requests' },
    { key: '/deals', icon: <SafetyCertificateOutlined />, label: 'Deal Registration' },
  ];

  const partnerMenuItems: MenuProps['items'] = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
    { key: '/opportunities', icon: <FundProjectionScreenOutlined />, label: 'My Opportunities' },
    { key: '/knowledge-base', icon: <BookOutlined />, label: 'Knowledge Base' },
    { key: '/lms', icon: <ReadOutlined />, label: 'Training Courses' },
    { key: '/doc-requests', icon: <FileTextOutlined />, label: 'Document Requests' },
    { key: '/deals', icon: <SafetyCertificateOutlined />, label: 'Deal Registration' },
  ];

  const menuItems = isAdmin ? adminMenuItems : partnerMenuItems;

  const selectedKey = '/' + location.pathname.split('/')[1];

  const userMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <UserOutlined />, label: 'Profile' },
    { key: 'logout', icon: <LogoutOutlined />, label: 'Logout', danger: true },
  ];

  const handleUserMenuClick: MenuProps['onClick'] = async ({ key }) => {
    if (key === 'profile') {
      navigate('/profile');
    } else if (key === 'logout') {
      await logout();
      navigate('/login');
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }} hasSider>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={220}
        style={{
          background: '#001529',
          overflow: 'auto',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
          zIndex: 10,
        }}
      >
        <div style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
        }}>
          <Text strong style={{ color: '#fff', fontSize: collapsed ? 14 : 18 }}>
            {collapsed ? 'EP' : 'Extravis Portal'}
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
        {!collapsed && user?.company_name && (
          <div style={{ padding: '16px', borderTop: '1px solid rgba(255,255,255,0.1)', position: 'absolute', bottom: 48, left: 0, right: 0 }}>
            <Space direction="vertical" size={0}>
              <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Company</Text>
              <Text style={{ color: '#fff', fontSize: 13 }}>{user.company_name}</Text>
              <Badge
                count={user.role === 'partner' ? (user as Record<string, unknown>).company_tier as string : undefined}
                style={{ backgroundColor: '#52c41a', marginTop: 4 }}
              />
            </Space>
          </div>
        )}
      </Sider>
      <Layout style={{ flex: 1, minWidth: 0 }}>
        <Header style={{
          background: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
        }}>
          <div
            onClick={() => setCollapsed(!collapsed)}
            style={{ cursor: 'pointer', fontSize: 18 }}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
          <Space size={20}>
            <Badge count={notifCount?.unread_count ?? 0} size="small">
              <BellOutlined
                style={{ fontSize: 20, cursor: 'pointer' }}
                onClick={() => navigate('/notifications')}
              />
            </Badge>
            <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} />
                <Text>{user?.full_name}</Text>
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ margin: 16, padding: 20, background: '#fff', borderRadius: 8, minHeight: 360 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;

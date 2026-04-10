import React, { useState } from 'react';
import { Layout, Menu, Avatar, Dropdown, Badge, Space, Typography, theme, Button, Tooltip } from 'antd';
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
  SafetyCertificateOutlined,
  BulbOutlined,
  BulbFilled,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useAppTheme } from '@/contexts/ThemeContext';
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
  const { isDark, toggle: toggleTheme } = useAppTheme();
  const { token } = theme.useToken();
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

  // Theme-aware colors. Sider always stays dark (like an app shell) but the
  // header + content follow the algorithm so the rest of the app is readable
  // in both modes.
  const siderBg = isDark ? '#0b0e14' : '#001529';
  const siderBorder = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.1)';

  return (
    <Layout style={{ minHeight: '100vh', background: token.colorBgLayout }} hasSider>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={220}
        style={{
          background: siderBg,
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
          borderBottom: `1px solid ${siderBorder}`,
        }}>
          <Text strong style={{ color: '#fff', fontSize: collapsed ? 14 : 18 }}>
            {collapsed ? 'EP' : 'Extravis Portal'}
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          style={{ background: siderBg }}
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
        {!collapsed && user?.company_name && (
          <div style={{ padding: '16px', borderTop: `1px solid ${siderBorder}`, position: 'absolute', bottom: 48, left: 0, right: 0 }}>
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
      <Layout style={{ flex: 1, minWidth: 0, background: token.colorBgLayout }}>
        <Header style={{
          background: token.colorBgContainer,
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: `0 1px 4px ${isDark ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.08)'}`,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}>
          <div
            onClick={() => setCollapsed(!collapsed)}
            style={{ cursor: 'pointer', fontSize: 18, color: token.colorText }}
            role="button"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
          <Space size={16}>
            <Tooltip title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}>
              <Button
                type="text"
                shape="circle"
                icon={isDark ? <BulbFilled style={{ color: '#faad14' }} /> : <BulbOutlined />}
                onClick={toggleTheme}
                aria-label="Toggle theme"
              />
            </Tooltip>
            <Badge count={notifCount?.unread_count ?? 0} size="small">
              <BellOutlined
                style={{ fontSize: 20, cursor: 'pointer', color: token.colorText }}
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
        <Content style={{
          margin: 16,
          padding: 20,
          background: token.colorBgContainer,
          borderRadius: 8,
          minHeight: 360,
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;

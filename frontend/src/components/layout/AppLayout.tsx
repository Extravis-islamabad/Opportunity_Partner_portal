import React, { useEffect, useState } from 'react';
import { Layout, Menu, Avatar, Dropdown, Badge, Space, Typography, theme, Button, Tooltip, Drawer } from 'antd';
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
  DollarOutlined,
  TrophyOutlined,
  CrownOutlined,
  SearchOutlined,
  MenuOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useAppTheme } from '@/contexts/ThemeContext';
import { useQuery } from '@tanstack/react-query';
import { notificationsApi } from '@/api/endpoints';
import KbChatWidget from '@/components/ai/KbChatWidget';
import CommandPalette from '@/components/common/CommandPalette';
import RouteBreadcrumb from '@/components/common/RouteBreadcrumb';
import { useBreakpoint } from '@/hooks/useBreakpoint';
import type { MenuProps } from 'antd';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const AppLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { isDark, toggle: toggleTheme } = useAppTheme();
  const { token } = theme.useToken();
  const { isMobile } = useBreakpoint();
  const isAdmin = user?.role === 'admin';

  // Global Cmd/Ctrl+K listener for the command palette
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      } else if (e.key === 'Escape' && paletteOpen) {
        setPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [paletteOpen]);

  // Close mobile drawer whenever the route changes
  useEffect(() => {
    setMobileDrawerOpen(false);
  }, [location.pathname]);

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
    { key: '/deals', icon: <SafetyCertificateOutlined />, label: 'Deal Registration' },
    { key: '/commissions', icon: <DollarOutlined />, label: 'Commissions' },
    { key: '/leaderboard', icon: <CrownOutlined />, label: 'Leaderboard' },
    { key: '/knowledge-base', icon: <BookOutlined />, label: 'Knowledge Base' },
    { key: '/lms', icon: <ReadOutlined />, label: 'LMS / Training' },
    { key: '/doc-requests', icon: <FileTextOutlined />, label: 'Document Requests' },
  ];

  const partnerMenuItems: MenuProps['items'] = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
    { key: '/scorecard', icon: <TrophyOutlined />, label: 'My Scorecard' },
    { key: '/opportunities', icon: <FundProjectionScreenOutlined />, label: 'My Opportunities' },
    { key: '/deals', icon: <SafetyCertificateOutlined />, label: 'Deal Registration' },
    { key: '/commissions', icon: <DollarOutlined />, label: 'My Commissions' },
    { key: '/leaderboard', icon: <CrownOutlined />, label: 'Leaderboard' },
    { key: '/knowledge-base', icon: <BookOutlined />, label: 'Knowledge Base' },
    { key: '/lms', icon: <ReadOutlined />, label: 'Training Courses' },
    { key: '/doc-requests', icon: <FileTextOutlined />, label: 'Document Requests' },
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

  const sideMenu = (
    <>
      <div style={{
        height: 64,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderBottom: `1px solid ${siderBorder}`,
      }}>
        <Text strong style={{ color: '#fff', fontSize: collapsed && !isMobile ? 14 : 18 }}>
          {collapsed && !isMobile ? 'EP' : 'Extravis Portal'}
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
      {!collapsed && user?.company_name && !isMobile && (
        <div style={{ padding: '16px', borderTop: `1px solid ${siderBorder}`, position: 'absolute', bottom: 48, left: 0, right: 0 }}>
          <Space direction="vertical" size={0}>
            <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Company</Text>
            <Text style={{ color: '#fff', fontSize: 13 }}>{user.company_name}</Text>
            <Badge
              count={user.role === 'partner' ? ((user as unknown) as Record<string, unknown>).company_tier as string : undefined}
              style={{ backgroundColor: '#52c41a', marginTop: 4 }}
            />
          </Space>
        </div>
      )}
    </>
  );

  return (
    <Layout style={{ minHeight: '100vh', background: token.colorBgLayout }} hasSider>
      {!isMobile && (
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
          {sideMenu}
        </Sider>
      )}

      {isMobile && (
        <Drawer
          placement="left"
          open={mobileDrawerOpen}
          onClose={() => setMobileDrawerOpen(false)}
          width={250}
          styles={{ body: { padding: 0, background: siderBg }, header: { display: 'none' } }}
        >
          {sideMenu}
        </Drawer>
      )}

      <Layout style={{ flex: 1, minWidth: 0, background: token.colorBgLayout }}>
        <Header style={{
          background: token.colorBgContainer,
          padding: '0 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: `0 1px 4px ${isDark ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.08)'}`,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}>
          <Space size={12}>
            {isMobile ? (
              <Button
                type="text"
                icon={<MenuOutlined style={{ fontSize: 20 }} />}
                onClick={() => setMobileDrawerOpen(true)}
                aria-label="Open menu"
              />
            ) : (
              <div
                onClick={() => setCollapsed(!collapsed)}
                style={{ cursor: 'pointer', fontSize: 18, color: token.colorText }}
                role="button"
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              >
                {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              </div>
            )}
          </Space>
          <Space size={isMobile ? 8 : 16}>
            <Tooltip title="Search (⌘K / Ctrl+K)">
              <Button
                type="text"
                icon={<SearchOutlined style={{ fontSize: 16 }} />}
                onClick={() => setPaletteOpen(true)}
                aria-label="Open command palette"
              >
                {!isMobile && <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>⌘K</span>}
              </Button>
            </Tooltip>
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
                {!isMobile && <Text>{user?.full_name}</Text>}
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{
          margin: isMobile ? 8 : 16,
          padding: isMobile ? 12 : 20,
          background: token.colorBgContainer,
          borderRadius: 8,
          minHeight: 360,
        }}>
          <RouteBreadcrumb />
          <Outlet />
        </Content>
      </Layout>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <KbChatWidget />
    </Layout>
  );
};

export default AppLayout;

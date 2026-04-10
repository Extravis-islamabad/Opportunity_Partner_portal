import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Modal, Input, List, Typography, Tag, Space, Empty } from 'antd';
import { SearchOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { ROUTES, type RouteDescriptor, type UserRole } from '@/routes/routeConfig';
import { useAuth } from '@/contexts/AuthContext';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose }) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);

  const role = (user?.role ?? 'partner') as UserRole;

  // Filter routes by role + search query
  const filtered: RouteDescriptor[] = useMemo(() => {
    const accessible = ROUTES.filter((r) => !r.roles || r.roles.includes(role));
    if (!query.trim()) return accessible;
    const q = query.trim().toLowerCase();
    return accessible.filter((r) => {
      if (r.label.toLowerCase().includes(q)) return true;
      if (r.section?.toLowerCase().includes(q)) return true;
      if (r.keywords?.some((k) => k.toLowerCase().includes(q))) return true;
      if (r.path.toLowerCase().includes(q)) return true;
      return false;
    });
  }, [query, role]);

  // Reset state whenever palette opens
  useEffect(() => {
    if (open) {
      setQuery('');
      setHighlighted(0);
    }
  }, [open]);

  // Clamp highlighted index when list shrinks
  useEffect(() => {
    if (highlighted >= filtered.length) {
      setHighlighted(Math.max(0, filtered.length - 1));
    }
  }, [filtered.length, highlighted]);

  const run = useCallback(
    (route: RouteDescriptor) => {
      navigate(route.path);
      onClose();
    },
    [navigate, onClose],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlighted((prev) => Math.min(prev + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlighted((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const target = filtered[highlighted];
        if (target) run(target);
      }
    },
    [filtered, highlighted, run],
  );

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      width={560}
      styles={{
        content: { padding: 0 },
        body: { padding: 0 },
      }}
    >
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--ant-color-border-secondary, #f0f0f0)' }}>
        <Input
          autoFocus
          size="large"
          prefix={<SearchOutlined />}
          placeholder="Search pages, sections…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          bordered={false}
        />
      </div>
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {filtered.length === 0 ? (
          <div style={{ padding: 24 }}>
            <Empty description="No matches" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : (
          <List
            dataSource={filtered}
            renderItem={(item, idx) => {
              const isActive = idx === highlighted;
              return (
                <List.Item
                  key={item.path}
                  onClick={() => run(item)}
                  onMouseEnter={() => setHighlighted(idx)}
                  style={{
                    cursor: 'pointer',
                    padding: '12px 16px',
                    background: isActive ? 'var(--ant-color-primary-bg, #e6f4ff)' : 'transparent',
                    borderLeft: isActive ? '3px solid var(--ant-color-primary, #1a237e)' : '3px solid transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                    <Space direction="vertical" size={0}>
                      <Typography.Text strong>{item.label}</Typography.Text>
                      {item.section && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {item.section}
                        </Typography.Text>
                      )}
                    </Space>
                    <Space>
                      {item.roles?.includes('admin') && <Tag color="blue">Admin</Tag>}
                      <ArrowRightOutlined style={{ color: '#888' }} />
                    </Space>
                  </div>
                </List.Item>
              );
            }}
          />
        )}
      </div>
      <div
        style={{
          padding: '8px 16px',
          borderTop: '1px solid var(--ant-color-border-secondary, #f0f0f0)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          <kbd>↑↓</kbd> navigate · <kbd>↵</kbd> open · <kbd>Esc</kbd> close
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          {filtered.length} results
        </Typography.Text>
      </div>
    </Modal>
  );
};

export default CommandPalette;

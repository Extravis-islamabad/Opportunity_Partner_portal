import React, { useState } from 'react';
import { Button, Card, Input, Space, Typography, Tag, message, Avatar, Spin, FloatButton } from 'antd';
import { MessageOutlined, SendOutlined, CloseOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { aiApi, type KbCitation } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';
import { useAppTheme } from '@/contexts/ThemeContext';

interface ChatTurn {
  role: 'user' | 'assistant';
  text: string;
  citations?: KbCitation[];
}

const KbChatWidget: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const navigate = useNavigate();
  const { isDark } = useAppTheme();

  // Probe whether AI is configured. If disabled, don't render anything.
  const { data: aiConfig } = useQuery({
    queryKey: ['ai-config'],
    queryFn: async () => {
      const res = await aiApi.config();
      return res.data;
    },
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,
  });

  const askMutation = useMutation({
    mutationFn: async (question: string) => {
      const res = await aiApi.kbAsk(question);
      return res.data;
    },
    onSuccess: (data) => {
      setHistory((prev) => [
        ...prev,
        { role: 'assistant', text: data.answer, citations: data.citations },
      ]);
    },
    onError: () => {
      void message.error('Failed to get answer');
    },
  });

  if (aiConfig && !aiConfig.enabled) {
    return null;
  }

  const handleSend = () => {
    const question = input.trim();
    if (!question || askMutation.isPending) return;
    setHistory((prev) => [...prev, { role: 'user', text: question }]);
    setInput('');
    askMutation.mutate(question);
  };

  return (
    <>
      <FloatButton
        icon={<MessageOutlined />}
        type="primary"
        tooltip="Ask the Knowledge Base"
        onClick={() => setOpen(true)}
        style={{ right: 24, bottom: 24 }}
      />

      {open && (
        <Card
          size="small"
          style={{
            position: 'fixed',
            right: 24,
            bottom: 80,
            width: 380,
            maxWidth: 'calc(100vw - 48px)',
            maxHeight: '72vh',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 1000,
            boxShadow: isDark
              ? '0 8px 32px rgba(0, 0, 0, 0.6)'
              : '0 8px 32px rgba(0, 0, 0, 0.15)',
          }}
          title={
            <Space>
              <RobotOutlined style={{ color: '#3750ed' }} />
              <span>KB Assistant</span>
            </Space>
          }
          extra={
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setOpen(false)}
            />
          }
          styles={{ body: { display: 'flex', flexDirection: 'column', padding: 12, height: 420 } }}
        >
          <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
            {history.length === 0 && !askMutation.isPending && (
              <Typography.Text type="secondary">
                Ask about the knowledge base, e.g. "What's the process for deal registration?"
              </Typography.Text>
            )}
            {history.map((turn, idx) => (
              <div
                key={idx}
                style={{
                  marginBottom: 12,
                  display: 'flex',
                  gap: 8,
                  alignItems: 'flex-start',
                  flexDirection: turn.role === 'user' ? 'row-reverse' : 'row',
                }}
              >
                <Avatar
                  size="small"
                  icon={turn.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  style={{ backgroundColor: turn.role === 'user' ? '#3750ed' : '#a064f3', flexShrink: 0 }}
                />
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '8px 12px',
                    borderRadius: 8,
                    background: turn.role === 'user'
                      ? (isDark ? '#1f2937' : '#e7e7f1')
                      : (isDark ? '#2d3748' : '#f5f5f5'),
                  }}
                >
                  <Typography.Text style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
                    {turn.text}
                  </Typography.Text>
                  {turn.citations && turn.citations.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        Sources:
                      </Typography.Text>
                      <div style={{ marginTop: 4 }}>
                        {turn.citations.map((c) => (
                          <Tag
                            key={c.id}
                            style={{ cursor: 'pointer', fontSize: 11 }}
                            onClick={() => {
                              setOpen(false);
                              navigate('/knowledge-base');
                            }}
                          >
                            {c.title}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {askMutation.isPending && (
              <div style={{ textAlign: 'center', padding: 16 }}>
                <Spin size="small" /> <Typography.Text type="secondary">Thinking…</Typography.Text>
              </div>
            )}
          </div>

          <Space.Compact style={{ marginTop: 8, width: '100%' }}>
            <Input
              placeholder="Ask a question…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={handleSend}
              disabled={askMutation.isPending}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              loading={askMutation.isPending}
            />
          </Space.Compact>
        </Card>
      )}
    </>
  );
};

export default KbChatWidget;

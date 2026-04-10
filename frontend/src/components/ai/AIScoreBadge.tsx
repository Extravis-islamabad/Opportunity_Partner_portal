import React from 'react';
import { Tag, Tooltip } from 'antd';
import { ThunderboltFilled } from '@ant-design/icons';

interface AIScoreBadgeProps {
  score: number | null | undefined;
  reasoning?: string | null;
  size?: 'small' | 'default';
}

const getColor = (score: number): string => {
  if (score >= 70) return 'green';
  if (score >= 40) return 'gold';
  return 'red';
};

const AIScoreBadge: React.FC<AIScoreBadgeProps> = ({ score, reasoning, size = 'default' }) => {
  if (score === null || score === undefined) {
    return (
      <Tooltip title="AI scoring pending">
        <Tag color="default" style={{ fontSize: size === 'small' ? 11 : 12 }}>
          <ThunderboltFilled /> —
        </Tag>
      </Tooltip>
    );
  }

  const color = getColor(score);
  const tag = (
    <Tag color={color} style={{ fontSize: size === 'small' ? 11 : 12, fontWeight: 600 }}>
      <ThunderboltFilled /> AI {score}
    </Tag>
  );

  if (reasoning) {
    return (
      <Tooltip title={reasoning} placement="top">
        {tag}
      </Tooltip>
    );
  }
  return tag;
};

export default AIScoreBadge;

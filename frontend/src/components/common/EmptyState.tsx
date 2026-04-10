import React from 'react';
import { Empty, Typography } from 'antd';

interface EmptyStateProps {
  title?: string;
  description?: string;
  illustration?: React.ReactNode;
  action?: React.ReactNode;
}

/**
 * Inline SVG illustration used when no custom illustration is passed.
 * Uses `currentColor` so it naturally inherits the active Ant theme colors.
 */
const DefaultIllustration: React.FC = () => (
  <svg width="120" height="96" viewBox="0 0 120 96" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="14" y="22" width="92" height="58" rx="6" stroke="currentColor" strokeWidth="2" opacity="0.35" />
    <rect x="24" y="34" width="52" height="6" rx="2" fill="currentColor" opacity="0.25" />
    <rect x="24" y="46" width="72" height="4" rx="2" fill="currentColor" opacity="0.18" />
    <rect x="24" y="56" width="60" height="4" rx="2" fill="currentColor" opacity="0.18" />
    <circle cx="90" cy="22" r="10" fill="currentColor" opacity="0.2" />
    <path d="M86 22 L90 26 L96 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.7" />
  </svg>
);

const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'Nothing here yet',
  description,
  illustration,
  action,
}) => {
  return (
    <div style={{ padding: '48px 16px', textAlign: 'center' }}>
      <Empty
        image={
          <div style={{ color: 'var(--ant-color-primary, #1a237e)', display: 'inline-flex' }}>
            {illustration ?? <DefaultIllustration />}
          </div>
        }
        imageStyle={{ height: 96 }}
        description={
          <div>
            <Typography.Title level={5} style={{ marginBottom: 4 }}>{title}</Typography.Title>
            {description && (
              <Typography.Text type="secondary">{description}</Typography.Text>
            )}
          </div>
        }
      >
        {action}
      </Empty>
    </div>
  );
};

export default EmptyState;

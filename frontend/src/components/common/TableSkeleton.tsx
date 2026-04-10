import React from 'react';
import { Skeleton } from 'antd';

interface TableSkeletonProps {
  rows?: number;
}

const TableSkeleton: React.FC<TableSkeletonProps> = ({ rows = 6 }) => {
  return (
    <div style={{ padding: '12px 0' }}>
      <Skeleton active paragraph={{ rows, width: '100%' }} title={{ width: '30%' }} />
    </div>
  );
};

export default TableSkeleton;

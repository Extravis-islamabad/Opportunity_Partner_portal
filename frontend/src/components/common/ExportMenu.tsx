import React, { useState } from 'react';
import { Button, Dropdown, message } from 'antd';
import { DownloadOutlined, FilePdfOutlined, FileExcelOutlined } from '@ant-design/icons';
import type { AxiosResponse } from 'axios';

type ExportFetcher = () => Promise<AxiosResponse<Blob>>;

interface ExportMenuProps {
  /** Async function that returns a PDF blob. Omit to hide the PDF option. */
  pdf?: ExportFetcher;
  /** Async function that returns an XLSX blob. Omit to hide the Excel option. */
  xlsx?: ExportFetcher;
  /** Filename prefix used for downloads (without extension). Default: "export" */
  filenamePrefix?: string;
  /** Button label. Default: "Export" */
  label?: string;
  disabled?: boolean;
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

const ExportMenu: React.FC<ExportMenuProps> = ({
  pdf,
  xlsx,
  filenamePrefix = 'export',
  label = 'Export',
  disabled = false,
}) => {
  const [busy, setBusy] = useState(false);

  const runExport = async (fetcher: ExportFetcher, ext: 'pdf' | 'xlsx') => {
    try {
      setBusy(true);
      const res = await fetcher();
      const timestamp = new Date().toISOString().slice(0, 10);
      triggerDownload(res.data, `${filenamePrefix}-${timestamp}.${ext}`);
      void message.success(`${ext.toUpperCase()} export ready`);
    } catch {
      void message.error(`Failed to export ${ext.toUpperCase()}`);
    } finally {
      setBusy(false);
    }
  };

  const items = [
    ...(pdf
      ? [
          {
            key: 'pdf',
            icon: <FilePdfOutlined />,
            label: 'Export as PDF',
            onClick: () => void runExport(pdf, 'pdf'),
          },
        ]
      : []),
    ...(xlsx
      ? [
          {
            key: 'xlsx',
            icon: <FileExcelOutlined />,
            label: 'Export as Excel',
            onClick: () => void runExport(xlsx, 'xlsx'),
          },
        ]
      : []),
  ];

  if (items.length === 0) return null;

  return (
    <Dropdown menu={{ items }} disabled={disabled || busy}>
      <Button icon={<DownloadOutlined />} loading={busy}>
        {label}
      </Button>
    </Dropdown>
  );
};

export default ExportMenu;

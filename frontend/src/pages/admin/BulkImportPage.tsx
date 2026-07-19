import React, { useState } from 'react';
import { Tabs, Card, Button, Upload, Space, Typography, Result, Alert, Table, message } from 'antd';
import { DownloadOutlined, UploadOutlined, ImportOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import type { AxiosResponse } from 'axios';
import type { AxiosError } from 'axios';
import { bulkImportApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { BulkImportResult, ErrorResponse } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const { Text, Paragraph } = Typography;

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

type TemplateFetcher = () => Promise<AxiosResponse<Blob>>;
type ImportFetcher = (file: File) => Promise<AxiosResponse<BulkImportResult>>;

interface ImportPanelProps {
  templateFetcher: TemplateFetcher;
  importFetcher: ImportFetcher;
  entityLabel: string;
  columnsHint: string;
}

interface FailedRow {
  row: number;
  error: string;
}

const failedColumns: ColumnsType<FailedRow> = [
  { title: 'Row', dataIndex: 'row', key: 'row', width: 100 },
  { title: 'Error', dataIndex: 'error', key: 'error' },
];

const ImportPanel: React.FC<ImportPanelProps> = ({
  templateFetcher,
  importFetcher,
  entityLabel,
  columnsHint,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [downloading, setDownloading] = useState(false);

  const importMut = useMutation<BulkImportResult, AxiosError<ErrorResponse>, File>({
    mutationFn: async (f: File) => {
      const res = await importFetcher(f);
      return res.data;
    },
    onSuccess: (result) => {
      void message.success(`${result.succeeded} of ${result.processed} rows imported`);
    },
    onError: (err) => {
      void message.error(err.response?.data?.message ?? 'Import failed');
    },
  });

  const handleDownloadTemplate = async () => {
    try {
      setDownloading(true);
      const res = await templateFetcher();
      triggerDownload(res.data, `${entityLabel}_import_template.xlsx`);
    } catch {
      void message.error('Failed to download template');
    } finally {
      setDownloading(false);
    }
  };

  const result = importMut.data;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card size="small" title={`Expected columns for ${entityLabel}`}>
        <Paragraph style={{ marginBottom: 8 }}>
          <Text type="secondary">{columnsHint}</Text>
        </Paragraph>
        <Button
          icon={<DownloadOutlined />}
          onClick={() => void handleDownloadTemplate()}
          loading={downloading}
        >
          Download Template
        </Button>
      </Card>

      <Card size="small" title="Upload workbook">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Upload
            accept=".xlsx"
            maxCount={1}
            beforeUpload={(f) => {
              setFile(f);
              return false;
            }}
            onRemove={() => setFile(null)}
          >
            <Button icon={<UploadOutlined />}>Select .xlsx file</Button>
          </Upload>
          {file && <Text type="secondary">Selected: {file.name}</Text>}
          <Button
            type="primary"
            icon={<ImportOutlined />}
            disabled={!file}
            loading={importMut.isPending}
            onClick={() => file && importMut.mutate(file)}
          >
            Import
          </Button>
        </Space>
      </Card>

      {result && (
        <Card size="small">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Result
              status="success"
              title={`${result.succeeded} of ${result.processed} rows imported`}
              subTitle="Refresh the relevant page to see the imported records."
            />
            {result.failed.length > 0 && (
              <>
                <Alert
                  type="warning"
                  showIcon
                  message={`${result.failed.length} row${result.failed.length === 1 ? '' : 's'} failed to import`}
                />
                <Table<FailedRow>
                  size="small"
                  rowKey="row"
                  columns={failedColumns}
                  dataSource={result.failed}
                  pagination={false}
                />
              </>
            )}
          </Space>
        </Card>
      )}
    </Space>
  );
};

const BulkImportPage: React.FC = () => {
  return (
    <>
      <PageHeader
        title="Bulk Import"
        subtitle="Import companies or opportunities from an .xlsx workbook (superadmin only)"
      />
      <Tabs
        defaultActiveKey="companies"
        items={[
          {
            key: 'companies',
            label: 'Companies',
            children: (
              <ImportPanel
                entityLabel="companies"
                columnsHint="Company Name, Country, City, Industry, Contact Email, Channel Manager Email"
                templateFetcher={() => bulkImportApi.companiesTemplate()}
                importFetcher={(file) => bulkImportApi.importCompanies(file)}
              />
            ),
          },
          {
            key: 'opportunities',
            label: 'Opportunities',
            children: (
              <ImportPanel
                entityLabel="opportunities"
                columnsHint="S.No, Customer, Partner, Extravis Team, City, Country, Industry, Progress, Product, Price, Time Frame"
                templateFetcher={() => bulkImportApi.opportunitiesTemplate()}
                importFetcher={(file) => bulkImportApi.importOpportunities(file)}
              />
            ),
          },
        ]}
      />
    </>
  );
};

export default BulkImportPage;

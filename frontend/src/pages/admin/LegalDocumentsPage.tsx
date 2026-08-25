import React, { useState } from 'react';
import {
  Card, Button, Alert, Space, Modal, Input, Select, Typography, Tag, message, Empty, Skeleton,
} from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { legalApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import dayjs from 'dayjs';

/**
 * The partner agreement and the NDA that are currently in force.
 *
 * Publishing a new version asks every partner in the programme to accept
 * again, and blocks them from registering business until they do — so it is a
 * deliberate act with a confirmation, not an edit box. Existing versions are
 * never changed: somebody accepted that text, and rewriting it would make
 * their acceptance a record of something that never existed.
 */
const LegalDocumentsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [publishing, setPublishing] = useState(false);
  const [kind, setKind] = useState('partner_agreement');
  const [version, setVersion] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['legal-documents'],
    queryFn: async () => (await legalApi.documents()).data,
  });

  const publishMut = useMutation({
    mutationFn: () => legalApi.publish({ kind, version: version.trim(), title: title.trim(), body }),
    onSuccess: () => {
      setPublishing(false);
      setVersion('');
      setTitle('');
      setBody('');
      void queryClient.invalidateQueries({ queryKey: ['legal-documents'] });
      void message.success('Published — every partner will be asked to accept it');
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { message?: string } } })?.response?.data?.message;
      void message.error(detail ?? 'Could not publish the document');
    },
  });

  if (error) return <Alert type="error" message="Failed to load legal documents" showIcon />;

  return (
    <>
      <PageHeader
        title="Legal Documents"
        subtitle="The partner agreement and NDA currently in force"
        extra={<Button type="primary" onClick={() => setPublishing(true)}>Publish new version</Button>}
      />

      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="Publishing a new version asks everybody again"
        description="Partners cannot register opportunities or deals until they accept the current version. Existing acceptances are kept as the record of what was agreed and when — they simply stop satisfying the requirement."
      />

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : (data ?? []).length === 0 ? (
        <Card>
          <Empty description="Nothing published yet — partners are not being asked to accept anything" />
        </Card>
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {data!.map((doc) => (
            <Card
              key={doc.id}
              title={
                <Space>
                  <span>{doc.title}</span>
                  <Tag color="blue">{doc.label}</Tag>
                  <Tag>Version {doc.version}</Tag>
                </Space>
              }
              extra={
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  published {dayjs(doc.published_at).format('MMM D, YYYY')}
                </Typography.Text>
              }
            >
              <div style={{ maxHeight: 220, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                <Typography.Text>{doc.body}</Typography.Text>
              </div>
            </Card>
          ))}
        </Space>
      )}

      <Modal
        title="Publish a new version"
        open={publishing}
        onCancel={() => setPublishing(false)}
        onOk={() => publishMut.mutate()}
        confirmLoading={publishMut.isPending}
        okText="Publish"
        okButtonProps={{ disabled: !version.trim() || !title.trim() || !body.trim() }}
        width={720}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Select
            style={{ width: '100%' }}
            value={kind}
            onChange={setKind}
            options={[
              { value: 'partner_agreement', label: 'Partner Agreement' },
              { value: 'nda', label: 'Non-Disclosure Agreement' },
            ]}
          />
          <Input
            placeholder="Version — e.g. 2026-08 or 3.1"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            maxLength={50}
          />
          <Input
            placeholder="Title as it appears to partners"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={255}
          />
          <Input.TextArea
            rows={10}
            placeholder="The full text partners will read and accept"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            A version can only be published once. To correct a mistake, publish
            a new version rather than replacing this one.
          </Typography.Text>
        </Space>
      </Modal>
    </>
  );
};

export default LegalDocumentsPage;

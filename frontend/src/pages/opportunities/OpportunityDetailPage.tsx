import React, { useState } from 'react';
import { Descriptions, Card, Tag, Skeleton, Alert, Empty, Button, Space, Row, Col, Modal, Input, Checkbox, Upload, List, message, Typography } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { opportunitiesApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import { StarFilled, WarningOutlined, UploadOutlined, FileOutlined } from '@ant-design/icons';
import { AxiosError } from 'axios';
import type { ErrorResponse, OpportunityResponse } from '@/types';
import dayjs from 'dayjs';

const statusColors: Record<string, string> = {
  draft: 'default', pending_review: 'orange', under_review: 'processing',
  approved: 'green', rejected: 'red', removed: 'default',
};

const OpportunityDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const oppId = Number(id);
  const isAdmin = user?.role === 'admin';

  const [rejectModal, setRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [approveModal, setApproveModal] = useState(false);
  const [preferredPartner, setPreferredPartner] = useState(false);
  const [noteModal, setNoteModal] = useState(false);
  const [noteText, setNoteText] = useState('');

  const { data: opp, isLoading, error } = useQuery({
    queryKey: ['opportunity', oppId],
    queryFn: async () => { const res = await opportunitiesApi.get(oppId); return res.data; },
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['opportunity', oppId] });

  const submitMut = useMutation({ mutationFn: () => opportunitiesApi.submit(oppId), onSuccess: () => { invalidate(); void message.success('Submitted'); } });
  const approveMut = useMutation({
    mutationFn: () => opportunitiesApi.approve(oppId, preferredPartner),
    onSuccess: () => { setApproveModal(false); invalidate(); void message.success('Approved'); },
  });
  const rejectMut = useMutation({
    mutationFn: () => opportunitiesApi.reject(oppId, rejectReason),
    onSuccess: () => { setRejectModal(false); invalidate(); void message.success('Rejected'); },
  });
  const reviewMut = useMutation({ mutationFn: () => opportunitiesApi.markUnderReview(oppId), onSuccess: invalidate });
  const removeMut = useMutation({
    mutationFn: () => opportunitiesApi.remove(oppId),
    onSuccess: () => { void message.success('Removed'); navigate('/opportunities'); },
  });
  const noteMut = useMutation({
    mutationFn: () => opportunitiesApi.addNote(oppId, noteText),
    onSuccess: () => { setNoteModal(false); invalidate(); void message.success('Note added'); },
  });

  if (error) return <Alert type="error" message="Failed to load opportunity" showIcon />;
  if (isLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
  if (!opp) return <Empty description="Opportunity not found" />;

  const canEdit = !isAdmin && (opp.status === 'draft' || opp.status === 'rejected');
  const canSubmit = !isAdmin && (opp.status === 'draft' || opp.status === 'rejected');
  const canReview = isAdmin && opp.status === 'pending_review';
  const canApproveReject = isAdmin && (opp.status === 'pending_review' || opp.status === 'under_review');

  return (
    <>
      <PageHeader
        title={opp.name}
        breadcrumbs={[{ label: 'Opportunities', path: '/opportunities' }, { label: opp.name }]}
        extra={
          <Space>
            {canEdit && <Button onClick={() => navigate(`/opportunities/${oppId}/edit`)}>Edit</Button>}
            {canSubmit && <Button type="primary" loading={submitMut.isPending} onClick={() => submitMut.mutate()}>Submit for Review</Button>}
            {canReview && <Button type="primary" loading={reviewMut.isPending} onClick={() => reviewMut.mutate()}>Mark Under Review</Button>}
            {canApproveReject && <Button type="primary" style={{ background: '#52c41a' }} onClick={() => setApproveModal(true)}>Approve</Button>}
            {canApproveReject && <Button danger onClick={() => setRejectModal(true)}>Reject</Button>}
            {isAdmin && <Button danger onClick={() => { Modal.confirm({ title: 'Remove this opportunity?', onOk: () => removeMut.mutate() }); }}>Remove</Button>}
            {isAdmin && <Button onClick={() => setNoteModal(true)}>Add Note</Button>}
          </Space>
        }
      />

      {opp.multi_partner_alert && (
        <Alert type="warning" icon={<WarningOutlined />} message="Multi-Partner Alert"
          description="Another partner has already submitted an opportunity for this customer. Admins have been notified."
          showIcon style={{ marginBottom: 16 }} />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card>
            <Descriptions bordered column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="Status">
                <Space><Tag color={statusColors[opp.status] ?? 'default'}>{opp.status.replace(/_/g, ' ').toUpperCase()}</Tag>
                  {opp.preferred_partner && <Tag color="gold" icon={<StarFilled />}>Preferred Partner</Tag>}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Worth">${Number(opp.worth).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="Customer">{opp.customer_name}</Descriptions.Item>
              <Descriptions.Item label="Company">{opp.company_name}</Descriptions.Item>
              <Descriptions.Item label="Region">{opp.region}</Descriptions.Item>
              <Descriptions.Item label="Country">{opp.country}</Descriptions.Item>
              <Descriptions.Item label="City">{opp.city}</Descriptions.Item>
              <Descriptions.Item label="Closing Date">{dayjs(opp.closing_date).format('MMM D, YYYY')}</Descriptions.Item>
              <Descriptions.Item label="Submitted By">{opp.submitted_by_name}</Descriptions.Item>
              {opp.submitted_at && <Descriptions.Item label="Submitted At">{dayjs(opp.submitted_at).format('MMM D, YYYY HH:mm')}</Descriptions.Item>}
              {opp.reviewer_name && <Descriptions.Item label="Reviewed By">{opp.reviewer_name}</Descriptions.Item>}
              {opp.reviewed_at && <Descriptions.Item label="Reviewed At">{dayjs(opp.reviewed_at).format('MMM D, YYYY HH:mm')}</Descriptions.Item>}
            </Descriptions>
          </Card>

          <Card title="Requirements" style={{ marginTop: 16 }}>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{opp.requirements}</Typography.Paragraph>
          </Card>

          {opp.rejection_reason && (
            <Card title="Rejection Reason" style={{ marginTop: 16 }}>
              <Alert type="error" message={opp.rejection_reason} />
            </Card>
          )}

          {isAdmin && opp.internal_notes && (
            <Card title="Internal Notes (Admin Only)" style={{ marginTop: 16 }}>
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{opp.internal_notes}</Typography.Paragraph>
            </Card>
          )}
        </Col>

        <Col xs={24} lg={8}>
          <Card title="Documents">
            {opp.documents.length > 0 ? (
              <List dataSource={opp.documents} renderItem={(doc) => (
                <List.Item>
                  <a href={doc.file_url} target="_blank" rel="noopener noreferrer">
                    <FileOutlined style={{ marginRight: 8 }} />{doc.file_name}
                  </a>
                </List.Item>
              )} />
            ) : <Empty description="No documents" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            {(canEdit || opp.status === 'draft') && (
              <Upload
                customRequest={async ({ file, onSuccess, onError }) => {
                  try {
                    await opportunitiesApi.uploadDocument(oppId, file as File);
                    invalidate();
                    onSuccess?.(null);
                    void message.success('Document uploaded');
                  } catch (e) { onError?.(e as Error); }
                }}
                showUploadList={false}
              >
                <Button icon={<UploadOutlined />} style={{ marginTop: 8 }}>Upload Document</Button>
              </Upload>
            )}
          </Card>
        </Col>
      </Row>

      <Modal title="Approve Opportunity" open={approveModal} onCancel={() => setApproveModal(false)}
        onOk={() => approveMut.mutate()} confirmLoading={approveMut.isPending}>
        <Checkbox checked={preferredPartner} onChange={(e) => setPreferredPartner(e.target.checked)}>
          Tag as Preferred Partner
        </Checkbox>
      </Modal>

      <Modal title="Reject Opportunity" open={rejectModal} onCancel={() => setRejectModal(false)}
        onOk={() => rejectMut.mutate()} confirmLoading={rejectMut.isPending}
        okButtonProps={{ disabled: !rejectReason.trim() }}>
        <Input.TextArea rows={4} placeholder="Rejection reason (required)" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} maxLength={1000} showCount />
      </Modal>

      <Modal title="Add Internal Note" open={noteModal} onCancel={() => setNoteModal(false)}
        onOk={() => noteMut.mutate()} confirmLoading={noteMut.isPending}
        okButtonProps={{ disabled: !noteText.trim() }}>
        <Input.TextArea rows={4} placeholder="Internal note..." value={noteText} onChange={(e) => setNoteText(e.target.value)} />
      </Modal>
    </>
  );
};

export default OpportunityDetailPage;

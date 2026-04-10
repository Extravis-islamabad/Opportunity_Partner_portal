import React, { useState } from 'react';
import { Card, Row, Col, Button, Tag, Skeleton, Alert, Empty, Modal, Form, Input, Select, InputNumber, Space, Table, Upload, message } from 'antd';
import { PlusOutlined, PlayCircleOutlined, TrophyOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { lmsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { CourseResponse, EnrollmentResponse } from '@/types';

const LmsPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const queryClient = useQueryClient();
  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();
  const [certFile, setCertFile] = useState<File | null>(null);

  const { data: courses, isLoading, error } = useQuery({
    queryKey: ['lms-courses'],
    queryFn: async () => { const res = await lmsApi.listCourses({ page: 1, page_size: 50 }); return res.data; },
  });

  const { data: myEnrollments } = useQuery({
    queryKey: ['my-enrollments'],
    queryFn: async () => { const res = await lmsApi.getMyEnrollments(); return res.data; },
    enabled: !isAdmin,
  });

  const { data: certRequests } = useQuery({
    queryKey: ['cert-requests'],
    queryFn: async () => { const res = await lmsApi.listCertificateRequests({ page: 1, page_size: 50 }); return res.data; },
    enabled: isAdmin,
  });

  const createMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => lmsApi.createCourse(data),
    onSuccess: () => { setCreateModal(false); createForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['lms-courses'] }); void message.success('Course created'); },
  });

  const enrollMut = useMutation({
    mutationFn: (courseId: number) => lmsApi.enroll(courseId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] }); void message.success('Enrolled'); },
  });

  const completeMut = useMutation({
    mutationFn: (enrollmentId: number) => lmsApi.updateEnrollment(enrollmentId, { status: 'completed' }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] }); void message.success('Marked complete'); },
  });

  const certReqMut = useMutation({
    mutationFn: (enrollmentId: number) => lmsApi.requestCertificate(enrollmentId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] }); void message.success('Certificate requested'); },
  });

  const issueCertMut = useMutation({
    mutationFn: ({ enrollmentId, file }: { enrollmentId: number; file: File }) => lmsApi.issueCertificate(enrollmentId, file),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['cert-requests'] }); void message.success('Certificate issued'); },
  });

  const isEnrolled = (courseId: number) => myEnrollments?.some(e => e.course_id === courseId);
  const getEnrollment = (courseId: number) => myEnrollments?.find(e => e.course_id === courseId);

  if (error) return <Alert type="error" message="Failed to load courses" showIcon />;

  return (
    <>
      <PageHeader
        title={isAdmin ? 'LMS Management' : 'Training Courses'}
        subtitle={`${courses?.items.length ?? 0} courses available`}
        extra={isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>Create Course</Button>}
      />

      {isLoading ? <Skeleton active /> : (
        courses && courses.items.length > 0 ? (
          <Row gutter={[16, 16]}>
            {courses.items.map((course: CourseResponse) => {
              const enrollment = getEnrollment(course.id);
              return (
                <Col xs={24} sm={12} lg={8} key={course.id}>
                  <Card
                    title={course.title}
                    extra={<Tag color={course.status === 'published' ? 'green' : 'default'}>{course.status}</Tag>}
                    actions={!isAdmin ? [
                      !isEnrolled(course.id) ? (
                        <Button type="link" icon={<PlayCircleOutlined />} onClick={() => enrollMut.mutate(course.id)} key="enroll">Enroll</Button>
                      ) : enrollment?.status === 'completed' ? (
                        !enrollment.certificate_requested ? (
                          <Button type="link" icon={<TrophyOutlined />} onClick={() => certReqMut.mutate(enrollment.id)} key="cert">Request Certificate</Button>
                        ) : enrollment.certificate_url ? (
                          <a href={enrollment.certificate_url} target="_blank" rel="noopener noreferrer" key="dl">Download Certificate</a>
                        ) : (
                          <Tag color="orange" key="pending">Certificate Pending</Tag>
                        )
                      ) : (
                        <Button type="link" onClick={() => completeMut.mutate(enrollment!.id)} key="complete">Mark Complete</Button>
                      ),
                    ] : undefined}
                  >
                    <p>{course.description || 'No description'}</p>
                    {course.duration_hours && <p>Duration: {course.duration_hours}h</p>}
                    <p>Enrolled: {course.enrollment_count} | Completed: {course.completion_count}</p>
                    {enrollment && (
                      <Tag color={enrollment.status === 'completed' ? 'green' : enrollment.status === 'in_progress' ? 'blue' : 'default'}>
                        {enrollment.status.toUpperCase()}
                      </Tag>
                    )}
                  </Card>
                </Col>
              );
            })}
          </Row>
        ) : <Empty description="No courses available" />
      )}

      {isAdmin && certRequests && certRequests.items.length > 0 && (
        <Card title="Pending Certificate Requests" style={{ marginTop: 24 }}>
          <Table
            dataSource={certRequests.items}
            rowKey="id"
            columns={[
              { title: 'Partner', dataIndex: 'user_name', key: 'user' },
              { title: 'Course', dataIndex: 'course_title', key: 'course' },
              {
                title: 'Action', key: 'action', render: (_, record: EnrollmentResponse) => (
                  <Space>
                    <Upload beforeUpload={(file) => { setCertFile(file); return false; }} maxCount={1} showUploadList={false}>
                      <Button icon={<UploadOutlined />} size="small">Select PDF</Button>
                    </Upload>
                    <Button type="primary" size="small" disabled={!certFile}
                      onClick={() => certFile && issueCertMut.mutate({ enrollmentId: record.id, file: certFile })}>
                      Issue Certificate
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      )}

      <Modal title="Create Course" open={createModal} onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()} confirmLoading={createMut.isPending}>
        <Form form={createForm} layout="vertical" onFinish={(v) => createMut.mutate({ ...v, modules_json: [] })}>
          <Form.Item name="title" label="Title" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="duration_hours" label="Duration (hours)"><InputNumber min={1} /></Form.Item>
          <Form.Item name="status" label="Status" initialValue="draft">
            <Select options={[{ value: 'draft', label: 'Draft' }, { value: 'published', label: 'Published' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default LmsPage;

import React, { useState } from 'react';
import {
  Card,
  Row,
  Col,
  Button,
  Tag,
  Skeleton,
  Alert,
  Empty,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  Progress,
  Typography,
  message,
} from 'antd';
import {
  PlusOutlined,
  PlayCircleOutlined,
  TrophyOutlined,
  ClockCircleOutlined,
  ReadOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { lmsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/components/common/PageHeader';
import type { CourseResponse, EnrollmentResponse } from '@/types';

const BRAND = {
  royal500: '#3750ed',
  royal400: '#4961f1',
  royal100: '#b4b6f7',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  violet500: '#a064f3',
  violet600: '#7a2280',
  violet100: '#f0e6ff',
};

const LmsPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'admin';
  const queryClient = useQueryClient();
  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();

  const { data: courses, isLoading, error } = useQuery({
    queryKey: ['lms-courses'],
    queryFn: async () => (await lmsApi.listCourses({ page: 1, page_size: 50 })).data,
  });

  const { data: myEnrollments } = useQuery({
    queryKey: ['my-enrollments'],
    queryFn: async () => (await lmsApi.getMyEnrollments()).data,
    enabled: !isAdmin,
  });

  const createMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => lmsApi.createCourse(data),
    onSuccess: (res) => {
      setCreateModal(false);
      createForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['lms-courses'] });
      void message.success('Course created — add lessons to start');
      navigate(`/lms/courses/${res.data.id}`);
    },
    onError: () => void message.error('Failed to create course'),
  });

  const enrollMut = useMutation({
    mutationFn: (courseId: number) => lmsApi.enroll(courseId),
    onSuccess: (_, courseId) => {
      void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] });
      void message.success('Enrolled');
      navigate(`/lms/courses/${courseId}`);
    },
    onError: () => void message.error('Failed to enroll'),
  });

  const getEnrollment = (courseId: number): EnrollmentResponse | undefined =>
    myEnrollments?.find((e) => e.course_id === courseId);

  const calcProgress = (course: CourseResponse, enrollment?: EnrollmentResponse): number => {
    if (!enrollment) return 0;
    if (enrollment.status === 'completed') return 100;
    const moduleCount = course.modules_json?.length ?? 0;
    if (moduleCount === 0) return 0;
    const completed = Object.values(enrollment.progress_json ?? {}).filter(Boolean).length;
    return Math.round((completed / moduleCount) * 100);
  };

  if (error) return <Alert type="error" message="Failed to load courses" showIcon />;

  return (
    <>
      <PageHeader
        title={isAdmin ? 'LMS Management' : 'Training Courses'}
        subtitle={`${courses?.items.length ?? 0} courses available`}
        extra={
          isAdmin && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
              Create Course
            </Button>
          )
        }
      />

      {isLoading ? (
        <Skeleton active />
      ) : courses && courses.items.length > 0 ? (
        <Row gutter={[16, 16]}>
          {courses.items.map((course: CourseResponse) => {
            const enrollment = getEnrollment(course.id);
            const progress = calcProgress(course, enrollment);
            const moduleCount = course.modules_json?.length ?? 0;
            const isCompleted = enrollment?.status === 'completed';

            return (
              <Col xs={24} sm={12} lg={8} key={course.id}>
                <Card
                  hoverable
                  bordered={false}
                  onClick={() => navigate(`/lms/courses/${course.id}`)}
                  style={{
                    borderRadius: 14,
                    overflow: 'hidden',
                    height: '100%',
                    boxShadow: '0 4px 12px rgba(28, 28, 58, 0.06)',
                  }}
                  styles={{ body: { padding: 0 } }}
                >
                  {/* Brand gradient header */}
                  <div
                    style={{
                      height: 88,
                      background: isCompleted
                        ? `linear-gradient(135deg, #10b981 0%, ${BRAND.violet500} 100%)`
                        : `linear-gradient(135deg, ${BRAND.royal500} 0%, ${BRAND.violet500} 100%)`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      position: 'relative',
                    }}
                  >
                    <ReadOutlined style={{ fontSize: 38, color: '#fff', opacity: 0.9 }} />
                    {isCompleted && (
                      <Tag
                        color="green"
                        style={{
                          position: 'absolute',
                          top: 12,
                          right: 12,
                          background: 'rgba(255,255,255,0.95)',
                          color: '#10b981',
                          border: 'none',
                          fontWeight: 600,
                        }}
                      >
                        <TrophyOutlined /> Completed
                      </Tag>
                    )}
                    {course.status === 'draft' && (
                      <Tag
                        style={{
                          position: 'absolute',
                          top: 12,
                          right: 12,
                          background: 'rgba(255,255,255,0.95)',
                          color: '#6b7280',
                          border: 'none',
                          fontWeight: 600,
                        }}
                      >
                        DRAFT
                      </Tag>
                    )}
                  </div>

                  {/* Body */}
                  <div style={{ padding: 18 }}>
                    <Typography.Title level={5} style={{ margin: '0 0 6px', color: BRAND.navy }}>
                      {course.title}
                    </Typography.Title>
                    <Typography.Paragraph
                      type="secondary"
                      ellipsis={{ rows: 2 }}
                      style={{ marginBottom: 12, fontSize: 13, minHeight: 36 }}
                    >
                      {course.description || 'No description'}
                    </Typography.Paragraph>

                    {/* Meta row */}
                    <div style={{ display: 'flex', gap: 14, marginBottom: 12, fontSize: 12, color: '#6b7280' }}>
                      <span>
                        <ReadOutlined style={{ marginRight: 4 }} />
                        {moduleCount} {moduleCount === 1 ? 'lesson' : 'lessons'}
                      </span>
                      {course.duration_hours && (
                        <span>
                          <ClockCircleOutlined style={{ marginRight: 4 }} />
                          {course.duration_hours}h
                        </span>
                      )}
                      <span>
                        <PlayCircleOutlined style={{ marginRight: 4 }} />
                        {course.enrollment_count} enrolled
                      </span>
                    </div>

                    {/* Progress bar (partner only) */}
                    {!isAdmin && enrollment && (
                      <div style={{ marginBottom: 12 }}>
                        <Progress
                          percent={progress}
                          strokeColor={{ '0%': BRAND.royal400, '100%': BRAND.violet500 }}
                          size="small"
                          format={(p) => `${p}%`}
                        />
                      </div>
                    )}

                    {/* Action button */}
                    {isAdmin ? (
                      <Button
                        type="primary"
                        block
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/lms/courses/${course.id}`);
                        }}
                      >
                        Manage lessons
                      </Button>
                    ) : !enrollment ? (
                      <Button
                        type="primary"
                        block
                        icon={<PlayCircleOutlined />}
                        loading={enrollMut.isPending}
                        onClick={(e) => {
                          e.stopPropagation();
                          enrollMut.mutate(course.id);
                        }}
                      >
                        Enroll & start
                      </Button>
                    ) : isCompleted ? (
                      enrollment.certificate_url ? (
                        <Button
                          block
                          icon={<TrophyOutlined />}
                          href={enrollment.certificate_url}
                          target="_blank"
                          onClick={(e) => e.stopPropagation()}
                          style={{ background: BRAND.violet100, color: BRAND.violet600, border: 'none', fontWeight: 600 }}
                        >
                          Download certificate
                        </Button>
                      ) : (
                        <Button block disabled icon={<CheckCircleOutlined />}>
                          Completed
                        </Button>
                      )
                    ) : (
                      <Button
                        type="primary"
                        block
                        icon={<PlayCircleOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/lms/courses/${course.id}`);
                        }}
                      >
                        Continue learning
                      </Button>
                    )}
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>
      ) : (
        <Empty description="No courses available" />
      )}

      <Modal
        title="Create Course"
        open={createModal}
        onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMut.isPending}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={(v) => createMut.mutate({ ...v, modules_json: [] })}
        >
          <Form.Item name="title" label="Title" rules={[{ required: true }]}>
            <Input placeholder="e.g. Cybersecurity Specialist" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} placeholder="What will partners learn from this course?" />
          </Form.Item>
          <Form.Item name="duration_hours" label="Duration (hours)">
            <InputNumber min={1} max={200} />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="draft">
            <Select
              options={[
                { value: 'draft', label: 'Draft (hidden from partners)' },
                { value: 'published', label: 'Published (visible to partners)' },
              ]}
            />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="After creating the course you'll be taken to its detail page where you can add lessons (videos, PDFs, quizzes)."
            style={{ marginTop: 8 }}
          />
        </Form>
      </Modal>
    </>
  );
};

export default LmsPage;

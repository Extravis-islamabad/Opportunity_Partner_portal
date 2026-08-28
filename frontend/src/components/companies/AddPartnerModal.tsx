import React from 'react';
import { Modal, Form, Input, message } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '@/api/endpoints';
import type { UserResponse, ErrorResponse } from '@/types';
import { AxiosError } from 'axios';

interface AddPartnerModalProps {
  open: boolean;
  companyId: number;
  companyName: string;
  onClose: () => void;
}

/**
 * Create a partner account against one company, from the company itself.
 *
 * This lives here rather than on the Users page because the Users page is
 * superadmin-only, while a channel manager may add partners to the companies
 * they manage — which is exactly what the backend allows (users.create_user
 * checks the manager's scope). Sending them to /users to do it meant the
 * route guard bounced them and nobody was ever created, so no account ever
 * got its activation email.
 *
 * Role and company are fixed here: this is the "add a partner to THIS
 * company" path, not the general user builder.
 */
const AddPartnerModal: React.FC<AddPartnerModalProps> = ({ open, companyId, companyName, onClose }) => {
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const createMut = useMutation({
    mutationFn: (values: { full_name: string; email: string; job_title?: string; phone?: string }) =>
      usersApi.create({ ...values, role: 'partner', company_id: companyId }),
    onSuccess: (res) => {
      const created = res.data as UserResponse;
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['company', companyId] });
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      // Say where the activation link went. The account is unusable until
      // that mail is acted on, so silence here reads as "nothing happened".
      void message.success(`Partner created — an activation email has been sent to ${created.email}`);
      onClose();
    },
    onError: (err: AxiosError<ErrorResponse>) =>
      void message.error(err.response?.data?.message || 'Failed to create partner'),
  });

  return (
    <Modal
      title={`Add Partner — ${companyName}`}
      open={open}
      onCancel={() => { form.resetFields(); onClose(); }}
      onOk={() => form.submit()}
      confirmLoading={createMut.isPending}
      okText="Create & Send Invite"
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={createMut.mutate}>
        <Form.Item name="full_name" label="Full Name" rules={[{ required: true, max: 255 }]}>
          <Input />
        </Form.Item>
        <Form.Item
          name="email" label="Email"
          rules={[{ required: true, type: 'email' }]}
          extra="The activation link is sent here. It expires, and a new one has to be issued if it does."
        >
          <Input />
        </Form.Item>
        <Form.Item name="job_title" label="Job Title"><Input maxLength={255} /></Form.Item>
        <Form.Item name="phone" label="Phone"><Input maxLength={50} /></Form.Item>
      </Form>
    </Modal>
  );
};

export default AddPartnerModal;

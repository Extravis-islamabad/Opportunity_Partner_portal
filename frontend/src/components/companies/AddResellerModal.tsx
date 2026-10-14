import React, { useEffect } from 'react';
import { Modal, Form, Input, Row, Col, Alert, message } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { companiesApi } from '@/api/endpoints';
import ChannelManagersSelect from '@/components/companies/ChannelManagersSelect';
import type { CompanyDetailResponse, CompanyCreateRequest, ErrorResponse } from '@/types';
import { AxiosError } from 'axios';

interface Props {
  open: boolean;
  distributor: CompanyDetailResponse;
  onClose: () => void;
}

/**
 * Add a partner company underneath a distributor, from the distributor itself.
 *
 * "Add Partner" on a distributor used to add a *user* to the distributor —
 * so someone adding a reseller got a login inside the distributor and no
 * reseller company at all. This creates the partner company with the
 * distributor as its parent, and (as every company creation does) provisions
 * its contact's account and emails them an activation link.
 */
const AddResellerModal: React.FC<Props> = ({ open, distributor, onClose }) => {
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!open) return;
    // Resellers usually sit in the distributor's market, and are looked after
    // by the same people — start from there.
    form.setFieldsValue({
      country: distributor.country,
      region: distributor.region ?? undefined,
      industry: distributor.industry,
      channel_manager_ids: distributor.channel_managers.length
        ? distributor.channel_managers.map((m) => m.id)
        : [distributor.channel_manager_id],
    });
  }, [open, distributor, form]);

  const createMut = useMutation({
    mutationFn: (values: Omit<CompanyCreateRequest, 'company_type' | 'parent_distributor_id'>) =>
      companiesApi.create({
        ...values,
        company_type: 'partner',
        parent_distributor_id: distributor.id,
      }),
    onSuccess: (res) => {
      const email = res.data.contact_email;
      switch (res.data.contact_invite) {
        case 'sent':
          void message.success(`${res.data.name} added — an activation email has been sent to ${email}`);
          break;
        case 'existing_user':
          void message.warning(`${res.data.name} added. ${email} already has an account, so no invite was sent.`);
          break;
        case 'failed':
          void message.warning(`${res.data.name} added and an account made for ${email}, but the invite email failed — re-send it from the Email Log.`);
          break;
        default:
          void message.success(`${res.data.name} added`);
      }
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['company', distributor.id] });
      void queryClient.invalidateQueries({ queryKey: ['companies'] });
      onClose();
    },
    onError: (err: AxiosError<ErrorResponse>) =>
      void message.error(err.response?.data?.message || 'Failed to add the partner company'),
  });

  return (
    <Modal
      title={`Add Partner Company under ${distributor.name}`}
      open={open}
      onCancel={() => { form.resetFields(); onClose(); }}
      onOk={() => form.submit()}
      confirmLoading={createMut.isPending}
      okText="Create Company & Send Invite"
      width={640}
      destroyOnHidden
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={`Creates a partner company that resells through ${distributor.name}, plus a portal account for its contact.`}
      />
      <Form form={form} layout="vertical" onFinish={createMut.mutate}>
        <Form.Item name="name" label="Partner Company Name" rules={[{ required: true, max: 255, message: 'Required' }]}>
          <Input placeholder="e.g. NetSoft Solutions" />
        </Form.Item>
        <Row gutter={12}>
          <Col xs={24} sm={8}>
            <Form.Item name="country" label="Country" rules={[{ required: true, max: 100, message: 'Required' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item name="region" label="Region">
              <Input placeholder="Optional" maxLength={100} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item name="city" label="City">
              <Input placeholder="Optional" maxLength={100} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="industry" label="Industry" rules={[{ required: true, max: 255, message: 'Required' }]}>
          <Input />
        </Form.Item>
        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="contact_name" label="Contact Name">
              <Input placeholder="Primary contact's full name" maxLength={255} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              name="contact_email"
              label="Contact Email"
              rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
            >
              <Input placeholder="contact@partner.com" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item
          name="channel_manager_ids"
          label="Channel Managers"
          rules={[{ required: true, type: 'array', min: 1, message: 'Choose at least one channel manager' }]}
        >
          <ChannelManagersSelect />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default AddResellerModal;

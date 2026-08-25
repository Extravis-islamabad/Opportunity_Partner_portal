import React, { useState } from 'react';
import { Card, Table, Tag, Alert, Button, Space, Modal, InputNumber, Typography, message } from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { currenciesApi } from '@/api/endpoints';
import PageHeader from '@/components/common/PageHeader';
import type { CurrencyRateInfo } from '@/types';
import dayjs from 'dayjs';

/**
 * The rates deals are converted at.
 *
 * A deal is converted once, when it is recorded, and the rate is stored on the
 * deal. So publishing a rate here changes what *future* deals are worth and
 * leaves recorded ones exactly as they were — which is the point: a report of
 * last quarter's business must not move because today's rate did.
 */
const CurrencyRatesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<CurrencyRateInfo | null>(null);
  const [rate, setRate] = useState<number | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['currencies'],
    queryFn: async () => (await currenciesApi.list()).data,
  });

  const saveMut = useMutation({
    mutationFn: (row: CurrencyRateInfo) =>
      currenciesApi.setRate(row.currency, String(rate)),
    onSuccess: () => {
      setEditing(null);
      setRate(null);
      void queryClient.invalidateQueries({ queryKey: ['currencies'] });
      void message.success('Rate published — it applies to deals recorded from now on');
    },
    onError: () => { void message.error('Could not publish the rate'); },
  });

  if (error) return <Alert type="error" message="Failed to load currencies" showIcon />;

  const anyDefault = (data?.currencies ?? []).some((c) => c.is_default);

  return (
    <>
      <PageHeader
        title="Currency Rates"
        subtitle={`Everything is reported in ${data?.reporting_currency ?? 'USD'}`}
      />

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="A new rate applies to deals recorded from now on"
        description="Each deal stores the rate it was converted at, so publishing a rate here never restates a deal that has already been recorded — last quarter's report will still say what it said."
      />

      {anyDefault && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="Some currencies are using built-in fallback rates"
          description="Nobody has published a rate for them, so deals are being converted at a default. Set the real rate below."
        />
      )}

      <Card>
        <Table
          rowKey="currency"
          loading={isLoading}
          dataSource={data?.currencies ?? []}
          pagination={false}
          columns={[
            {
              title: 'Currency',
              dataIndex: 'currency',
              render: (v: string, row: CurrencyRateInfo) => (
                <Space>
                  <strong>{v}</strong>
                  {row.is_reporting_currency && <Tag color="blue">Reporting</Tag>}
                  {row.is_default && <Tag color="orange">Default</Tag>}
                </Space>
              ),
            },
            {
              title: `1 unit in ${data?.reporting_currency ?? 'USD'}`,
              dataIndex: 'rate_to_usd',
              align: 'right' as const,
            },
            {
              title: 'In effect since',
              dataIndex: 'effective_from',
              render: (v: string | null) => (v ? dayjs(v).format('MMM D, YYYY') : '—'),
            },
            {
              title: '',
              key: 'actions',
              render: (_: unknown, row: CurrencyRateInfo) =>
                // The reporting currency is 1 by definition; a settable value
                // would let somebody make dollars worth something else.
                row.is_reporting_currency ? null : (
                  <Button
                    size="small"
                    onClick={() => { setEditing(row); setRate(Number(row.rate_to_usd)); }}
                  >
                    Set rate
                  </Button>
                ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`Set ${editing?.currency} rate`}
        open={editing !== null}
        onCancel={() => setEditing(null)}
        onOk={() => editing && saveMut.mutate(editing)}
        confirmLoading={saveMut.isPending}
        okButtonProps={{ disabled: !rate || rate <= 0 }}
        okText="Publish"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            What one {editing?.currency} is worth in {data?.reporting_currency ?? 'USD'}.
            Deals already recorded keep the rate they were converted at.
          </Typography.Paragraph>
          <InputNumber
            style={{ width: '100%' }}
            min={0.000001}
            step={0.0001}
            // Six places because PKR needs four to be useful at all.
            precision={6}
            value={rate}
            onChange={setRate}
          />
        </Space>
      </Modal>
    </>
  );
};

export default CurrencyRatesPage;

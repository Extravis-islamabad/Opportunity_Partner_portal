import React from 'react';
import { Button, Card, Col, Empty, InputNumber, Row, Select, Space, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { opportunitiesApi } from '@/api/endpoints';
import type { ProductLine } from '@/types';

/**
 * The products on a deal, with the sizing the quote is built from.
 *
 * A form field rather than a page: the create and edit forms both need it, and
 * a second copy is how the two drift apart. Shaped as a controlled value so it
 * drops into an antd `Form.Item` alongside every other field.
 *
 * Sizing is captured here — before the PO — because it is what the quote is
 * priced from. It used to appear only on the licence record, which is created
 * after the PO has already landed.
 */
interface Props {
  value?: ProductLine[];
  onChange?: (lines: ProductLine[]) => void;
  /** The deal's currency, so a line value is not labelled in dollars on a
   *  deal the customer pays for in rupees. */
  currency?: string;
}

const ProductLinesField: React.FC<Props> = ({ value, onChange, currency = 'USD' }) => {
  const lines = value ?? [];

  const { data: catalogue } = useQuery({
    queryKey: ['product-catalogue'],
    queryFn: async () => (await opportunitiesApi.products()).data,
    staleTime: Infinity,
  });

  const update = (index: number, patch: Partial<ProductLine>) => {
    onChange?.(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  };

  const taken = new Set(lines.map((l) => l.product));
  const available = (catalogue ?? []).filter((o) => !taken.has(o.value));

  return (
    <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
      {lines.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No products yet — add the ones this deal covers"
          style={{ margin: '8px 0' }}
        />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {lines.map((line, index) => (
            <Row gutter={8} key={`${line.product}-${index}`} align="middle">
              <Col xs={24} sm={7}>
                <Select
                  style={{ width: '100%' }}
                  value={line.product || undefined}
                  placeholder="Product"
                  onChange={(product) => update(index, { product })}
                  options={(catalogue ?? []).map((o) => ({
                    value: o.value,
                    label: o.label,
                    // A product already on the deal cannot be added twice —
                    // the API refuses it, so the form should not offer it.
                    disabled: o.value !== line.product && taken.has(o.value),
                  }))}
                />
              </Col>
              <Col xs={12} sm={4}>
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  placeholder="Devices"
                  value={line.device_count ?? null}
                  onChange={(v) => update(index, { device_count: v ?? null })}
                />
              </Col>
              <Col xs={12} sm={4}>
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  placeholder="Nodes"
                  value={line.node_count ?? null}
                  onChange={(v) => update(index, { node_count: v ?? null })}
                />
              </Col>
              <Col xs={20} sm={7}>
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  prefix={currency}
                  placeholder="Line value"
                  value={line.value !== null && line.value !== undefined ? Number(line.value) : null}
                  onChange={(v) => update(index, { value: v ?? null })}
                />
              </Col>
              <Col xs={4} sm={2} style={{ textAlign: 'right' }}>
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => onChange?.(lines.filter((_, i) => i !== index))}
                />
              </Col>
            </Row>
          ))}
        </Space>
      )}

      <Button
        type="dashed"
        icon={<PlusOutlined />}
        style={{ marginTop: 12, width: '100%' }}
        disabled={available.length === 0}
        onClick={() =>
          onChange?.([
            ...lines,
            { product: available[0]?.value ?? '', device_count: null, node_count: null, value: null },
          ])
        }
      >
        {available.length === 0 ? 'Every product is already on this deal' : 'Add product'}
      </Button>

      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
        Line values need not add up to the deal total — anything left over is
        reported as unattributed rather than assigned to a product.
      </Typography.Text>
    </Card>
  );
};

export default ProductLinesField;

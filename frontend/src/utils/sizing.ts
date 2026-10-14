/**
 * Nodes and devices are the same thing. Product lines and licences still carry
 * both columns from when they were tracked apart; the UI shows and edits one
 * number, stored in device_count, falling back to node_count for records that
 * only ever had that one filled in.
 */
export const lineSize = (line: {
  device_count?: number | null;
  node_count?: number | null;
}): number | null => line.device_count ?? line.node_count ?? null;

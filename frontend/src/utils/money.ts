/**
 * Money that may not be in dollars.
 *
 * A deal carries the currency it was done in and its value converted at the
 * rate stamped when it was recorded. Screens show the native amount — that is
 * what the customer signed — and the reporting value beside it when the two
 * differ, because a bare "500,000" against a PKR deal reads as half a million
 * dollars to anybody scanning a column.
 */
export const formatMoney = (
  amount: string | number | null | undefined,
  currency = 'USD',
): string => {
  if (amount === null || amount === undefined || amount === '') return '—';
  const n = Number(amount);
  if (Number.isNaN(n)) return '—';
  return `${currency} ${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

/** The reporting figure, shown only when it differs from the native amount. */
export const reportingSuffix = (
  currency: string | null | undefined,
  worthUsd: string | null | undefined,
): string | null => {
  if (!currency || currency === 'USD' || !worthUsd) return null;
  return `≈ USD ${Number(worthUsd).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

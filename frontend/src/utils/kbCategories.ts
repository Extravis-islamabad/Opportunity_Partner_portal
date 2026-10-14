/**
 * Knowledge-base categories offered wherever a document is uploaded. Extravis
 * (company-wide material) and every product, PatchX included, come first.
 */
export const KB_CATEGORIES = [
  'Extravis', 'MonetX', 'SupportX', 'GreenX', 'PatchX', 'AgentX',
  'Product Sheets', 'Case Studies', 'Technical Guides',
] as const;

export const KB_CATEGORY_OPTIONS = KB_CATEGORIES.map((value) => ({ value, label: value }));

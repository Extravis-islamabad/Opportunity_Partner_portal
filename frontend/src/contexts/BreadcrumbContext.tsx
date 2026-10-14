import React, { createContext, useContext, useState } from 'react';

/**
 * Whether the current page renders its own breadcrumb trail (PageHeader's
 * `breadcrumbs`). When it does, the layout's route-derived trail stands aside:
 * showing both stacked two trails for the same location, the generic one
 * naming records by id ("#25") right above the page's ("E2E Direct Deal").
 */
interface BreadcrumbOwnership {
  pageOwnsCrumbs: number;
  setPageOwnsCrumbs: React.Dispatch<React.SetStateAction<number>>;
}

const BreadcrumbContext = createContext<BreadcrumbOwnership>({
  pageOwnsCrumbs: 0,
  setPageOwnsCrumbs: () => undefined,
});

export const BreadcrumbProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // A count rather than a flag, so overlapping mounts during a route change
  // cannot leave it stuck either way.
  const [pageOwnsCrumbs, setPageOwnsCrumbs] = useState(0);
  return (
    <BreadcrumbContext.Provider value={{ pageOwnsCrumbs, setPageOwnsCrumbs }}>
      {children}
    </BreadcrumbContext.Provider>
  );
};

export const useBreadcrumbOwnership = (): BreadcrumbOwnership => useContext(BreadcrumbContext);

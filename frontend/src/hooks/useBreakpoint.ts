import { Grid } from 'antd';

/**
 * Thin wrapper around Ant Design's Grid.useBreakpoint that also exposes a
 * boolean `isMobile` flag (viewport < md). Avoids re-implementing
 * matchMedia in a dozen places.
 */
export function useBreakpoint(): { isMobile: boolean; isTablet: boolean; isDesktop: boolean } {
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const isTablet = !!screens.md && !screens.lg;
  const isDesktop = !!screens.lg;
  return { isMobile, isTablet, isDesktop };
}

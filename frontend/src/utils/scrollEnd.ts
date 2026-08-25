// react-native-web's FlatList/VirtualizedList only calls `onEndReached` once
// per distinct measured content length (see `_sentEndForContentLength` in
// @react-native/virtualized-lists). On web, grid FlatLists (`numColumns`)
// reliably fire it once during the initial loading-skeleton render (harmless,
// guarded away by callers checking `hasMore`/`total`) and then never again
// for the real, larger content — even once genuinely scrolled to the bottom.
// Reproduced live: 25+ incremental scroll-to-bottom events, zero further
// `onEndReached` calls, despite correct contentSize/scroll offsets. This is a
// known upstream RN-Web limitation, not app logic — so callers should treat
// `onEndReached` as a bonus and drive pagination from `onScroll` directly.
export function isNearScrollEnd(
  nativeEvent: { contentOffset: { y: number }; contentSize: { height: number }; layoutMeasurement: { height: number } },
  thresholdRatio = 0.5,
): boolean {
  const { contentOffset, contentSize, layoutMeasurement } = nativeEvent;
  if (contentSize.height <= layoutMeasurement.height) return false;
  const distanceFromEnd = contentSize.height - layoutMeasurement.height - contentOffset.y;
  return distanceFromEnd <= layoutMeasurement.height * thresholdRatio;
}

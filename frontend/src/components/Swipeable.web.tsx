import { forwardRef, type ReactNode, useImperativeHandle } from "react";

export type SwipeableHandle = { close: () => void };

// Follow-up cards already use visible action controls in the browser. Avoid
// loading Hammer/gesture-handler solely for a native-only swipe affordance.
export const Swipeable = forwardRef<SwipeableHandle, { children: ReactNode }>(function Swipeable({ children }, ref) {
  useImperativeHandle(ref, () => ({ close: () => undefined }), []);
  return <>{children}</>;
});

export default Swipeable;

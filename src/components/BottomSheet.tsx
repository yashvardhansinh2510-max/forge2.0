// Legacy API adapter. All app sheets now use the design-system Sheet so their
// safe-area, keyboard, backdrop, close, and accessibility behavior cannot
// drift between catalog and quotation flows.
import React from "react";

import { Sheet } from "@/src/design/components";

export function BottomSheet({
  visible, onClose, title, children, footer, testID, maxHeight = 0.85,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  testID?: string;
  maxHeight?: number;
}) {
  return (
    <Sheet
      open={visible}
      onClose={onClose}
      title={title}
      footer={footer}
      maxHeight={maxHeight}
      testID={testID}
    >
      {children}
    </Sheet>
  );
}

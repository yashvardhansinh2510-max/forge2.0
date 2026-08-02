import { Text, View } from "react-native";

import { Card, EmptyState, ErrorState, LoadingState, SkeletonList } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

/**
 * One block of the Sales Data page: a titled card that owns its own loading,
 * error and empty states.
 *
 * Every section on the page is one of these, so a section that has no data
 * always says so in the same words and in the same place. The alternative —
 * each block inventing its own empty rendering — is how a page ends up
 * showing a blank card in one place and "₹0" in another for the identical
 * condition, leaving the owner unable to tell "nothing sold" from "failed to
 * load".
 *
 * `question` is the owner-facing question the block answers, kept on the
 * block itself rather than in documentation.
 */
export function SalesSection<T>({
  title, question, rows, error, onRetry, emptyTitle, emptySubtitle, footer, testID, children,
}: {
  title: string;
  question?: string;
  /** null means still loading. */
  rows: T[] | null;
  error?: string | null;
  onRetry?: () => void;
  emptyTitle: string;
  emptySubtitle?: string;
  footer?: React.ReactNode;
  testID: string;
  children: (rows: T[]) => React.ReactNode;
}) {
  return (
    <Card testID={testID} variant="flat" padding={spacing.xl}>
      <View style={{ gap: spacing.md }}>
        <View style={{ gap: 2 }}>
          <Text style={type.titleSm}>{title}</Text>
          {question ? (
            <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>{question}</Text>
          ) : null}
        </View>

        {error ? (
          <ErrorState subtitle={error} onRetry={onRetry} />
        ) : rows === null ? (
          <SkeletonList rows={4} />
        ) : rows.length === 0 ? (
          <EmptyState icon="inbox" title={emptyTitle} subtitle={emptySubtitle} />
        ) : (
          <>
            {children(rows)}
            {footer}
          </>
        )}
      </View>
    </Card>
  );
}

/** Re-exported so sections that need a spinner rather than skeleton rows do
 *  not reach past this module for it. */
export { LoadingState };

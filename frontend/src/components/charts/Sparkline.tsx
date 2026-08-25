import Svg, { Polyline } from "react-native-svg";

import { colors } from "@/src/theme/tokens";

import { ChartFrame, type ChartState } from "./ChartFrame";

type Props = {
  points: number[];
  height?: number;
  state?: ChartState;
  testID?: string;
};

/**
 * The KPI-card trend line. Deliberately axis-less and label-less: it shows
 * shape, and the card's value shows magnitude.
 *
 * A single data point cannot describe a trend, so it renders the empty state
 * rather than a misleading flat line — the same honesty rule the backend's
 * history_state follows.
 */
export function Sparkline({ points, height = 36, state, testID }: Props) {
  const resolved: ChartState = state ?? (points.length < 2 ? "empty" : "ready");

  return (
    <ChartFrame height={height} state={resolved} testID={testID}>
      {(width) => {
        const min = Math.min(...points);
        const max = Math.max(...points);
        const span = max - min || 1;
        const stepX = width / (points.length - 1);
        const coords = points
          .map((value, i) => `${i * stepX},${height - ((value - min) / span) * height}`)
          .join(" ");

        return (
          <Svg width={width} height={height}>
            <Polyline points={coords} fill="none" stroke={colors.brand} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          </Svg>
        );
      }}
    </ChartFrame>
  );
}

// ProductImage
// -----------------------------------------------------------------------------
// A production-ready image renderer for supplier catalog products.
//
// Responsibilities
//   * Skeleton loader while the byte stream lands
//   * Graceful fallback (branded "no image" glyph) when the product has no
//     image or every candidate URL / data-URL fails to load
//   * Error handling that walks through the images array before giving up
//     (some suppliers ship multiple candidates; we prefer the first that loads)
//   * Caching via expo-image's memory+disk cache (default policy `disk`)
//   * Responsive by design — the caller controls dimensions via `style`
//   * Supports both http(s) URLs and base64 data URLs (the format the catalog
//     pipeline produces after image_extractor decodes WDP → PNG)
//
// It is deliberately dependency-free of app state; it just needs the array of
// candidate images (or a single string) and optional style/contentFit props.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { Image as ExpoImage, ImageContentFit } from "expo-image";
import { useEffect, useMemo, useRef, useState } from "react";
import { Animated, Easing, StyleSheet, View, ViewStyle } from "react-native";

import { colors, radius } from "@/src/theme/tokens";

export type ProductImageProps = {
  // Accept either a single URL/data-URL or an ordered list of fallback candidates.
  source?: string | string[] | null | undefined;
  // Container style — width/height/aspectRatio live here.
  style?: ViewStyle | ViewStyle[];
  // "cover" | "contain" | "fill" | "scale-down" — passed through to expo-image.
  contentFit?: ImageContentFit;
  // Optional testID for e2e testing.
  testID?: string;
  // Optional accessible name; falls back to "Product image".
  accessibilityLabel?: string;
  // If true, the skeleton shimmer is disabled (useful for tiny thumbs).
  disableSkeleton?: boolean;
  // Corner radius override; defaults to `radius.md`.
  borderRadius?: number;
  // Optional label to display in the fallback state (usually SKU).
  fallbackLabel?: string | null;
};

const CACHE_POLICY = "memory-disk" as const;
// Small transparent placeholder shown by expo-image while the real image
// loads. Prevents a flash of layout-shifting default.
const BLURHASH = "L6PZfSjE.AyE_3t7t7R**0o#DgR4";

export function ProductImage({
  source,
  style,
  contentFit = "cover",
  testID,
  accessibilityLabel = "Product image",
  disableSkeleton = false,
  borderRadius,
  fallbackLabel,
}: ProductImageProps) {
  // Normalise `source` into an ordered list of candidates. Empty / null entries
  // are stripped so we don't waste a load attempt on them.
  const candidates: string[] = useMemo(() => {
    if (!source) return [];
    const arr = Array.isArray(source) ? source : [source];
    return arr.filter((s): s is string => typeof s === "string" && s.length > 0);
  }, [source]);

  // Track the current candidate index. On error we advance; once we run out
  // of candidates we render the fallback glyph.
  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(candidates.length === 0);

  // Reset when the candidate list changes (e.g. product swap).
  useEffect(() => {
    setIdx(0);
    setLoaded(false);
    setFailed(candidates.length === 0);
  }, [candidates.join("|")]);

  const current = candidates[idx];
  const finalRadius = typeof borderRadius === "number" ? borderRadius : radius.md;

  return (
    <View
      style={[styles.wrap, { borderRadius: finalRadius }, style as any]}
      testID={testID}
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="image"
    >
      {failed || !current ? (
        <FallbackGlyph label={fallbackLabel} />
      ) : (
        <>
          {!loaded && !disableSkeleton ? <Skeleton /> : null}
          <ExpoImage
            source={{ uri: current }}
            style={[StyleSheet.absoluteFill, { borderRadius: finalRadius }]}
            contentFit={contentFit}
            cachePolicy={CACHE_POLICY}
            placeholder={{ blurhash: BLURHASH }}
            transition={220}
            recyclingKey={current}
            onLoad={() => setLoaded(true)}
            onError={() => {
              // Advance to next candidate, or give up.
              if (idx + 1 < candidates.length) {
                setIdx(idx + 1);
                setLoaded(false);
              } else {
                setFailed(true);
              }
            }}
          />
        </>
      )}
    </View>
  );
}

// -----------------------------------------------------------------------------
// Skeleton — a soft shimmer used while the real bytes are decoding. Kept
// deliberately small; big shimmer animations on lists cause jank.
// -----------------------------------------------------------------------------
function Skeleton() {
  const opacity = useRef(new Animated.Value(0.35)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 700, useNativeDriver: true, easing: Easing.inOut(Easing.ease) }),
        Animated.timing(opacity, { toValue: 0.35, duration: 700, useNativeDriver: true, easing: Easing.inOut(Easing.ease) }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return <Animated.View style={[StyleSheet.absoluteFill, styles.skeleton, { opacity }]} />;
}

// -----------------------------------------------------------------------------
// FallbackGlyph — displayed when the product has no image at all, or every
// candidate failed. Deliberately understated so it doesn't scream "broken".
// -----------------------------------------------------------------------------
function FallbackGlyph({ label }: { label?: string | null }) {
  return (
    <View style={styles.fallback}>
      <Feather name="image" size={18} color={colors.onSurfaceMuted} />
      {label ? (
        <View style={styles.fallbackLabelWrap}>
          <FallbackLabel label={label} />
        </View>
      ) : null}
    </View>
  );
}

function FallbackLabel({ label }: { label: string }) {
  const { Text } = require("react-native");
  return (
    <Text
      numberOfLines={1}
      style={{
        fontSize: 9,
        fontWeight: "600",
        color: colors.onSurfaceMuted,
        letterSpacing: 0.4,
      }}
    >
      {label.toUpperCase()}
    </Text>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.surfaceTertiary,
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  skeleton: {
    backgroundColor: colors.surfaceTertiary,
  },
  fallback: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
  },
  fallbackLabelWrap: {
    paddingHorizontal: 4,
    maxWidth: "90%",
  },
});

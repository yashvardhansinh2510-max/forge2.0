// Reusable BottomSheet (portal-modeled) — mounts at document root so it never
// clashes with tab bars / sidebars. No zIndex bleed: React Native <Modal> handles it.
import { Feather } from "@expo/vector-icons";
import { BlurView } from "expo-blur";
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, radius, spacing, type } from "@/src/theme/tokens";

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
  const { height, width } = useWindowDimensions();
  const isTablet = width >= 900;
  const targetWidth = isTablet ? Math.min(560, width - 80) : width;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <Pressable style={styles.backdrop} onPress={onClose} testID={`${testID}-backdrop`}>
        <Pressable style={{ maxHeight: height * maxHeight, width: targetWidth, marginTop: "auto" }} onPress={(e) => e.stopPropagation()}>
          <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"}>
            <SafeAreaView edges={["bottom"]} style={styles.sheet}>
              <View style={styles.grabber} />
              <View style={styles.head}>
                <Text style={type.titleMd}>{title}</Text>
                <Pressable testID={`${testID}-close`} hitSlop={12} onPress={onClose}>
                  <Feather name="x" size={20} color={colors.onSurfaceMuted} />
                </Pressable>
              </View>
              <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 0 }} keyboardShouldPersistTaps="handled">
                {children}
              </ScrollView>
              {footer ? <View style={styles.foot}>{footer}</View> : null}
            </SafeAreaView>
          </KeyboardAvoidingView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: colors.overlay, alignItems: "center" },
  sheet: {
    backgroundColor: colors.surfaceSecondary,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    borderRadius: 20,
    overflow: "hidden",
  },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong, marginTop: 8, marginBottom: 4 },
  head: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  foot: {
    padding: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
});

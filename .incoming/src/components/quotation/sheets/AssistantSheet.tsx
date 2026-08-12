// AssistantSheet — mobile bottom-sheet host for the AssistantPane.
import { Modal, Pressable, StyleSheet, View, useWindowDimensions } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import { AssistantPane } from "../panes/AssistantPane";

export function AssistantSheet() {
  const b = useBuilder();
  const { height } = useWindowDimensions();
  const close = () => b.setAssistantOpenMobile(false);

  return (
    <Modal
      visible={b.assistantOpenMobile}
      transparent
      animationType="slide"
      onRequestClose={close}
      statusBarTranslucent
    >
      <Pressable style={styles.backdrop} onPress={close} testID="assistant-sheet-backdrop">
        <Pressable onPress={(e) => e.stopPropagation()} style={{ marginTop: "auto", width: "100%", height: height * 0.9 }}>
          <SafeAreaView edges={["bottom"]} style={styles.sheet}>
            <View style={styles.grabber} />
            <View style={{ flex: 1 }}>
              <AssistantPane onClose={close} />
            </View>
          </SafeAreaView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  sheet: {
    flex: 1, backgroundColor: colors.surfaceSecondary,
    borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: "hidden",
  },
  grabber: {
    alignSelf: "center", width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.borderStrong, marginTop: 8, marginBottom: 4,
  },
});

// Browser-only compatibility surface for native animation integrations.
// The app uses browser-native scrolling on web; this preserves the React
// Native Reanimated interface used by draggable-flatlist without loading its
// native runtime into every browser route.
const React = require("react");
const RN = require("react-native");

const value = (initial) => ({ value: initial });
const passthrough = (callback) => callback;
const Animated = Object.assign({}, RN.Animated, {
  View: RN.View,
  Text: RN.Text,
  Image: RN.Image,
  ScrollView: RN.ScrollView,
  FlatList: RN.FlatList,
  createAnimatedComponent: (Component) => Component,
});

module.exports = Animated;
module.exports.default = Animated;
function useSharedValue(initial) { return React.useRef(value(initial)).current; }
function useDerivedValue(factory) { return React.useRef(value(factory())).current; }
function useAnimatedRef() { return React.useRef(null); }
module.exports.makeMutable = value;
module.exports.useSharedValue = useSharedValue;
module.exports.useDerivedValue = useDerivedValue;
module.exports.useAnimatedRef = useAnimatedRef;
module.exports.useAnimatedStyle = (factory) => factory();
module.exports.useAnimatedProps = (factory) => factory();
module.exports.useAnimatedScrollHandler = (handlers) => handlers?.onScroll || (() => undefined);
module.exports.useEvent = () => () => undefined;
module.exports.useAnimatedReaction = () => undefined;
module.exports.useFrameCallback = () => undefined;
module.exports.withTiming = (next) => next;
module.exports.withSpring = (next) => next;
module.exports.withDecay = (config) => config?.velocity ?? 0;
module.exports.cancelAnimation = () => undefined;
module.exports.interpolate = (input, inputRange, outputRange) => {
  const index = Math.max(0, inputRange.findIndex((point) => input <= point));
  return outputRange[index] ?? outputRange[outputRange.length - 1];
};
module.exports.Extrapolation = { CLAMP: "clamp", EXTEND: "extend", IDENTITY: "identity" };
module.exports.ReduceMotion = { System: "system", Always: "always", Never: "never" };
module.exports.Easing = RN.Easing;
module.exports.runOnJS = passthrough;
module.exports.runOnUI = passthrough;
module.exports.measure = () => null;
module.exports.startScreenTransition = () => undefined;
module.exports.finishScreenTransition = () => undefined;
module.exports.ScreenTransition = {};

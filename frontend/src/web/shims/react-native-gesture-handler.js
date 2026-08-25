// Native gestures are not used by the browser shell. This compatibility
// surface preserves navigation/component imports while avoiding HammerJS and
// the native gesture runtime in the initial web graph.
const React = require("react");
const { View } = require("react-native");
const Empty = ({ children }) => React.createElement(React.Fragment, null, children);
const Swipeable = React.forwardRef(({ children }, ref) => {
  React.useImperativeHandle(ref, () => ({ close() {}, openLeft() {}, openRight() {} }), []);
  return React.createElement(React.Fragment, null, children);
});
Swipeable.displayName = "WebSwipeable";
const gesture = new Proxy({}, { get: () => () => gesture });
module.exports = {
  GestureHandlerRootView: View,
  GestureDetector: Empty,
  Swipeable,
  DrawerLayout: Empty,
  PanGestureHandler: Empty,
  TapGestureHandler: Empty,
  LongPressGestureHandler: Empty,
  NativeViewGestureHandler: Empty,
  Gesture: gesture,
  State: { UNDETERMINED: 0, FAILED: 1, BEGAN: 2, CANCELLED: 3, ACTIVE: 4, END: 5 },
  Directions: { RIGHT: 1, LEFT: 2, UP: 4, DOWN: 8 },
};
module.exports.default = module.exports;

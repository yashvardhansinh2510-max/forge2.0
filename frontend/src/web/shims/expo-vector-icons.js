// A compact browser icon fallback. Native keeps the full bundled icon-font;
// the web shell uses familiar Unicode marks so startup does not include the
// icon font loader and its complete glyph table on every route.
const React = require("react");
const { Text } = require("react-native");
const marks = {
  "arrow-left":"←", "arrow-right":"→", "chevron-left":"‹", "chevron-right":"›", "chevron-down":"⌄", "chevron-up":"⌃",
  "x":"×", "x-circle":"×", "check":"✓", "check-circle":"✓", "plus":"+", "minus":"−", "search":"⌕", "menu":"☰",
  "more-horizontal":"•••", "more-vertical":"⋮", "eye":"◉", "eye-off":"◌", "edit":"✎", "edit-3":"✎", "trash":"⌫", "trash-2":"⌫",
  "phone":"☎", "phone-call":"☎", "mail":"✉", "message-circle":"◌", "calendar":"□", "clock":"◷", "bell":"●", "user":"●",
  "users":"●", "settings":"⚙", "home":"⌂", "package":"□", "layers":"▤", "file-text":"▧", "download":"↓", "upload":"↑",
  "filter":"≡", "sliders":"≡", "shopping-cart":"□", "credit-card":"▭", "lock":"●", "info":"i", "alert-circle":"!",
};
function Feather({ name, size = 16, color, style, ...props }) {
  return React.createElement(Text, { ...props, style: [{ fontSize: size, lineHeight: size, color, fontFamily: "system-ui", textAlign: "center" }, style] }, marks[name] || "•");
}
Feather.glyphMap = marks;
module.exports = { Feather };

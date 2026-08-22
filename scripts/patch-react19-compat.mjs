import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const packageFiles = [
  "../node_modules/@radix-ui/react-slot/dist/index.js",
  "../node_modules/@radix-ui/react-slot/dist/index.mjs",
  "../node_modules/expo-router/node_modules/@radix-ui/react-slot/dist/index.js",
  "../node_modules/expo-router/node_modules/@radix-ui/react-slot/dist/index.mjs",
].map((relativePath) => resolve(decodeURIComponent(new URL(relativePath, import.meta.url).pathname)));

for (const packageFile of packageFiles) {
  if (!existsSync(packageFile)) continue;
  const source = readFileSync(packageFile, "utf8");
  const target = /function getElementRef\(element\) \{[\s\S]*?\n\}/;
  if (!target.test(source) || source.includes("return element.props?.ref;")) continue;
  const replacement = "function getElementRef(element) {\n  return element.props?.ref;\n}";
  writeFileSync(packageFile, source.replace(target, replacement));
}

for (const relativePath of [
  "../node_modules/react-native-web/src/exports/TouchableWithoutFeedback/index.js",
  "../node_modules/react-native-web/dist/cjs/exports/TouchableWithoutFeedback/index.js",
  "../node_modules/react-native-web/dist/exports/TouchableWithoutFeedback/index.js",
  "../node_modules/react-native-gesture-handler/lib/commonjs/handlers/createHandler.js",
  "../node_modules/react-native-gesture-handler/lib/module/handlers/createHandler.js",
  "../node_modules/react-native-gesture-handler/lib/commonjs/web/utils.js",
  "../node_modules/react-native-gesture-handler/lib/module/web/utils.js",
]) {
  const packageFile = resolve(decodeURIComponent(new URL(relativePath, import.meta.url).pathname));
  if (!existsSync(packageFile)) continue;
  const source = readFileSync(packageFile, "utf8");
  const target = /React\.version\.startsWith\('19'\) \? element\.props\.ref : element\.ref|(?:(?:\(0, _utils2\.isReact19\)\(\)|isReact19\(\))) \? child\.props\.ref : child\.ref/;
  if (target.test(source)) {
    writeFileSync(packageFile, source.replace(target, source.includes("element.props.ref") ? "element.props?.ref" : "child.props?.ref"));
  } else if (source.includes("node.ref?.rngh")) {
    writeFileSync(packageFile, source.replaceAll("node.ref?.rngh", "node.props?.ref?.rngh"));
  }
}

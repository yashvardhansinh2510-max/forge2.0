# Frontend dependency audit — 2026-09-01

Command: `cd frontend && npm audit --omit=dev --json`.

Result: 31 production dependency-tree advisories: 14 high and 17 moderate, with no critical advisories. The lockfile was not changed: every offered top-level remediation crosses Expo SDK compatibility boundaries, and `npm audit fix --force` was not used.

## Classification

Potential runtime reachability:

- `expo-router` → React Navigation → `query-string` → `decode-uri-component` (moderate). Router/deep-link parsing is part of application navigation, so treat this as potentially runtime reachable.
- The direct `expo`, `expo-asset`, `expo-constants`, `expo-linking`, `expo-splash-screen`, and `react-native` findings are shipped mobile-platform dependencies. Their reported vulnerable paths are primarily Expo/Metro configuration, but they must be re-audited as part of the supported SDK upgrade.

Build/development-path reachability:

- `@expo/cli`, `@expo/config*`, `@expo/metro*`, `metro*`, `@react-native/community-cli-plugin`, `image-size`, `postcss`, `brace-expansion`, `js-yaml`, `nanoid`, `uuid`, and `xcode` are reached through Expo/Metro tooling. They run in local/CI/cloud build environments rather than the released browser bundle.

## Safe remediation path

The audit proposes Expo SDK 57 packages (including `expo@57.0.18`, `expo-router@5.1.11`, and React Native `0.87.1`) or related major compatibility moves. This project is on Expo SDK 54 / React Native 0.81, so applying those changes independently would create an unsupported dependency matrix. Schedule a dedicated Expo SDK upgrade with `npx expo install --fix`, Expo Doctor, native build smoke tests, and a repeat production-only audit. Until then, restrict build credentials, keep build runners patched, and do not process untrusted project configuration in build environments.

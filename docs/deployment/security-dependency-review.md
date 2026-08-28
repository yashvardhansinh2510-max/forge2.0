# Dependency security review

Reviewed 2026-08-28 using the committed production dependency manifests.

## Commands and results

- `cd frontend && npm audit --omit=dev --json`: 24 findings (14 high, 10 moderate, 0 critical).
- `cd frontend && npx expo install --check`: passed after updating Expo SDK-compatible patches to `expo@~54.0.37` and `expo-constants@~18.0.14`.
- `cd backend && .venv/bin/python -m pip_audit -r requirements-prod.txt --format json`: no known vulnerabilities.
- `cd backend && .venv/bin/python -m pip check`: no broken requirements.

## Residual frontend risk

The remaining npm findings are rooted in the Expo 54 / React Native 0.81 Metro toolchain. `npm audit` offers only a breaking Expo 57 and React Native 0.87 upgrade. The affected packages include the Expo CLI/config/prebuild chain, Metro/image parsing tooling, and React Native's community CLI plugin. They run during local development/build/prebuild rather than in the generated browser bundle, but can affect a build runner that processes untrusted project assets or configuration.

This review intentionally did not use `npm audit fix --force`, package-manager resolutions, or overrides to mask those findings. A separate Expo 57 migration, native smoke test, and audit re-run are required before treating the frontend audit as clean.

## Non-production requirements freeze

`backend/requirements.txt` is an Emergent preview-environment freeze, not the production install source. It currently cannot be resolver-audited on Python 3.14 because `google-ai-generativelanguage==0.6.15` requires `protobuf<6`, while the Python-3.14-compatible `grpcio-status` line requires `protobuf>=6.33.5`. Production uses `requirements-prod.txt`, which resolver-audits cleanly. Reconcile or retire the unused preview-only Google dependency group before making the full freeze a CI installation target.

import { spawnSync } from "node:child_process";

// Expo SDK 54's Metro/CLI dependency graph currently carries high-severity
// parser/DoS advisories whose only available npm remediation is the breaking
// Expo 57 upgrade. They execute during trusted local/CI builds and are not
// shipped as server-side request handlers. Keep them visible, but do not let
// that known build-tool cluster hide a newly introduced runtime advisory.
const expoBuildToolAllowlist = new Set([
  "expo",
  "@expo/cli",
  "@expo/metro",
  "@expo/metro-config",
  "metro",
  "metro-config",
  "metro-transform-worker",
  "brace-expansion",
  "image-size",
  "postcss",
]);

const audit = spawnSync("npm", ["audit", "--json"], { encoding: "utf8" });
if (!audit.stdout) {
  process.stderr.write(audit.stderr || "npm audit produced no report\n");
  process.exit(1);
}

const report = JSON.parse(audit.stdout);
const blocking = Object.entries(report.vulnerabilities || {}).filter(([name, finding]) => {
  if (finding.severity === "critical") return true;
  return finding.severity === "high" && !expoBuildToolAllowlist.has(name);
});

if (blocking.length) {
  console.error("Blocking npm advisories:", blocking.map(([name, finding]) => `${name} (${finding.severity})`).join(", "));
  process.exit(1);
}

const allowed = Object.entries(report.vulnerabilities || {})
  .filter(([name, finding]) => finding.severity === "high" && expoBuildToolAllowlist.has(name))
  .map(([name]) => name);
console.log(`npm audit gate passed; tracked Expo 54 build-tool advisories: ${allowed.join(", ") || "none"}`);

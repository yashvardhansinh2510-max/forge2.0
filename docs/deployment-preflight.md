# Deployment preflight

Run the manual **Pre-deployment Gate** workflow from the release commit. It is
read-only against MongoDB and Supabase: it checks connectivity, required
indexes, object/media metadata and runs the normal dependency, test, lint,
accessibility-contract, web-export and bundle-budget gates.

The gate fails on any media object that is missing, undecodable, has a MIME,
size, dimension or SHA-1 mismatch, or whose Mongo metadata is orphaned. It
does not repair, delete, overwrite, migrate or rotate anything. Full scans are
rate limited; use `--max-items` only for a non-release smoke test.

Before approving a deployment, a release owner must also confirm:

- pending migrations have a documented forward-safe plan and the known live
  duplicate SKU blocking migration `0006` is resolved;
- backups and rollback ownership are confirmed outside this repository;
- production secrets exist in the protected GitHub `production` environment;
- the live service health/latency dashboard meets the agreed SLO; and
- any failing audit item is explicitly resolved, rather than suppressed.

The workflow intentionally has no deploy step. Deployment remains a human
approval action after this evidence is reviewed.

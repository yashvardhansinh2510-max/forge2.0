# Persistence & Environment Audit — BuildCon House (Forge) — 2026-07-07

Scope: explain exactly why this workspace loses state between sessions, what is
and isn't recoverable right now, and what a permanent fix requires. No feature
work, no bug fixes beyond the two persistence-threatening issues noted at the
end. No automated test suites were run for this report.

---

## 1. Filesystem map — what's ephemeral vs what's on real disk

```
mount output (this session):
  overlay  on /            (container image layers — EPHEMERAL, resets every new session/pod)
  nvme0n2  on /app         (real block volume — persists across restarts WITHIN a session/pod)
  nvme0n2  on /data/db     (same volume — MongoDB dbpath)
  nvme0n2  on /root        (same volume — includes /root/.venv, the Python venv)
```

The important nuance: `/app`, `/data/db` and `/root` all sit on the *same*
per-pod volume, so a simple container/process restart (supervisor restart,
crash, `sudo supervisorctl restart backend`) does **not** by itself wipe
Mongo data or the venv — evidence from this session: `/data/db` had WiredTiger
files already dated at the current session's start timestamp, i.e. freshly
initialized, not restored from a prior pod.

**What actually resets state is a new session/fork**, which provisions a
**brand-new pod with a brand-new volume**. That new volume only gets seeded
with:
1. Whatever is checked out from **GitHub** into `/app` (your code — this
   persists correctly, 77 commits, remote confirmed reachable).
2. A base container image (Python/Node runtimes, OS packages).

Everything else that lived on the *previous* pod's volume — the local Mongo
data files, the `/root/.venv` site-packages, any files written outside git —
does not exist on the new volume. It isn't "deleted", it's simply a disk that
was never written to in the new pod.

## 2. Where MongoDB actually stores data right now

- `mongod` runs **inside this container** (`/usr/bin/mongod --bind_ip_all
  --wiredTigerCacheSizeGB 0.25`, supervisor-managed, config `/etc/mongod.conf`).
- Data directory: `/data/db` (on the per-pod volume described above).
- `backend/db.py` connects via `MONGO_URL` from `backend/.env` — this session
  it was `mongodb://localhost:27017` (local, not Atlas).
- **This is a local, non-persistent MongoDB.** It is not MongoDB Atlas, not
  any external managed database. Every new session/fork = empty database.
- Verified live at session start: `/data/db` contained zero application
  databases (`admin`, `config`, `local` only) — the previously-imported
  catalog was not present, confirming total data loss from the prior session.

## 3 & 4. Local vs external / Atlas vs temporary — answered above
Local, temporary, container-internal. **Not** Atlas. This is the single
biggest root cause of "the app forgets everything."

## 5. Why `.env` files disappear
Three independent facts combine to cause this:
1. `.gitignore` correctly excludes `.env`, `.env.*`, `*.env` — this is
   correct practice (secrets must never be committed).
2. A new session/fork only restores what's in Git (see §1) — so a file that
   was never committed doesn't come back.
3. The platform's own `/entrypoint.sh` **does** try to patch
   `frontend/.env` on every pod boot (it `sed`-replaces
   `EXPO_PACKAGER_HOSTNAME` / `EXPO_PUBLIC_BACKEND_URL` /
   `EXPO_TUNNEL_SUBDOMAIN` / `EXPO_PACKAGER_PROXY_URL` with the new pod's
   preview URL) — **but only if the file already exists**
   (`if [ -f "/app/frontend/.env" ]; then ... fi`). If it's missing, this
   block silently no-ops. There is **no equivalent logic for
   `backend/.env`** anywhere in `entrypoint.sh` — backend secrets are 100%
   this app's own responsibility, by design (the platform can't know what a
   given FastAPI app needs).
   This session started with **both** files missing, which is why the
   backend was crash-looping (`KeyError: MONGO_URL`) before I intervened.
4. This repo already has a self-authored recovery tool for exactly this —
   `scripts/setup-env` — which regenerates both `.env` files from prompts or
   from shell env vars. It was not run automatically anywhere (no supervisor
   hook, no entrypoint hook, no `/root/.emergent/on-restart.sh` — that file
   doesn't exist in this session even though `entrypoint.sh` looks for it).

## 6. Why product imports disappear
Direct consequence of §2–3: the catalog importer (`catalog_pipeline/
orchestrator.py`) writes accepted rows into `db.products` — and `db` is the
local, per-pod Mongo. Nothing about the *import pipeline itself* is
lossy — it is correctly idempotent and upsert-by-SKU — the problem is 100%
that its target database is ephemeral. The same import job run against a
persistent Atlas cluster would survive indefinitely.

## 7. Why uploaded/imported images disappear
This one is more nuanced — the *architecture* is actually already correct:
`catalog_pipeline/orchestrator.py` → `_upload_supplier_images()` →
`services/media_service.py::upload_and_register()` → `media_storage/
supabase_driver.py` uploads every image to **Supabase Storage** (external,
persistent), and only a small metadata pointer (`product_media` collection —
bucket + key + public_url + sha1) is kept in Mongo. Legacy base64-in-Mongo
storage was explicitly retired (see orchestrator.py comment: *"Legacy fields
kept empty — media now lives in product_media"*).

So there are actually **two separate failure modes** stacked on top of each
other:
- **The pointer metadata (`product_media` docs) lives in the same ephemeral
  local Mongo** as everything else → lost every new session, same as §6.
- **The actual image bytes may still be safe in Supabase** — I found hard
  evidence of this (see §9 below). But without `SUPABASE_URL` /
  `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env` (also wiped every session,
  same as §5), the app cannot read or write to that bucket at all, so from
  the app's point of view images "disappear" even on sessions where the
  bytes are technically still sitting in Supabase.

## 8. Which files are not committed to GitHub (and shouldn't be)
Confirmed via `.gitignore` + live inspection:
- `backend/.env`, `frontend/.env` — secrets, correctly excluded.
- `frontend/node_modules/` — correctly excluded (restored from a prebuilt
  `/opt/node_modules.tar.zst` archive by `entrypoint.sh`, not from git).
- `/root/.venv` (Python virtualenv / installed packages) — not tracked by
  git at all (it's outside `/app`), and **nothing currently reinstalls it
  automatically** on a fresh pod. This is a second, smaller version of the
  same problem: `requirements.txt` IS committed (good), but nothing runs
  `pip install -r requirements.txt` on session start. I had to do this
  manually this session.
- `backend/backups/` (new, added this session) — intentionally excluded;
  data snapshots are not code and Mongo dumps of customer data shouldn't
  live in a public/private git history either.
- Local Mongo data (`/data/db`) — never touched by git, correct.

## 9. Product catalog recovery — investigation result

**Searched for:** Mongo dumps, `.bson` files, `products.json` exports,
cached collections, prior import JSON outputs, source Excel/PDF files, image
mappings. Result: **no local dump, no export, no cached JSON with full
product rows exists anywhere in this container.** `/app/memory/*.json`
reports (`vitra_qa_report.json`, `import_final_tally.json`, etc.) only
contain **aggregate counts and certification scores** — not the underlying
row data — so they cannot be used to reconstruct the catalog by themselves.

**One real lead, and it's a good one:** `/app/memory/media_migration_
20260704_202102.json` proves that on 2026-07-04, **250 VITRA product images
(1.97 MB) were successfully uploaded to Supabase** (`migrated: 250,
would_migrate: 0`, zero failures). I confirmed live just now that the
Supabase project referenced everywhere in this repo's tooling
(`https://vburaxruvbnbahegtbya.supabase.co`, project ref
`vburaxruvbnbahegtbya`) **is still alive and answering Supabase Storage API
requests right now** (got a real Supabase gateway response with
`sb-project-ref` header, not a DNS failure). This means:
- The 250 Vitra image *files* are very likely still sitting in that
  project's `forge-products` bucket, untouched by any of this container's
  resets (Supabase storage is external — it doesn't care what happens to
  our pod).
- Storage keys are **content-addressed** (`<brand>/<family_or_product>/
  <source>/<role>-<sha1[:12]>.<ext>`) — NOT tied to any MongoDB `_id`. That
  means if we re-run the Vitra import against the *original source XLSX*,
  the images will hash to the exact same keys and the upload call is a
  no-op (idempotent upsert) — the pointer metadata in `product_media` just
  gets recreated, no re-upload needed, no risk of duplication.
- **What's still missing to actually recover anything:** (a) the
  `SUPABASE_SERVICE_ROLE_KEY` for that project (only redacted placeholders
  exist in `/app/memory/iteration_2a_certification.md`), and (b) the
  original supplier source files for Vitra/Grohe/Geberit (the actual product
  names/prices/specs/SKUs — none of these were found on disk; they must have
  been uploaded by the user via the catalog-import UI in a prior session and
  never saved anywhere durable after processing).

**Bottom line:** the *images* Vitra migrated to Supabase are probably
recoverable with the right key. The *product records* (names, SKUs, prices,
1,610 rows across Vitra/Grohe/Geberit) are **not recoverable from anything
in this container** — they only ever existed in the ephemeral local Mongo.
The only paths back to a full catalog are: (a) re-upload the original
supplier PDFs/Excel files and re-run the existing, working import pipeline
(recommended — it's fast, deterministic, and already proven at 96–99%
certification scores), or (b) if a real Mongo Atlas backup/dump exists
somewhere outside this container (e.g. on your own machine, an old Atlas
cluster, a previous export you saved), restore from that instead.

## 10. Runtime assets that must never live inside the container again
- **MongoDB data** → MongoDB Atlas (persistent, external, already the app's
  only supported target once `MONGO_URL` is a `mongodb+srv://` string —
  `backend/db.py` has zero code changes to make, it already just reads
  `MONGO_URL`/`DB_NAME` from the environment).
- **Product images / PDFs / documents / attachments** → Supabase Storage
  (architecture already built and already used correctly by
  `catalog_pipeline` + `media_service.py` — it just needs live credentials
  every session).
- **Secrets** (`MONGO_URL`, `SUPABASE_*`, `JWT_SECRET`) → must be re-supplied
  every session via `scripts/setup-env --from-env` (or interactively) — this
  repo already has that script, it's just never invoked automatically. There
  is no in-platform secret vault available to this agent; the durable place
  for the actual secret values is outside this container (your password
  manager / notes), and `scripts/setup-env` is the fast (<1 minute) path back
  from there into a working `.env`.
- **Backups** (`backend/scripts/backup_db.py` output) → should be pushed to a
  private Supabase bucket or downloaded, not left on local disk, once
  Supabase is wired up (currently they land in `backend/backups/`, gitignored,
  same ephemeral disk as everything else — fine as a same-session safety net,
  not a real disaster-recovery target yet).

---

## Two persistence-threatening gaps fixed this session (infra hygiene only, no feature work)
1. **Backend Python deps had no auto-restore path.** `requirements.txt` is
   committed, but nothing reinstalls it on a fresh pod (`/root/.venv` isn't
   git-tracked and no restart hook exists). I ran `pip install -r
   requirements.txt` manually to unblock this session. **Recommended
   permanent fix:** add a `pip install -r backend/requirements.txt` line to
   `/root/.emergent/on-restart.sh` (the hook `entrypoint.sh` already looks
   for and runs — it just doesn't exist yet in this repo/pod image).
2. **No automatic `.env` bootstrap.** Recreated both `.env` files for this
   session (local Mongo, fresh JWT secret) so the app is healthy again, and
   added `backend/.env.example` / `frontend/.env.example` (safe, secret-free
   templates) to git so `scripts/setup-env`'s expectations are documented
   in-repo. Added `GET /api/health/system` (no auth, never returns secret
   values) that reports mongo/supabase reachability, `is_local` warning,
   live collection counts, and which required secrets are actually loaded —
   so the very first thing anyone does in a new session is get an honest
   answer to "is this pointed at real, persistent infrastructure, or a
   fresh, empty container?" Also added `backend/scripts/backup_db.py` /
   `restore_db.py` (JSON snapshot export/import, idempotent) as a
   same-session safety net.

## What is required from you to close this permanently
Nothing further will be built until you decide — this is intentionally left
as a decision point, not an assumption:
1. A MongoDB **Atlas** connection string (existing cluster, or I can walk you
   through creating a free M0 cluster in ~5 minutes) to replace the local
   Mongo in `backend/.env` permanently.
2. The Supabase **service role key** and **anon key** for project
   `vburaxruvbnbahegtbya` (confirmed still alive) — or a new Supabase
   project if you no longer have access to that one.
3. A decision on the catalog: re-upload the original Vitra/Grohe/Geberit
   source files to re-run the (already working) import pipeline, or point me
   at an existing backup/export if one exists outside this container.

# Forge Recovery Procedure

## Why local `.env` files disappear

Emergent preview runs in an ephemeral Kubernetes container. Workspace files excluded from the persisted project snapshot by `.gitignore`—including populated `.env` files—are not restored when that container is recreated. This is persistence-by-design in preview, not Forge deleting the files. Supervisor injects only platform runtime values and cannot recover MongoDB/Supabase secrets that were stored solely in the old container.

Deployed applications support persistent environment variables through deployment settings. Agents cannot configure platform-level persistent secrets for preview. Therefore application code can eliminate silent/crash-loop failure and prefer persistent process secrets, but it cannot make a preview-only secret persist across container recreation.

## Production recovery

1. Open the deployment environment settings.
2. Configure every variable listed in `STARTUP_CHECK.md` from the approved password manager.
3. Restart/redeploy using the Emergent Publish workflow.
4. Run `python backend/bootstrap.py` in the runtime environment.
5. Confirm the post-start check:

```bash
cd /app/backend
python bootstrap.py --health-url http://127.0.0.1:8001/api/health
```

6. Confirm `GET /api/health/system` reports MongoDB and Supabase connected and the expected catalog count.
7. If data counts are wrong, stop. Do not seed over production. Use the documented Supabase backup restore flow.

## Preview/local recovery

Preview cannot persist custom secrets. Supply them to the current runtime and generate the ignored fallback file through the existing guarded script:

```bash
cd /app
MONGO_URL='...' DB_NAME='...' JWT_SECRET='...' \
SUPABASE_URL='...' SUPABASE_SERVICE_ROLE_KEY='...' SUPABASE_ANON_KEY='...' \
SUPABASE_PUBLIC_BUCKET='...' SUPABASE_PRIVATE_BUCKET='...' \
scripts/setup-env --from-env
sudo supervisorctl restart backend expo
```

Then run both bootstrap commands above. Never commit the populated `.env` file.

## Failure interpretation

- `Missing or placeholder configuration`: deployment secret absent or local fallback incomplete.
- `MongoDB connection failed`: URI, Atlas network access, DNS, or credentials issue.
- `missing required collections`: likely wrong `DB_NAME` or incomplete restore. Do not create production collections blindly.
- `missing required indexes`: review the reported signatures before applying an index migration.
- `Supabase connection failed`: project URL/key invalid or network unavailable.
- `missing required buckets`: create/restore the named buckets before starting Forge.
- Health endpoint failure: inspect backend startup logs; do not route traffic until preflight is green.

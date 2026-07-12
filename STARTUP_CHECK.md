# Forge Startup Configuration

Forge reads production configuration from process environment variables. `backend/.env` is an optional local/preview fallback loaded with `override=False`; it never replaces platform-injected values.

## Required backend variables

| Variable | Purpose | Validation |
|---|---|---|
| `MONGO_URL` | MongoDB Atlas connection | Must start with `mongodb://` or `mongodb+srv://`; no whitespace |
| `DB_NAME` | Production database | Non-empty, no whitespace |
| `JWT_SECRET` | Signs staff/customer sessions | At least 32 characters |
| `SUPABASE_URL` | Storage project | Valid HTTPS URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side storage administration | Complete value; never exposed to frontend |
| `SUPABASE_ANON_KEY` | Public storage/client-safe operations | Complete value |
| `SUPABASE_PUBLIC_BUCKET` | Product images | Bucket must exist |
| `SUPABASE_PRIVATE_BUCKET` | Backups/private files | Bucket must exist |

## Optional variables with safe defaults

| Variable | Default |
|---|---|
| `JWT_ALGORITHM` | `HS256` |
| `JWT_EXP_MINUTES` | `43200` (30 days) |
| `MEDIA_STORAGE_DRIVER` | `supabase` (only supported production driver) |

## Frontend

`EXPO_PUBLIC_BACKEND_URL` should be empty for the Emergent preview and same-origin web deployment because `/api/*` is routed by ingress. Never hardcode localhost or a preview hostname in application code.

## Startup sequence

1. `settings.py` loads process values, then optional local fallback values without overriding the process.
2. Invalid or placeholder configuration raises a descriptive `ConfigurationError` before Mongo/auth clients are created.
3. FastAPI startup runs the infrastructure preflight before reporting ready.
4. `bootstrap.py` checks MongoDB, Supabase, required buckets, collections, and existing indexes.
5. After Uvicorn starts, run the post-start health check:

```bash
cd /app/backend
python bootstrap.py --health-url http://127.0.0.1:8001/api/health
```

The script returns exit code 0 only when every requested check passes. It never prints secret values and does not create indexes silently.

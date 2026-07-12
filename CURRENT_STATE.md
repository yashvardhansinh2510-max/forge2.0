# Current State

- Production architecture remains FastAPI + Expo/React Native Web + MongoDB Atlas + Supabase Storage.
- Catalog baseline from the last verified persistent environment is 2,966 products and 2,970 media records.
- The current preview container lost ignored `.env` files during recreation; this is an ephemeral-preview persistence limitation.
- Infrastructure hardening is complete and backend-testing-agent verified: process environment is authoritative, local `.env` is fallback-only, and startup is gated by a green preflight.
- The official quotation reference PDF is available for the later PDF task.

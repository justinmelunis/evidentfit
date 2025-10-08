# EvidentFit Web (Next.js)

Static-exported Next.js app for research chat, stack planner, and supplement database.

## Quick start
```bash
cd web/evidentfit-web
npm install
# Point to API
set NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev
```

## Build & export
```bash
# Production build
npm run build
npm run export
# Output in out/
```

## Pages
- `src/app/page.tsx` — landing
- `src/app/agent/page.tsx` — research chat
- `src/app/stack-chat/page.tsx` — conversational stack planner
- `src/app/supplements/page.tsx` — supplement database (Level 1 evidence)
- `src/app/methodology/page.tsx` — public methodology

## Config
- `NEXT_PUBLIC_API_BASE` must point to the API base URL

## Common pitfalls
- `NEXT_PUBLIC_API_BASE` not set → pages call undefined API; set it before `npm run dev`
- CORS blocked in browser → ensure API `CORS_ALLOW_ORIGINS` includes your dev origin
- Using https API from http dev server → mixed content; prefer http://localhost:8000 in dev

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## PDF plan → JSON → IFC (Phase 1)

Upload a structural steel **PDF** (2D plans with a text layer works best in this phase):

```bash
pip install -r requirements.txt
uvicorn analyzer_service.main:app --reload --host 127.0.0.1 --port 8011
```

| Endpoint | Purpose |
|----------|---------|
| `POST /api/pdf-to-structural-json` | PDF → `PureStructuralModelSpec` JSON + validation report |
| `POST /api/pdf-to-ifc` | PDF → validated JSON → IFC bytes |
| `POST /api/validate-structural-json` | Validate hand-edited JSON before export |

## PDF region crop → analyze → 3D (PWA)

Open [http://localhost:3000/plan-crop](http://localhost:3000/plan-crop) with the same Python service on port **8011**.

| Endpoint | Purpose |
|----------|---------|
| `POST /upload-pdf` | PDF → per-page PNG gallery (`GET /assets/pdf-projects/...`) |
| `POST /analyze-region` | Cropped PNG → structured region analysis (grid / truss / mezzanine / staircase) |
| `POST /api/region-to-intent-preview` | Analysis + overrides → `UniversalStructuralIntent` JSON |
| `POST /api/intent-to-ifc` | Approved intent → IFC bytes (grid_frame_compiler) |
| `POST /api/validate-universal-intent` | Validate intent before IFC export |

Staircase is detected by vision but 3D compilation is not supported yet. Env: `PDF_PROJECTS_ROOT`, `PDF_PROJECT_DPI`.

**Plan crop** (`POST /analyze-region`): when `project_id`, `page_index`, and `crop_rect_norm` are sent, the server reads **PDF dimension text + grid vectors** from `source.pdf` and merges them with **Claude vision** (profiles/sparse columns). Vision-only if no project PDF. Env: `ANTHROPIC_API_KEY`, `REGION_VISION_MODEL`, `PDF_PROJECTS_ROOT`.

Form fields (optional): `scale_note`, `hints` (e.g. `1:100`, grid origin).

Set `PDF_EXTRACT_SKIP_LLM=1` to ingest text only (no OpenAI) while testing parsers.

Later phases will add vector geometry + vision on raster sheets; IFC generation already uses the same `PureStructuralModelSpec` path as chat-to-IFC.

## AI Designer (Chat-to-IFC)

1. Install Python dependencies and start the analyzer / chat-to-IFC API:

```bash
cd eyesteel
pip install -r requirements.txt
uvicorn analyzer_service.main:app --reload --host 0.0.0.0 --port 8000
```

2. Set `OPENAI_API_KEY` in your shell or a `.env` file in `eyesteel/` (see `.env.local.example`).

3. Copy `.env.local.example` to `.env.local` for the Next.js app (optional; defaults to `http://localhost:8000`).

4. Run Next.js (see below) and open [http://localhost:3000/ai-designer](http://localhost:3000/ai-designer).

Describe the structure with dimensions and elevations. The API uses **Pure Vector** extraction (`PureStructuralModelSpec`): each steel member is a 3D line segment + profile; the compiler is blind to words like roof/truss/mezzanine. IFC column vs beam is inferred from geometry only.

Legacy grid-frame compilation remains for tests (`PURE_VECTOR_LEGACY_GRID=1`).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

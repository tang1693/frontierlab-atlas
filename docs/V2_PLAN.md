# FrontierLab Atlas V2 Plan — Scholar Citation Geography

## Goal
Allow users to input a Google Scholar profile URL and visualize where citing papers come from (institutions/countries/cities) on the map.

Target load: ~100 users/day.

---

## Product Scope (V2)

### Input
- Google Scholar profile URL (e.g. `https://scholar.google.com/citations?user=...`)

### Output
- Geographic distribution of citing papers
- Top citing institutions / countries
- Time trend (recent vs historical)
- Map markers + ranked list for "labs to follow"

### UX Modes
1. **Quick Scan** (10–30s): sampled/limited result for fast preview
2. **Deep Scan** (async job): full result with progress + completion notice

---

## Data Strategy (Important)

### Do NOT rely on direct Scholar scraping for production
Reason: anti-bot limits, CAPTCHA, unstable service behavior, legal/compliance risks.

### Recommended production data sources
- **Primary:** OpenAlex
- **Secondary fallback:** Semantic Scholar (if needed)

Scholar URL acts as user-friendly entry point, not the core production data pipeline.

---

## High-Level Architecture

1. Parse Scholar URL -> extract `user` id
2. Resolve author identity (OpenAlex author candidate matching)
3. Fetch author works
4. Fetch papers that cite those works
5. Extract affiliations/institutions/countries from citing papers
6. Geocode institution -> lat/lon (cache-first)
7. Aggregate + rank + map render

### Async pipeline
- API receives request -> creates job
- Worker processes job in background
- Frontend polls `/jobs/{id}` status
- On completion, frontend loads map payload

---

## API Draft

- `POST /api/v2/scholar/jobs`
  - body: `{ scholar_url, mode: quick|deep, from_year?, to_year?, max_citing_works? }`
  - returns: `{ job_id, status }`

- `GET /api/v2/scholar/jobs/{job_id}`
  - returns status/progress/error

- `GET /api/v2/scholar/jobs/{job_id}/result`
  - returns map markers + aggregates

---

## Data Model (Draft)

- `scholar_jobs`
  - `job_id`, `status`, `created_at`, `finished_at`, `input_url`, `mode`, `error`
- `author_resolution_cache`
  - `scholar_user_id`, `openalex_author_id`, `confidence`, `updated_at`
- `author_works_cache`
  - `openalex_author_id`, `work_id`, `title`, `year`, `cached_at`
- `citing_works_cache`
  - `root_work_id`, `citing_work_id`, `year`, `cached_at`
- `institution_geo_cache`
  - `institution_id/name`, `country`, `lat`, `lon`, `status`, `updated_at`
- `job_result_aggregates`
  - `job_id`, `country`, `institution`, `count`, `weighted_score`

---

## Performance Plan for 100 users/day

- Queue-based execution (Celery/RQ)
- Hard caps by mode
  - Quick: `max_citing_works <= 2k`
  - Deep: `max_citing_works <= 20k` (configurable)
- Strong cache reuse (author/work/citing/institution geo)
- Daily refresh for hot authors
- Concurrency control per user/IP and per job size

Expected: 100 users/day is feasible with one modest VM if caching is effective.

---

## Risk Controls

- Avoid direct Scholar scraping in critical path
- Timeout + retry + circuit breaker on external APIs
- Persist partial progress to survive worker restart
- Geo cache prevents repeated geocoding spend
- Add abuse control (rate limits and job quotas)

---

## Delivery Milestones

### M1 (3–5 days)
- Job framework + API skeleton
- Scholar URL parser + author resolution MVP
- Quick Scan result with country-level map

### M2 (5–7 days)
- Deep Scan pipeline
- Institution-level map markers
- Ranked "labs to follow" panel

### M3 (3–5 days)
- Performance tuning + caching hardening
- Error handling and observability dashboard
- UX polish + docs

---

## Versioning / Rollback

- V1 baseline tag (local runtime): `v1.0-runtime`
- V2 development branch: `v2-dev`
- Rollback command (runtime repo):
  - `git checkout v1.0-runtime`
  - restart service

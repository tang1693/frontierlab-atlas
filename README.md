# FrontierLab Atlas: PhD Lab & Journal GeoNavigator

FrontierLab Atlas: PhD Lab & Journal GeoNavigator is a visual research-intelligence cockpit built for **new PhD students**.

Instead of spending weeks manually reading and mapping a field, you can quickly answer:

- **Which labs are active at the frontier of a topic?**
- **Where are those labs located globally?**
- **Which journals/preprints are shaping the conversation right now?**

### Why this is useful for PhD onboarding
- Start from a keyword and get a global lab map in minutes.
- Spot high-impact venues with IF/CIT signals at a glance.
- Move from “I’m new to this field” to a concrete reading + lab-target list fast.

## Screenshots

<p align="center">
  <img src="assets/screenshots/dashboard-overview.jpg" alt="FrontierLab Atlas dashboard overview" width="100%" />
</p>
<p align="center"><em>Global overview: map + paper stream + timeline + console in one workspace.</em></p>

<table>
  <tr>
    <td width="50%">
      <img src="assets/screenshots/sidebar-and-filters.jpg" alt="Sidebar, sort and filter panel" width="100%" />
      <p align="center"><em>Search workflow with sort/filter and IF/CIT signals.</em></p>
    </td>
    <td width="50%">
      <img src="assets/screenshots/map-paper-popup.jpg" alt="Map popup for paper details" width="100%" />
      <p align="center"><em>Geo marker popup with journal, institution, IF and citation info.</em></p>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="assets/screenshots/timeline-enlarged.jpg" alt="Enlarged timeline chart" width="100%" />
      <p align="center"><em>Enlarged timeline for publication density and trend reading.</em></p>
    </td>
  </tr>
</table>

---

## What it does

### 1) Two working modes
- **RADAR 1DAY**
  - Continuous monitoring mode
  - Starts with a 1-day window
  - Auto-fallback to 7-day window when too sparse
  - Countdown shown in UI

- **HISTORY**
  - One-shot retrieval mode
  - Time ranges: `7D`, `30D`, `90D`, `6M`, `1Y`, `2Y`
  - Large windows are fetched in **30-day chunks** with progress bar

### 2) Search logic
- Comma-separated query terms use **AND matching** on title/abstract.
- Example: `LLM, Agent` means both must match.

### 3) Quality + impact display
- Journal papers show **IF** (OpenAlex source proxy: `2yr_mean_citedness`)
- Preprints show **ARXIV**
- Citation badge (`CIT`) available
- Sort by Date / IF / Citation

### 4) Geo handling
- arXiv papers are excluded from geocoding pending queue
- Non-arXiv geocoding retries up to 2 times
- After 2 failures, status becomes `unknown` and is cached

### 5) Usability
- Import / Export JSON
- Import restores context (query/mode/days/filters)
- Numeric filters: IF min/max + Citation min/max
- Timeline enlarge modal

---

## Tech stack

- Python 3.10+
- Flask
- OpenAlex API (`works`, `sources`)
- Leaflet + Chart.js frontend
- Gunicorn (recommended production runtime)

Key files:
- `paper_app.py` — API + scan/geocode orchestration
- `paper_fetcher.py` — OpenAlex retrieval + relevance/IF enrichment
- `geocoder.py` — geocode/cache logic
- `templates/paper_earth.html` — UI and interaction logic

---

## Quick start (local)

```bash
cd frontierlab-atlas
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 paper_app.py
```

Open:
- `http://127.0.0.1:5000/`

### Security note (recommended)
- Keep the repository **Private** until all credentials are rotated.
- Never commit `.env` or real API keys.
- Use `.env.example` as template and keep real keys only in local `.env`.
- If this repo was ever public with real keys, rotate those keys immediately.

---

## Self-hosting: what others need to prepare

If someone else wants to host FrontierLab Atlas: PhD Lab & Journal GeoNavigator, prepare the following:

### A) Infrastructure
1. A Linux server (recommended: **2 vCPU / 4GB RAM** minimum)
2. Python 3.10+
3. Public domain (optional but recommended)
4. Reverse proxy + TLS (Caddy or Nginx)

### B) Required API setup (only 2)
1. **Geolocation API** (used by `geocoder.py`)
   - Register your own provider key
   - Set it via environment variable: `MAPS_CO_API_KEY`
2. **OpenAlex data API** (used by paper retrieval)
   - Ensure your deployment can access `api.openalex.org`
   - Configure your own OpenAlex contact/email policy if needed
3. Other API keys are optional and **not required** for the core FrontierLab Atlas flow.

### C) Network / external access
1. Outbound access to:
   - `api.openalex.org`
   - geocoding provider endpoints used by `geocoder.py`
2. Inbound routing to app (typically via reverse proxy)

### D) Runtime config
1. Use **Gunicorn + systemd** in production (do not use Flask debug mode)
2. Bind app to localhost (e.g. `127.0.0.1:5000`) behind reverse proxy
3. Ensure writable `data/` directory for cache files

### E) Security basics
1. Rotate any leaked tokens/keys immediately
2. Add basic auth or app auth for public deployments
3. Enable rate limit at gateway/reverse proxy
4. Keep service logs and monitor restart failures

### F) Optional quality-of-life
1. Daily backup for exported/imported user datasets
2. Cron/system job for service health checks
3. Alerting for 5xx spikes

---

## API

- `GET /api/papers?q=<query>&days=<n>&from=<YYYY-MM-DD>&to=<YYYY-MM-DD>&lite=0|1`
- `GET /api/papers/status`
- `GET /api/stats?days=<n>`
- `GET /api/default-seed`

---

## Attribution

- **Author:** OPENCLAW
- **Product direction / instruction:** Yang Tang

---

## License

Please align `LICENSE.md` to your intended release model before public launch.

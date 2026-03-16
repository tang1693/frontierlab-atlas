import os
import requests
import json
import time
import random
import re
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from geocoder import geocoder

# Load local .env when running directly (e.g., python paper_app.py)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# OpenAlex API Base URL
OPENALEX_API_URL = "https://api.openalex.org/works"
OPENALEX_SOURCE_API_URL = "https://api.openalex.org/sources"
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO", "").strip()

# Source IF proxy cache (persistent)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SOURCE_IF_CACHE_FILE = os.path.join(DATA_DIR, 'source_if_cache.json')
SOURCE_IF_CACHE = {}
_SOURCE_CACHE_DIRTY = False

# High-impact venue keywords (White List)
HIGH_IMPACT_KEYWORDS = [
    'IEEE', 'ACM', 'Springer', 'Nature', 'Science', 'Cell', 'Lancet',
    'NeurIPS', 'ICLR', 'CVPR', 'ICML', 'AAAI', 'ACL', 'ECCV', 'ICCV',
    'JAMA', 'BMJ', 'PNAS', 'Physical Review', 'Chemical Reviews'
]


def _load_source_if_cache():
    global SOURCE_IF_CACHE
    if SOURCE_IF_CACHE:
        return
    try:
        if os.path.exists(SOURCE_IF_CACHE_FILE):
            with open(SOURCE_IF_CACHE_FILE, 'r', encoding='utf-8') as f:
                SOURCE_IF_CACHE = json.load(f)
            print(f"[SourceIF] Loaded cache entries: {len(SOURCE_IF_CACHE)}")
        else:
            SOURCE_IF_CACHE = {}
    except Exception as e:
        print(f"[SourceIF] Cache load error: {e}")
        SOURCE_IF_CACHE = {}


def _save_source_if_cache(force=False):
    global _SOURCE_CACHE_DIRTY
    if not _SOURCE_CACHE_DIRTY and not force:
        return
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SOURCE_IF_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(SOURCE_IF_CACHE, f, ensure_ascii=False, indent=2)
        _SOURCE_CACHE_DIRTY = False
    except Exception as e:
        print(f"[SourceIF] Cache save error: {e}")


def _source_key(source_id):
    if not source_id:
        return None
    return source_id.rsplit('/', 1)[-1]


def _get_source_if_proxy(source_id):
    """
    Fetch IF-proxy from source endpoint.
    Uses OpenAlex source.summary_stats.2yr_mean_citedness as proxy.
    """
    global _SOURCE_CACHE_DIRTY

    sid = _source_key(source_id)
    if not sid:
        return None

    _load_source_if_cache()

    if sid in SOURCE_IF_CACHE:
        cached = SOURCE_IF_CACHE[sid]
        try:
            return float(cached) if cached is not None else None
        except Exception:
            return None

    metric = None
    try:
        res = requests.get(f"{OPENALEX_SOURCE_API_URL}/{sid}", timeout=12)
        if res.status_code == 200:
            src = res.json() or {}
            stats = src.get('summary_stats') or {}
            raw = stats.get('2yr_mean_citedness')
            if raw is not None:
                metric = round(float(raw), 2)
    except Exception as e:
        print(f"[SourceIF] Fetch error sid={sid}: {e}")

    SOURCE_IF_CACHE[sid] = metric
    _SOURCE_CACHE_DIRTY = True
    return metric


def _build_abstract_text(work):
    """Reconstruct abstract from OpenAlex inverted index."""
    idx = work.get('abstract_inverted_index')
    if not idx:
        return ""

    words = [None] * 800
    for word, positions in idx.items():
        for pos in positions:
            if 0 <= pos < len(words):
                words[pos] = word
    return " ".join([w for w in words if w is not None])


def _derive_published_utc(work):
    """
    Build UTC publication timestamp text.
    OpenAlex usually has date-level publication_date, so default to 00:00:00 UTC.
    If created_date has same date prefix, reuse its time component.
    """
    pub_date = work.get('publication_date')
    if not pub_date:
        return None

    created = (work.get('created_date') or '').strip()
    if created.startswith(pub_date) and 'T' in created:
        time_part = created.split('T', 1)[1]
        time_part = time_part.split('.', 1)[0]
        return f"{pub_date} {time_part} UTC"

    return f"{pub_date} 00:00:00 UTC"


def _is_within_last_24h(published_utc_text):
    """Strict 24h check for radar mode."""
    if not published_utc_text:
        return False
    try:
        # expected format: YYYY-MM-DD HH:MM:SS UTC
        dt = datetime.strptime(published_utc_text, '%Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
        return dt >= (datetime.now(timezone.utc) - timedelta(hours=24))
    except Exception:
        return False


def _keyword_hit(title, abstract_text, keywords):
    """
    Relevance guard (AND mode): all keywords must hit title or abstract.
    - For short tokens (<=3): word-boundary match
    - For longer terms/phrases: substring match
    """
    if not keywords:
        return True

    text = f"{title or ''} {abstract_text or ''}".lower()
    if not text.strip():
        return False

    required_terms = [(kw or '').strip().lower() for kw in keywords if (kw or '').strip()]
    if not required_terms:
        return True

    for term in required_terms:
        # Phrase term (contains spaces): direct phrase match
        if ' ' in term:
            matched = term in text
        else:
            # Single token term: strict word boundary match
            matched = re.search(rf"\b{re.escape(term)}\b", text) is not None

        if not matched:
            return False

    return True


def _fetch_source_works(source_filter, query_str, max_pages=6, per_page=200):
    """Fetch works page-by-page from one source filter."""
    works = []

    # OpenAlex per-page max is 200
    per_page = max(1, min(per_page, 200))

    for page in range(1, max_pages + 1):
        params = {
            "filter": source_filter,
            "search": query_str,
            "per-page": per_page,
            "page": page,
            "sort": "publication_date:desc"
        }
        if OPENALEX_MAILTO:
            params["mailto"] = OPENALEX_MAILTO

        res = requests.get(OPENALEX_API_URL, params=params, timeout=25)
        res.raise_for_status()
        batch = res.json().get('results', [])

        if not batch:
            break

        works.extend(batch)
        print(f"    page {page}: +{len(batch)}")

        # Last page
        if len(batch) < per_page:
            break

        time.sleep(0.15)

    return works


def fetch_recent_papers(keywords=["LLM", "Agent"], days_back=7, from_date=None, to_date=None):
    """
    Fetch recent papers from OpenAlex based on keywords and recency.

    New behavior:
    1) No fixed hard cap like 50+50
    2) Relevance guard: keyword must hit title/abstract
    3) Keep dual-source strategy (arXiv + core)
    """

    _load_source_if_cache()

    # Date filter: explicit range if provided, otherwise last N days
    if from_date and to_date:
        pass
    else:
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        to_date = datetime.utcnow().strftime('%Y-%m-%d')

    # Multi-tag support (comma keeps phrase groups)
    if isinstance(keywords, str):
        raw_query = keywords.strip()
        if ',' in raw_query:
            keywords = [k.strip() for k in raw_query.split(',') if k.strip()]
        else:
            keywords = [k.strip() for k in raw_query.split() if k.strip()]

    # Use compact query for OpenAlex recall, then enforce strict AND locally
    query_str = " ".join(keywords)

    # Strategy: Fetch arXiv + Core papers separately and merge
    # arXiv source ID: S4306400194
    arxiv_filter = (
        f"from_publication_date:{from_date},"
        f"to_publication_date:{to_date},"
        f"primary_location.source.id:S4306400194"
    )
    core_filter = (
        f"from_publication_date:{from_date},"
        f"to_publication_date:{to_date},"
        f"primary_location.source.is_core:true"
    )

    # Safety page budget (not fixed result count; prevents runaway queries)
    if days_back <= 7:
        max_pages = 2
    elif days_back <= 30:
        max_pages = 4
    elif days_back <= 90:
        max_pages = 8
    else:
        max_pages = 12

    print(f"[Config] days={days_back}, page_budget={max_pages}, query={query_str}")

    all_papers = []
    seen_ids = set()

    # Fetch arXiv papers
    print("[1/2] Fetching arXiv papers...")
    try:
        arxiv_works = _fetch_source_works(arxiv_filter, query_str, max_pages=max_pages)
        print(f"  → Raw arXiv papers: {len(arxiv_works)}")
        for work in arxiv_works:
            work_id = work.get('id')
            if work_id and work_id not in seen_ids:
                all_papers.append(work)
                seen_ids.add(work_id)
    except Exception as e:
        print(f"  ⚠️ arXiv fetch failed: {e}")

    # Fetch Core papers
    print("[2/2] Fetching Core papers...")
    try:
        core_works = _fetch_source_works(core_filter, query_str, max_pages=max_pages)
        print(f"  → Raw core papers: {len(core_works)}")
        for work in core_works:
            work_id = work.get('id')
            if work_id and work_id not in seen_ids:
                all_papers.append(work)
                seen_ids.add(work_id)
    except Exception as e:
        print(f"  ⚠️ Core fetch failed: {e}")

    # Sort by date desc
    all_papers.sort(key=lambda x: x.get('publication_date', ''), reverse=True)

    print(f"Total unique papers before relevance filter: {len(all_papers)}")

    papers = []
    rejected_irrelevant = 0

    for work in all_papers:
        # Extract source info for display
        primary_loc = work.get('primary_location') or {}
        source = primary_loc.get('source') or {}
        source_id = source.get('id') or ""
        source_name = source.get('display_name') or ""

        # Identify paper type
        is_arxiv = 'S4306400194' in source_id or 'arxiv' in source_name.lower()

        # Extract basic info
        paper_id = work.get('id')
        title = work.get('display_name') or work.get('title') or "Untitled"
        date = work.get('publication_date')
        url = work.get('doi') or work.get('ids', {}).get('openalex')
        published_utc = _derive_published_utc(work)

        # Radar mode uses API date-window filtering (days_back) directly.
        # Do not apply extra strict 24h timestamp cutoff here,
        # otherwise many domains may return zero papers.

        abstract_text = _build_abstract_text(work)

        # Relevance gate: keyword must be in title or abstract
        if not _keyword_hit(title, abstract_text, keywords):
            rejected_irrelevant += 1
            continue

        # Geocoding / Institution logic
        lab_name = "Unknown Lab"
        lat = None
        lon = None
        institution_id = None
        institution_country = None

        authorships = work.get('authorships', [])
        if authorships:
            for author in authorships:
                institutions = author.get('institutions', [])
                if institutions:
                    inst = institutions[0]
                    lab_name = inst.get('display_name') or "Unknown Lab"
                    institution_id = inst.get('id')
                    institution_country = inst.get('country_code')
                    break

        cited_by = work.get('cited_by_count', 0)

        # Journal IF-like metric from Source endpoint (no randomness)
        # Note: OpenAlex doesn't provide Clarivate JIF directly; use 2yr_mean_citedness as IF proxy.
        impact_factor = None if is_arxiv else _get_source_if_proxy(source.get('id'))

        # Backward-compatible numeric score for color buckets (deterministic)
        # Use IF-proxy directly and cap to 10 for old score-based UI paths.
        if is_arxiv:
            impact_score = 0
        else:
            impact_score = min(10, impact_factor if impact_factor is not None else 0)

        # Extract additional metrics
        author_count = len(work.get('authorships', []))
        is_open_access = work.get('open_access', {}).get('is_oa', False)
        pub_year = work.get('publication_year')

        papers.append({
            "id": paper_id,
            "title": title,
            "summary": (abstract_text[:300] + "...") if abstract_text else "No abstract available.",
            "published_utc": published_utc,
            "lab": lab_name,
            "lat": lat,
            "lon": lon,
            "impact_score": impact_score,
            "impact_factor": impact_factor,
            "impact_label": "ARXIV" if is_arxiv else (f"IF {impact_factor:.2f}" if impact_factor is not None else "IF N/A"),
            "url": url,
            "date": date,
            "institution_id": institution_id,
            "institution_country": institution_country,
            "institution_city": None,
            "source": source_name,
            "is_arxiv": is_arxiv,
            "cited_by": cited_by,
            "author_count": author_count,
            "is_open_access": is_open_access,
            "pub_year": pub_year
        })

    print(f"Relevance rejected: {rejected_irrelevant}")
    print(f"Final papers returned: {len(papers)}")
    _save_source_if_cache()
    return papers


def enrich_with_geocoding(papers):
    """
    Fill in lat/lon for papers using the centralized SmartGeocoder.
    """
    for p in papers:
        inst_id = p.get('institution_id')
        inst_name = p.get('lab')
        country = p.get('institution_country')

        # Get coordinates from our robust geocoder
        lat, lon, source, city = geocoder.get_coordinates(inst_id, inst_name, country)

        p['lat'] = lat
        p['lon'] = lon
        p['institution_city'] = city

        # Add slight jitter for visualization (unless it's country fallback)
        if lat is not None and lon is not None and lat != 0 and lon != 0 and source != "country_fallback":
            p['lat'] += random.uniform(-0.0005, 0.0005)
            p['lon'] += random.uniform(-0.0005, 0.0005)

    return papers


if __name__ == "__main__":
    # Test run
    papers = fetch_recent_papers(keywords=["Large Language Model", "Autonomous Agent"])
    papers = enrich_with_geocoding(papers)
    print(json.dumps(papers[:2], indent=2))

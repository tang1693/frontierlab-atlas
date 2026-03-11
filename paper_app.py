import os
import json
import time
import threading
from flask import Flask, render_template, jsonify, request
from paper_fetcher import fetch_recent_papers
from geocoder import geocoder

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEODATA_DIR = os.path.join(BASE_DIR, 'geodata')
DATA_DIR = os.path.join(BASE_DIR, 'data')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'paper-sentinel-secret'

# Global state for async geocoding
geocoding_state = {
    "status": "idle",  # idle | running | completed
    "total": 0,
    "completed": 0,
    "papers": [],
    "request_id": None,
    "lock": threading.Lock()
}

COUNTRY_NAME_MAP = {
    'US': 'United States',
    'CN': 'China',
    'GB': 'United Kingdom',
    'CA': 'Canada',
    'AU': 'Australia',
    'DE': 'Germany',
    'FR': 'France',
    'JP': 'Japan',
    'KR': 'South Korea',
    'IN': 'India',
    'RU': 'Russia',
    'BR': 'Brazil',
    'SG': 'Singapore',
    'CH': 'Switzerland',
    'NL': 'Netherlands',
    'SE': 'Sweden',
    'IL': 'Israel',
    'IT': 'Italy',
    'ES': 'Spain',
    'HK': 'Hong Kong SAR',
    'TW': 'Taiwan'
}


def country_code_to_flag(code: str):
    if not code or len(code) != 2:
        return '🏳️'
    code = code.upper()
    return chr(0x1F1E6 + ord(code[0]) - ord('A')) + chr(0x1F1E6 + ord(code[1]) - ord('A'))

@app.route('/')
@app.route('/earth')
def earth():
    return render_template("paper_earth.html")

@app.route('/api/papers')
def get_papers():
    """
    API Endpoint to fetch latest papers.
    Returns immediately with cached coordinates, triggers background geocoding for missing ones.
    """
    keyword_param = request.args.get('q', 'LLM OR "Generative AI"')
    days_param = request.args.get('days', '30')
    from_param = request.args.get('from')
    to_param = request.args.get('to')
    lite_mode = request.args.get('lite', '0') == '1'
    
    raw_query = (keyword_param or '').strip()
    if ',' in raw_query:
        # Comma means explicit multi-term query (supports phrases)
        keywords = [k.strip() for k in raw_query.split(',') if k.strip()]
    else:
        # Fallback: whitespace terms
        keywords = [k.strip() for k in raw_query.split() if k.strip()]

    if not keywords:
        keywords = ["LLM"]
    
    try:
        days_back = int(days_param)
    except ValueError:
        days_back = 30
        
    print(f"[API] Fetching papers for keywords: {keywords}, days_back: {days_back}")
    
    try:
        # Fetch paper metadata (fast)
        papers = fetch_recent_papers(
            keywords=keywords,
            days_back=days_back,
            from_date=from_param,
            to_date=to_param
        )
        
        # Quick pass: fill in cached coordinates / city
        papers_with_cache = []
        papers_need_geo = []
        papers_need_city = []

        for p in papers:
            inst_id = p.get('institution_id')
            inst_name = p.get('lab')

            # ArXiv papers should never enter pending geocoding queue
            if p.get('is_arxiv', False):
                p['lat'] = None
                p['lon'] = None
                p['institution_city'] = None
                p['geo_status'] = 'arxiv'
                papers_with_cache.append(p)
                continue

            cache_key = inst_id if inst_id else f"name:{inst_name}"
            if cache_key and cache_key in geocoder.cache:
                entry = geocoder.cache[cache_key]
                p['lat'] = entry.get('lat')
                p['lon'] = entry.get('lon')
                p['institution_city'] = entry.get('city')

                # Unknown cache means permanent give-up (don't retry)
                if entry.get('status') == 'unknown' or (p['lat'] is None and p['lon'] is None):
                    p['geo_status'] = 'unknown'
                else:
                    p['geo_status'] = 'cached'
                    # City label enrichment task (for cached entries without city)
                    if (not p.get('institution_city')) and p.get('lat') is not None and p.get('lon') is not None:
                        papers_need_city.append(p)
            else:
                p['lat'] = None
                p['lon'] = None
                p['institution_city'] = None
                if lite_mode:
                    p['geo_status'] = 'unknown'
                else:
                    p['geo_status'] = 'pending'
                    papers_need_geo.append(p)

            papers_with_cache.append(p)

        if lite_mode:
            papers_need_city = []

        total_tasks = len(papers_need_geo) + len(papers_need_city)

        # Update global state (new request generation)
        request_id = time.time_ns()
        with geocoding_state["lock"]:
            geocoding_state["papers"] = papers_with_cache
            geocoding_state["total"] = total_tasks
            geocoding_state["completed"] = 0
            geocoding_state["status"] = "running" if total_tasks > 0 else "completed"
            geocoding_state["request_id"] = request_id

        # Trigger background geocoding + city enrichment
        if total_tasks > 0:
            threading.Thread(
                target=background_geocode,
                args=(papers_need_geo, papers_need_city, request_id),
                daemon=True
            ).start()

        return jsonify({
            "papers": papers_with_cache,
            "geo_pending": len(papers_need_geo),
            "city_pending": len(papers_need_city),
            "request_id": request_id
        })
        
    except Exception as e:
        print(f"[API] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/papers/status')
def get_geocoding_status():
    """
    Returns current geocoding progress and newly resolved coordinates.
    """
    with geocoding_state["lock"]:
        return jsonify({
            "status": geocoding_state["status"],
            "total": geocoding_state["total"],
            "completed": geocoding_state["completed"],
            "request_id": geocoding_state.get("request_id"),
            "papers": geocoding_state["papers"]
        })

@app.route('/api/default-seed', methods=['GET'])
def get_default_seed():
    """
    Optional startup dataset for UI warm-start.
    Return 200 with empty payload when no seed file exists (avoid frontend 404 noise).
    """
    candidates = [
        os.path.join(DATA_DIR, 'default_seed.json'),
        os.path.join(DATA_DIR, 'default_seed_papers.json')
    ]

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            papers = payload if isinstance(payload, list) else (payload.get('papers') or [])
            if not isinstance(papers, list):
                papers = []
            return jsonify({
                'papers': papers,
                'mode': (payload.get('mode') if isinstance(payload, dict) else 'history') or 'history',
                'days': (payload.get('days') if isinstance(payload, dict) else 30) or 30,
                'query': (payload.get('query') if isinstance(payload, dict) else 'LLM, Agent') or 'LLM, Agent'
            })
        except Exception as e:
            return jsonify({'error': 'default_seed_read_failed', 'message': str(e)}), 500

    return jsonify({'papers': [], 'mode': 'history', 'days': 30, 'query': 'LLM, Agent'})


@app.route('/api/stats')
def get_statistics():
    """
    Returns aggregated statistics for dashboard visualization.
    Supports `days` filter and excludes future dates.
    """
    with geocoding_state["lock"]:
        papers = geocoding_state["papers"]

    try:
        days_back = int(request.args.get('days', '30'))
    except ValueError:
        days_back = 30
    days_back = max(1, min(days_back, 3650))

    if not papers:
        return jsonify({
            "papers_by_date": {},
            "top_countries": [],
            "top_labs": [],
            "impact_distribution": {},
            "total_papers": 0,
            "days": days_back
        })

    from collections import Counter
    from datetime import datetime, timedelta

    today = datetime.utcnow().date()
    cutoff = today - timedelta(days=days_back)

    # Filter by valid date window: cutoff <= date <= today
    filtered_papers = []
    for p in papers:
        d = p.get('date')
        if not d:
            continue
        try:
            pd = datetime.strptime(d, '%Y-%m-%d').date()
        except Exception:
            continue
        if pd > today:
            continue  # remove future dates
        if pd < cutoff:
            continue
        filtered_papers.append(p)

    # 1. Papers by Date (for timeline chart)
    papers_by_date = Counter()
    for p in filtered_papers:
        papers_by_date[p['date']] += 1

    # Sort by date
    sorted_dates = sorted(papers_by_date.items(), key=lambda x: x[0])

    # 2. Top Countries (merge Taiwan into China)
    countries = Counter()
    for p in filtered_papers:
        country = (p.get('institution_country') or '').upper().strip()
        if not country:
            continue
        if country == 'TW':
            country = 'CN'
        countries[country] += 1

    top_countries = countries.most_common(10)

    # 3. Top Labs
    labs = Counter()
    for p in filtered_papers:
        lab = p.get('lab')
        if lab and lab != 'Unknown Lab':
            labs[lab] += 1
    top_labs = labs.most_common(10)

    # 4. Impact Distribution (IF-based)
    impact_dist = Counter()
    for p in filtered_papers:
        if p.get('is_arxiv'):
            impact_dist['ArXiv'] += 1
            continue

        iff = p.get('impact_factor')
        try:
            iff = float(iff) if iff is not None else None
        except Exception:
            iff = None

        if iff is None:
            impact_dist['IF N/A'] += 1
        elif iff >= 10:
            impact_dist['IF High (>=10)'] += 1
        elif iff >= 5:
            impact_dist['IF Medium (5-10)'] += 1
        else:
            impact_dist['IF Low (<5)'] += 1

    return jsonify({
        "papers_by_date": dict(sorted_dates),
        "top_countries": [
            {
                "country": c,
                "country_name": COUNTRY_NAME_MAP.get(c, c),
                "flag": country_code_to_flag(c),
                "count": n
            }
            for c, n in top_countries
        ],
        "top_labs": [{"lab": l, "count": n} for l, n in top_labs],
        "impact_distribution": dict(impact_dist),
        "total_papers": len(filtered_papers),
        "days": days_back
    })

def background_geocode(papers_need_geo, papers_need_city=None, request_id=None):
    """
    Background thread to:
      1) geocode papers with missing coordinates
      2) enrich city labels for cached coordinates without city
    """
    from affiliation_extractor import extractor
    from pdf_affiliation_extractor import pdf_extractor

    papers_need_city = papers_need_city or []
    tasks = [("geo", p) for p in papers_need_geo] + [("city", p) for p in papers_need_city]

    def _is_stale_generation():
        with geocoding_state["lock"]:
            current = geocoding_state.get("request_id")
        return request_id is not None and current != request_id

    print(f"[Background] Starting tasks: geo={len(papers_need_geo)}, city={len(papers_need_city)}, request_id={request_id}")

    for idx, (mode, p) in enumerate(tasks):
        if _is_stale_generation():
            print(f"[Background] Abort stale task generation request_id={request_id}")
            return

        try:
            inst_id = p.get('institution_id')
            inst_name = p.get('lab')
            country = p.get('institution_country')
            cache_key = inst_id if inst_id else f"name:{inst_name}"

            if mode == "city":
                lat = p.get('lat')
                lon = p.get('lon')
                city = geocoder.get_city_for_coordinates(lat, lon, cache_key=cache_key)

                with geocoding_state["lock"]:
                    if request_id is not None and geocoding_state.get("request_id") != request_id:
                        return
                    for paper in geocoding_state["papers"]:
                        if paper['id'] == p['id']:
                            paper['institution_city'] = city
                            break
                    geocoding_state["completed"] = idx + 1

                print(f"[Background] City {idx+1}/{len(tasks)}: {inst_name} -> {city}")
                continue

            # mode == "geo"
            is_arxiv = p.get('is_arxiv', False)

            # Safety: arXiv should never be in pending queue; mark and skip if slipped in
            if is_arxiv:
                with geocoding_state["lock"]:
                    if request_id is not None and geocoding_state.get("request_id") != request_id:
                        return
                    for paper in geocoding_state["papers"]:
                        if paper['id'] == p['id']:
                            paper['lat'] = None
                            paper['lon'] = None
                            paper['geo_status'] = 'arxiv'
                            break
                    geocoding_state["completed"] = idx + 1
                continue

            # 如果是非arXiv且没有机构信息，尝试提取
            if not inst_name or inst_name == 'Unknown Lab':
                doi_url = p.get('url')
                if doi_url and doi_url.startswith('http'):
                    print(f"[Background] 尝试HTML提取: {doi_url[:50]}...")
                    affiliations = extractor.extract_from_doi(doi_url)

                    if not affiliations and 'doi.org' in doi_url:
                        pdf_url = doi_url.replace('doi.org', 'doi.org') + '.pdf'
                        print(f"[Background] 尝试PDF提取...")
                        affiliations = pdf_extractor.extract_from_pdf_url(pdf_url)

                    if affiliations:
                        inst_name = affiliations[0]
                        print(f"[Background] ✓ 提取到机构: {inst_name[:50]}")

                        with geocoding_state["lock"]:
                            if request_id is not None and geocoding_state.get("request_id") != request_id:
                                return
                            for paper in geocoding_state["papers"]:
                                if paper['id'] == p['id']:
                                    paper['lab'] = inst_name
                                    break

            lat, lon, source, city = None, None, "fail", None
            for attempt in range(2):
                lat, lon, source, city = geocoder.get_coordinates(inst_id, inst_name, country)
                if source != "fail":
                    break
                if attempt == 0:
                    print(f"[Background] Attempt 1 failed for '{inst_name}', retrying...")
                    time.sleep(0.3)
            if source == "fail":
                source = "unknown"
                # Persist unknown so next scans won't retry endlessly
                if cache_key:
                    geocoder.cache[cache_key] = {
                        "name": inst_name,
                        "lat": None,
                        "lon": None,
                        "country": country,
                        "city": None,
                        "status": "unknown"
                    }
                    geocoder.save_cache()
                print(f"[Background] Gave up after 2 attempts: '{inst_name}' -> UNKNOWN (cached)")

            with geocoding_state["lock"]:
                if request_id is not None and geocoding_state.get("request_id") != request_id:
                    return
                for paper in geocoding_state["papers"]:
                    if paper['id'] == p['id']:
                        paper['lat'] = lat
                        paper['lon'] = lon
                        paper['geo_status'] = source
                        paper['institution_city'] = city
                        break

                geocoding_state["completed"] = idx + 1

            print(f"[Background] Geocoded {idx+1}/{len(tasks)}: {inst_name} -> ({lat}, {lon}) via {source}, city={city}")

        except Exception as e:
            print(f"[Background] Error task for {p.get('lab')}: {e}")
            with geocoding_state["lock"]:
                if request_id is not None and geocoding_state.get("request_id") != request_id:
                    return
                if mode == "geo":
                    for paper in geocoding_state["papers"]:
                        if paper['id'] == p['id']:
                            paper['lat'] = None
                            paper['lon'] = None
                            paper['geo_status'] = 'unknown'
                            break
                    # Cache terminal unknown on exception as well
                    if cache_key:
                        geocoder.cache[cache_key] = {
                            "name": inst_name,
                            "lat": None,
                            "lon": None,
                            "country": country,
                            "city": None,
                            "status": "unknown"
                        }
                        geocoder.save_cache()
                geocoding_state["completed"] = idx + 1

    with geocoding_state["lock"]:
        if request_id is None or geocoding_state.get("request_id") == request_id:
            geocoding_state["status"] = "completed"

    print(f"[Background] Done. All tasks completed. request_id={request_id}")

# -----------------------------------------------------------------
# Geo Tile Services (Legacy, keep for compatibility)
# -----------------------------------------------------------------
@app.route('/api/geo/index')
def get_geo_index():
    filepath = os.path.join(GEODATA_DIR, 'geo', 'index.json')
    if not os.path.exists(filepath):
        return jsonify({"error": "Index not found"}), 404
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/geo/tile/<z>/<x>/<y>')
def get_geo_tile(z, x, y):
    try:
        z, x, y = int(z), int(x), int(y)
    except ValueError:
        return jsonify({"error": "Invalid tile coordinates"}), 400
    filepath = os.path.join(GEODATA_DIR, 'geo', str(z), str(x), f"{y}.json")
    if not os.path.exists(filepath):
        return jsonify({"error": "Tile not found"}), 404
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

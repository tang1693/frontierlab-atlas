import os
import json
import requests
import time
from urllib.parse import quote

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CACHE_FILE = os.path.join(DATA_DIR, 'institutions.json')
MAPS_CO_API_KEY = os.getenv("MAPS_CO_API_KEY", "").strip()

# Country Centers (Fallback)
COUNTRY_CENTERS = {
    'US': (37.0902, -95.7129), 'CN': (35.8617, 104.1954), 'GB': (55.3781, -3.4360),
    'CA': (56.1304, -106.3468), 'AU': (-25.2744, 133.7751), 'DE': (51.1657, 10.4515),
    'FR': (46.2276, 2.2137), 'JP': (36.2048, 138.2529), 'KR': (35.9078, 127.7669),
    'IN': (20.5937, 78.9629), 'RU': (61.5240, 105.3188), 'BR': (-14.2350, -51.9253),
    'SG': (1.3521, 103.8198), 'CH': (46.8182, 8.2275), 'NL': (52.1326, 5.2913),
    'SE': (60.1282, 18.6435), 'IL': (31.0461, 34.8516), 'IT': (41.8719, 12.5674),
    'ES': (40.4637, -3.7492), 'TW': (23.6978, 120.9605), 'HK': (22.3193, 114.1694)
}


class SmartGeocoder:
    def __init__(self):
        self.cache = {}
        self.load_cache()
        if not MAPS_CO_API_KEY:
            print("[Geocoder] MAPS_CO_API_KEY not set; online geocoding will be skipped.")

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                print(f"[Geocoder] Loaded {len(self.cache)} institutions from offline cache.")
            except Exception as e:
                print(f"[Geocoder] Error loading cache: {e}")
                self.cache = {}
        else:
            self.cache = {}

    def save_cache(self):
        """Persist cache to disk."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Geocoder] Error saving cache: {e}")

    @staticmethod
    def _extract_city(address: dict):
        if not isinstance(address, dict):
            return None
        for k in ['city', 'town', 'village', 'municipality', 'suburb', 'county', 'state_district', 'state']:
            v = address.get(k)
            if v:
                return v
        return None

    def get_city_for_coordinates(self, lat, lon, cache_key=None):
        """Reverse lookup city and optionally store it into institution cache entry."""
        try:
            if lat is None or lon is None:
                return None

            # If cache has city already, return directly
            if cache_key and cache_key in self.cache:
                existing = self.cache[cache_key].get('city')
                if existing:
                    return existing

            city = self._reverse_city(lat, lon)
            if city and cache_key and cache_key in self.cache:
                self.cache[cache_key]['city'] = city
                self.save_cache()
            return city
        except Exception as e:
            print(f"[Geocoder] Reverse city error: {e}")
            return None

    def get_coordinates(self, institution_id, display_name=None, country_code=None):
        """
        Get coordinates for an institution.
        Strategy: Cache -> Online Geocode -> Country Center
        Returns: (lat, lon, source, city)
        """
        cache_key = institution_id if institution_id else f"name:{display_name}"

        # 1. Check Local Cache
        if cache_key and cache_key in self.cache:
            entry = self.cache[cache_key]
            status = entry.get('status')
            if status == 'unknown':
                return None, None, "unknown", entry.get('city')
            return entry.get('lat'), entry.get('lon'), "cache", entry.get('city')

        # 2. Online geocode by institution name
        lat, lon, city = None, None, None
        if display_name and display_name not in ['Unknown Lab', 'Unknown', '']:
            print(f"[Geocoder] Online lookup for: {display_name}...")
            lat, lon, city = self._query_nominatim(display_name)

            if lat is not None and lon is not None:
                if cache_key:
                    self.cache[cache_key] = {
                        "name": display_name,
                        "lat": lat,
                        "lon": lon,
                        "country": country_code,
                        "city": city,
                        "status": "ok"
                    }
                    self.save_cache()
                return lat, lon, "nominatim", city

        # 3. Country fallback (for stats only, not map markers)
        if country_code and country_code in COUNTRY_CENTERS:
            lat, lon = COUNTRY_CENTERS[country_code]
            return lat, lon, "country_fallback", None

        # 4. Fail
        return None, None, "fail", None

    def _query_nominatim(self, query):
        """Forward geocode institution name. Returns (lat, lon, city)."""
        if not MAPS_CO_API_KEY:
            return None, None, None
        try:
            url = f"https://geocode.maps.co/search?q={quote(query)}&api_key={MAPS_CO_API_KEY}"
            res = requests.get(url, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data:
                    first = data[0]
                    lat = float(first['lat'])
                    lon = float(first['lon'])
                    city = self._extract_city(first.get('address', {}))
                    return lat, lon, city
            time.sleep(0.15)
        except Exception as e:
            print(f"[Geocoder] Forward API Error: {e}")
        return None, None, None

    def _reverse_city(self, lat, lon):
        """Reverse geocode coordinates to city name."""
        if not MAPS_CO_API_KEY:
            return None
        try:
            url = f"https://geocode.maps.co/reverse?lat={lat}&lon={lon}&api_key={MAPS_CO_API_KEY}"
            res = requests.get(url, timeout=6)
            if res.status_code == 200:
                data = res.json() or {}
                city = self._extract_city(data.get('address', {}))
                return city
            time.sleep(0.15)
        except Exception as e:
            print(f"[Geocoder] Reverse API Error: {e}")
        return None


# Singleton instance
geocoder = SmartGeocoder()

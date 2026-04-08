#!/usr/bin/env python3
import os
import time
import json
import tempfile
import shutil
import logging
from typing import Dict, Tuple

import requests


ZONE_MAP = {
    "UK": "GB",  
    "DE": "DE", 
    "ES": "ES", 
}

CARBON_FILE = "carbon.json"    
POLL_INTERVAL_SEC = 3600       
TIMEOUT = 15                    
RETRIES = 2                    

# ElectricityMaps endpoint
BASE_URL = "https://api.electricitymap.org/v3/carbon-intensity/latest"


API_TOKEN = os.getenv("ELECTRICITYMAPS_TOKEN")  


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def read_existing_carbon(path: str) -> Dict[str, float]:
    """Return existing carbon.json values (or empty)."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
            # Normalize to floats
            return {k: float(v) for k, v in data.items()}
    except FileNotFoundError:
        logging.warning("No existing carbon.json found; starting fresh.")
        return {}
    except Exception as e:
        logging.error(f"Failed to read {path}: {e}")
        return {}

def write_atomic_json(path: str, data: Dict[str, float]) -> None:
    """Write JSON atomically to avoid readers seeing partial content."""
    d = json.dumps(data, indent=2, sort_keys=True)
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".carbon.tmp.", text=True)
    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(d + "\n")
        shutil.move(tmp_path, path)
    finally:
       
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def fetch_zone_intensity(zone_code: str) -> Tuple[bool, float]:
    """
    Query ElectricityMaps for a single zone.
    Returns (ok, intensity_g_per_kwh).
    """
    headers = {}
    if API_TOKEN:
    
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    else:
        logging.error("ELECTRICITYMAPS_TOKEN not set in environment.")
        return (False, 0.0)

    params = {"zone": zone_code}
    url = BASE_URL
    last_err = None

    for _ in range(RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                payload = r.json()
                # ElectricityMaps returns gCO2eq/kWh in "carbonIntensity"
                val = float(payload.get("carbonIntensity"))
                return (True, val)
            else:
                last_err = f"HTTP {r.status_code} {r.text[:200]}"
        except Exception as e:
            last_err = str(e)

        time.sleep(1.5)  

    logging.error(f"Zone {zone_code} fetch failed: {last_err}")
    return (False, 0.0)

def update_once():
    """Fetch all zones, update carbon.json keeping old values on per-zone failure."""
    current = read_existing_carbon(CARBON_FILE)
    updated = dict(current)  

    for human_key, em_zone in ZONE_MAP.items():
        ok, val = fetch_zone_intensity(em_zone)
        if ok:
            logging.info(f"{human_key} ({em_zone}) = {val:.1f} gCO2/kWh")
            updated[human_key] = round(val, 1)
        else:
            
            if human_key in updated:
                logging.warning(f"Keeping previous value for {human_key}: {updated[human_key]}")
            else:
                logging.warning(f"No previous value for {human_key}; leaving it unset.")

    write_atomic_json(CARBON_FILE, updated)
    logging.info(f"Wrote {CARBON_FILE}: {updated}")

def main_loop():

    while True:
        try:
            update_once()
        except Exception as e:
            logging.exception(f"Unexpected error during update: {e}")
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":

    if os.getenv("RUN_ONCE") == "1":
        update_once()
    else:
        main_loop()

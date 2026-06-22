import re
import logging
import os
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

NAVAREA_FEEDS = {
    "NAVAREA I":   "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_I",
    "NAVAREA II":  "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_II",
    "NAVAREA IV":  "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_IV",
    "NAVAREA XII": "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_XII",
}


def _extract_coords_from_text(text):
    patterns = [
        r'[NS]\d{2,3}[-°]\d{2}(?:\.\d+)?(?:[-°]\d{2}(?:\.\d+)?)?\s+[EW]\d{2,3}[-°]\d{2}(?:\.\d+)?(?:[-°]\d{2}(?:\.\d+)?)?',
        r'\d{2,3}[-°]\d{2}(?:\.\d+)?[NS]\s+\d{2,3}[-°]\d{2}(?:\.\d+)?[EW]',
        r'\d+\.\d+[NS]\s+\d+\.\d+[EW]',
        r'[NS]\s?\d{4,6}(?:\.\d+)?\s+[EW]\s?\d{4,6}(?:\.\d+)?',
    ]
    coords = []
    for pat in patterns:
        found = re.findall(pat, text, re.IGNORECASE)
        coords.extend(found)
    return list(dict.fromkeys(coords))


def _extract_time_window(text):
    patterns = [
        r'(\d{10})\s*/\s*(\d{10})',
        r'(\d{4}Z)\s*(?:TO|UNTIL|-)\s*(\d{4}Z)',
        r'FROM\s+([\d\s\w:/-]+?)\s+TO\s+([\d\s\w:/-]+?)(?:\.|$)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} -> {m.group(2)}"
    return "Не указано"


def fetch_faa_notams():
    # FAA требует регистрацию — пока пропускаем
    return []


def fetch_navarea_warnings():
    results = []

    for area_name, url in NAVAREA_FEEDS.items():
        try:
            resp = requests.get(url, timeout=15)
            logger.info(f"{area_name} status: {resp.status_code}, length: {len(resp.text)}")
            logger.info(f"{area_name} response preview: {resp.text[:500]}")

            data = resp.json()
            items = data if isinstance(data, list) else data.get("broadcastWarn", [])
            logger.info(f"{area_name} items count: {len(items)}")

            for item in items:
                text = item.get("text", "") or item.get("detail", "") or str(item)
                coords = _extract_coords_from_text(text)
                logger.info(f"Item coords found: {coords}, text preview: {text[:200]}")

                results.append({
                    "id": f"{item.get('msgYear','')}/{item.get('msgNumber','')}",
                    "text": text[:600],
                    "coords": coords,
                    "time_window": _extract_time_window(text),
                    "area_name": item.get("subregion", area_name),
                    "source": f"NAVAREA ({area_name})",
                })

        except Exception as e:
            logger.error(f"NAVAREA {area_name} error: {e}")

    return results

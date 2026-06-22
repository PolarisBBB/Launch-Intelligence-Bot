import re
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Keywords that indicate launch reservations
LAUNCH_KEYWORDS = [
    "rocket", "launch", "missile", "space", "spacecraft", "NASA",
    "SpaceX", "ULA", "Rocket Lab", "range", "NOTAM", "TEMPORARY",
    "WARNING", "CAUTION", "PARACHUTE", "JATO", "UAV", "UAS"
]

FAA_NOTAM_URL = "https://external-api.faa.gov/notamapi/v1/notams"
FAA_CLIENT_ID = os.getenv("FAA_CLIENT_ID", "")
FAA_CLIENT_SECRET = os.getenv("FAA_CLIENT_SECRET", "")

# NAVAREA warnings RSS/XML feeds (public)
NAVAREA_FEEDS = {
    "NAVAREA I":    "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_I&output=xml",
    "NAVAREA II":   "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_II&output=xml",
    "NAVAREA III":  "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_III&output=xml",
    "NAVAREA IV":   "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_IV&output=xml",
    "NAVAREA XII":  "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_XII&output=xml",
]

import os


def _is_launch_related(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in LAUNCH_KEYWORDS)


def _extract_coords_from_text(text: str) -> list[str]:
    """Extract coordinate patterns like N28-27.5 W080-31.7 or 28.45N 080.52W"""
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
    return list(dict.fromkeys(coords))  # deduplicate, preserve order


def _extract_time_window(text: str) -> str:
    """Extract time window from NOTAM/NAVAREA text."""
    patterns = [
        r'(\d{10})\s*/\s*(\d{10})',                         # 2501010000/2501012359
        r'(\d{2}/\d{4})\s*UTC?\s*TO\s*(\d{2}/\d{4})\s*UTC?',
        r'(\d{4}Z)\s*(?:TO|UNTIL|-)\s*(\d{4}Z)',
        r'EFFECTIVE\s+([\d\s\w:/-]+?)\s+UNTIL\s+([\d\s\w:/-]+?)(?:\.|$)',
        r'FROM\s+([\d\s\w:/-]+?)\s+TO\s+([\d\s\w:/-]+?)(?:\.|$)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} → {m.group(2)}"
    return "Не указано"


def _extract_area_name(text: str) -> str:
    """Try to extract the name/location of the reservation."""
    m = re.search(r'([A-Z][A-Z0-9 \-]{3,40}(?:RANGE|LAUNCH|AREA|ZONE|POLYGON|CORRIDOR|SECTOR))', text)
    if m:
        return m.group(1).strip()
    m = re.search(r'(?:VICINITY OF|NEAR|AROUND)\s+([A-Z][A-Z ,]{3,40})', text)
    if m:
        return m.group(1).strip()
    return "Не указано"


def fetch_faa_notams() -> list[dict]:
    """Fetch active launch-related NOTAMs from FAA API."""
    results = []
    headers = {"Accept": "application/json"}

    # If API keys provided, use authenticated endpoint
    if FAA_CLIENT_ID and FAA_CLIENT_SECRET:
        headers["client_id"] = FAA_CLIENT_ID
        headers["client_secret"] = FAA_CLIENT_SECRET

    params = {
        "pageSize": 100,
        "pageNum": 1,
        "notamType": "NOTAM",
        "classification": "INTL",
    }

    try:
        resp = requests.get(FAA_NOTAM_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
    except Exception as e:
        logger.warning(f"FAA API failed, trying fallback: {e}")
        return _fetch_faa_fallback()

    for item in items:
        props = item.get("properties", {})
        core = props.get("coreNOTAMData", {}).get("notam", {})
        text = core.get("fullText", "") or core.get("text", "")
        if not text:
            continue
        if not _is_launch_related(text):
            continue

        coords = _extract_coords_from_text(text)
        if not coords:
            continue  # skip if no coordinates

        results.append({
            "id": core.get("id", "N/A"),
            "text": text,
            "coords": coords,
            "time_window": _extract_time_window(text),
            "area_name": _extract_area_name(text),
            "source": "FAA NOTAM",
        })

    return results


def _fetch_faa_fallback() -> list[dict]:
    """Fallback: fetch NOTAMs from SkyVector/ADDS public feed."""
    results = []
    # FAA public NOTAM search (no auth needed)
    url = "https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do"
    params = {
        "reportType": "Raw",
        "retrieveLocId": "ZJX ZMA ZNY ZBW ZOB ZDC ZID ZTL ZME ZLC ZDV ZAB ZLA ZSE ZOA ZHU",
        "actionType": "notamRetrievalByICAOs",
    }
    try:
        resp = requests.post(url, data=params, timeout=15)
        text_blocks = re.findall(r'![\w\d /\.\-\n]+?(?=!|\Z)', resp.text, re.DOTALL)
        for block in text_blocks[:50]:
            block = block.strip()
            if not _is_launch_related(block):
                continue
            coords = _extract_coords_from_text(block)
            if not coords:
                continue
            results.append({
                "id": re.search(r'!([\w\d]+)', block).group(1) if re.search(r'!([\w\d]+)', block) else "N/A",
                "text": block[:800],
                "coords": coords,
                "time_window": _extract_time_window(block),
                "area_name": _extract_area_name(block),
                "source": "FAA NOTAM",
            })
    except Exception as e:
        logger.error(f"FAA fallback failed: {e}")
    return results


def fetch_navarea_warnings() -> list[dict]:
    """Fetch active NAVAREA broadcast warnings from NGA MSI."""
    results = []

    for area_name, url in NAVAREA_FEEDS.items():
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            # NGA MSI XML structure
            ns = {"": ""}
            items = root.findall(".//{*}broadcastWarn") or root.findall(".//item") or root.findall(".//warn")

            for item in items:
                def get_text(tag):
                    el = item.find(f".//{tag}")
                    return el.text.strip() if el is not None and el.text else ""

                text = get_text("text") or get_text("description") or get_text("detail") or ET.tostring(item, encoding="unicode")
                if not text:
                    continue

                if not _is_launch_related(text):
                    # Still include NAVAREA items with coordinates (they're always relevant)
                    pass

                coords = _extract_coords_from_text(text)
                if not coords:
                    continue

                number = get_text("msgYear") + "/" + get_text("msgNumber") if get_text("msgNumber") else get_text("number") or "N/A"
                subregion = get_text("subregion") or get_text("area") or area_name

                results.append({
                    "id": number,
                    "text": text[:800],
                    "coords": coords,
                    "time_window": _extract_time_window(text),
                    "area_name": subregion or area_name,
                    "source": f"NAVAREA ({area_name})",
                })

        except ET.ParseError:
            # Try JSON fallback for NGA MSI
            results.extend(_fetch_navarea_json(area_name, url.replace("output=xml", "output=json")))
        except Exception as e:
            logger.error(f"NAVAREA {area_name} fetch error: {e}")

    return results


def _fetch_navarea_json(area_name: str, url: str) -> list[dict]:
    results = []
    try:
        url_json = url.replace("navArea=", "navArea=").replace("output=xml", "")
        base = "https://msi.nga.mil/api/publications/broadcast-warn"
        nav_key = area_name.replace("NAVAREA ", "NAVAREA_")
        resp = requests.get(base, params={"status": "active", "navArea": nav_key}, timeout=15)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("broadcastWarn", [])
        for item in items:
            text = item.get("text", "") or item.get("detail", "")
            coords = _extract_coords_from_text(text)
            if not coords:
                continue
            results.append({
                "id": f"{item.get('msgYear','')}/{item.get('msgNumber','')}",
                "text": text[:800],
                "coords": coords,
                "time_window": _extract_time_window(text),
                "area_name": item.get("subregion", area_name),
                "source": f"NAVAREA ({area_name})",
            })
    except Exception as e:
        logger.error(f"NAVAREA JSON fallback {area_name}: {e}")
    return results

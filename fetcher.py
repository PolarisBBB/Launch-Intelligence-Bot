import re
import logging
import os
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

FAA_CLIENT_ID = os.getenv("FAA_CLIENT_ID", "")
FAA_CLIENT_SECRET = os.getenv("FAA_CLIENT_SECRET", "")

NAVAREA_FEEDS = {
    "NAVAREA I":   "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_I&output=xml",
    "NAVAREA II":  "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_II&output=xml",
    "NAVAREA III": "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_III&output=xml",
    "NAVAREA IV":  "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_IV&output=xml",
    "NAVAREA XII": "https://msi.nga.mil/api/publications/broadcast-warn?status=active&navArea=NAVAREA_XII&output=xml",
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


def _extract_area_name(text):
    m = re.search(r'([A-Z][A-Z0-9 \-]{3,40}(?:RANGE|LAUNCH|AREA|ZONE|POLYGON|CORRIDOR|SECTOR))', text)
    if m:
        return m.group(1).strip()
    return "Не указано"


def fetch_faa_notams():
    results = []
    headers = {"Accept": "application/json"}

    if FAA_CLIENT_ID and FAA_CLIENT_SECRET:
        headers["client_id"] = FAA_CLIENT_ID
        headers["client_secret"] = FAA_CLIENT_SECRET

    # Ищем specifically резервации пространства (R, W, P зоны)
    for notam_type in ["R", "W", "P"]:
        try:
            params = {
                "pageSize": 50,
                "pageNum": 1,
                "notamType": notam_type,
            }
            resp = requests.get(
                "https://external-api.faa.gov/notamapi/v1/notams",
                headers=headers,
                params=params,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            for item in items:
                props = item.get("properties", {})
                core = props.get("coreNOTAMData", {}).get("notam", {})
                text = core.get("fullText", "") or core.get("text", "")
                if not text:
                    continue
                coords = _extract_coords_from_text(text)
                results.append({
                    "id": core.get("id", "N/A"),
                    "text": text[:600],
                    "coords": coords,
                    "time_window": _extract_time_window(text),
                    "area_name": _extract_area_name(text),
                    "source": f"FAA NOTAM ({notam_type})",
                })
        except Exception as e:
            logger.error(f"FAA NOTAM {notam_type} error: {e}")

    return results


def fetch_navarea_warnings():
    results = []

    for area_name, url in NAVAREA_FEEDS.items():
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()

            # Попробуем JSON
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("broadcastWarn", [])
                for item in items:
                    text = item.get("text", "") or item.get("detail", "")
                    if not text:
                        continue
                    coords = _extract_coords_from_text(text)
                    results.append({
                        "id": f"{item.get('msgYear','')}/{item.get('msgNumber','')}",
                        "text": text[:600],
                        "coords": coords,
                        "time_window": _extract_time_window(text),
                        "area_name": item.get("subregion", area_name),
                        "source": f"NAVAREA ({area_name})",
                    })
                continue
            except Exception:
                pass

            # Попробуем XML
            root = ET.fromstring(resp.content)
            items = root.findall(".//{*}broadcastWarn") or root.findall(".//item")

            for item in items:
                def get_tag(tag):
                    el = item.find(f".//{tag}")
                    return el.text.strip() if el is not None and el.text else ""

                text = get_tag("text") or get_tag("description") or ET.tostring(item, encoding="unicode")
                coords = _extract_coords_from_text(text)
                results.append({
                    "id": f"{get_tag('msgYear')}/{get_tag('msgNumber')}",
                    "text": text[:600],
                    "coords": coords,
                    "time_window": _extract_time_window(text),
                    "area_name": get_tag("subregion") or area_name,
                    "source": f"NAVAREA ({area_name})",
                })

        except Exception as e:
            logger.error(f"NAVAREA {area_name} error: {e}")

    return results

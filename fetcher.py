import re
import logging
import requests

logger = logging.getLogger(__name__)

NAVAREA_URLS = {
    "NAVAREA IV":  "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemIV.txt",
    "NAVAREA XII": "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemXII.txt",
    "HYDROPAC":    "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemPAC.txt",
}

LAUNCH_KEYWORDS = [
    "rocket", "launch", "missile", "hazardous operations",
    "firing", "range", "space", "NASA", "SpaceX", "PMRF",
    "rocket launching", "weapons", "exercise", "cable operations"
]


def _is_relevant(text):
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in LAUNCH_KEYWORDS)


def _extract_coords(text):
    patterns = [
        r'\d{1,2}-\d{2}\.\d+[NS]\s+\d{1,3}-\d{2}\.\d+[EW]',
        r'\d{1,2}-\d{2}[NS]\s+\d{1,3}-\d{2}[EW]',
        r'[NS]\d{2,3}[-]\d{2}(?:\.\d+)?\s+[EW]\d{2,3}[-]\d{2}(?:\.\d+)?',
        r'\d+\.\d+[NS]\s+\d+\.\d+[EW]',
        r'\d{4}[NS][/\s]?\d{5}[EW]',
        r'\d{4}[NS]\d{5}[EW]',
        r'\d{1,3}\.\d+[NS]\s+\d{1,3}\.\d+[EW]',
    ]
    coords = []
    for pat in patterns:
        found = re.findall(pat, text, re.IGNORECASE)
        coords.extend(found)
    return list(dict.fromkeys(coords))


def _extract_time_window(text):
    patterns = [
        r'(\d{6}Z\s+\w+\s+\d{2})\s+(?:TO|UNTIL|-)\s+(\d{6}Z\s+\w+\s+\d{2})',
        r'(\d{4}Z)\s+(?:TO|UNTIL|-)\s+(\d{4}Z)',
        r'(\d{1,2}\s+\w+\s+(?:TO|THRU)\s+\d{1,2}\s+\w+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if m.lastindex == 2:
                return f"{m.group(1)} -> {m.group(2)}"
            return m.group(1)
    return "Не указано"


def _parse_warnings_text(text, source_name):
    results = []
    blocks = re.split(
        r'(?=\d{6}Z\s+\w{3}\s+\d{2}\s+(?:NAVAREA|HYDRO\w+|HYDROLANT|HYDROPAC))',
        text
    )
    for block in blocks:
        block = block.strip()
        if len(block) < 50:
            continue
        if not _is_relevant(block):
            continue
        coords = _extract_coords(block)
        if not coords:
            continue
        id_match = re.search(r'((?:NAVAREA|HYDRO\w+)\s+[\w/]+)', block)
        warn_id = id_match.group(1) if id_match else "N/A"
        results.append({
            "id": warn_id,
            "text": block[:600],
            "coords": coords,
            "time_window": _extract_time_window(block),
            "area_name": source_name,
            "source": f"NAVAREA ({source_name})",
        })
    return results


def fetch_faa_notams():
    results = []

    try:
        resp = requests.get(
            "https://aviationweather.gov/api/data/airsigmet",
            params={"format": "json", "type": "SIGMET"},
            timeout=20,
            headers={"User-Agent": "TelegramNotamBot/1.0"}
        )
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"SIGMET: получено {len(data)} записей")
            for item in data:
                text = item.get("rawAirSigmet", "") or str(item)
                if not text:
                    continue

                coords = _extract_coords(text)

                if not coords:
                    area = item.get("area", [])
                    coords = [
                        f"{p.get('lat','')}/{p.get('lon','')}"
                        for p in area if p.get('lat') and p.get('lon')
                    ]

                if not coords:
                    logger.info(f"SIGMET без координат, текст: {text[:300]}")
                    continue

                results.append({
                    "id": item.get("airSigmetId", "N/A"),
                    "text": text[:600],
                    "coords": coords,
                    "time_window": f"{item.get('validTimeFrom', '')} -> {item.get('validTimeTo', '')}",
                    "area_name": item.get("region", "SIGMET"),
                    "source": "SIGMET (воздушная)",
                })
        else:
            logger.warning(f"SIGMET статус: {resp.status_code}")
    except Exception as e:
        logger.error(f"SIGMET ошибка: {e}")

    return results


def fetch_navarea_warnings():
    results = []

    for area_name, url in NAVAREA_URLS.items():
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            text = resp.text
            logger.info(f"{area_name}: получено {len(text)} символов")
            warnings = _parse_warnings_text(text, area_name)
            logger.info(f"{area_name}: найдено {len(warnings)} резерваций")
            results.extend(warnings)
        except Exception as e:
            logger.error(f"{area_name} ошибка: {e}")

    return results

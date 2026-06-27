import re
import logging
import requests

logger = logging.getLogger(__name__)

NAVAREA_URLS = {
    "NAVAREA IV":  "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemIV.txt",
    "NAVAREA XII": "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemXII.txt",
    "HYDROPAC":    "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemPAC.txt",
    "HYDROLANT":   "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemLant.txt",
}

LAUNCH_KEYWORDS = [
    "rocket", "missile", "hazardous operations",
    "rocket launching", "missile firing", "weapons firing",
    "space launch", "NASA", "SpaceX", "PMRF",
    "firing operations", "rocket launch",
]

AIR_KEYWORDS = [
    "aircraft", "airspace", "altitude", "flight level",
    "FL", "feet", "FT MSL", "air navigation"
]

CHILE_KEYWORDS = [
    "chile", "chilean", "valparaiso", "santiago"
]


def _is_relevant(text):
    return any(kw.lower() in text.lower() for kw in LAUNCH_KEYWORDS)


def _is_chile(text):
    return any(kw.lower() in text.lower() for kw in CHILE_KEYWORDS)


def _is_air_reservation(text):
    return any(kw.lower() in text.lower() for kw in AIR_KEYWORDS)


def _extract_coords(text):
    patterns = [
        r'\d{1,2}-\d{2}\.\d+[NS]\s+\d{1,3}-\d{2}\.\d+[EW]',
        r'\d{1,2}-\d{2}[NS]\s+\d{1,3}-\d{2}[EW]',
        r'[NS]\d{2,3}[-]\d{2}(?:\.\d+)?\s+[EW]\d{2,3}[-]\d{2}(?:\.\d+)?',
        r'\d+\.\d+[NS]\s+\d+\.\d+[EW]',
        r'\d{4}[NS][/\s]?\d{5}[EW]',
        r'\d{1,3}\.\d+[NS]\s+\d{1,3}\.\d+[EW]',
    ]
    coords = []
    for pat in patterns:
        coords.extend(re.findall(pat, text, re.IGNORECASE))
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
            return f"{m.group(1)} -> {m.group(2)}" if m.lastindex == 2 else m.group(1)
    return "Не указано"


def _extract_published_time(text):
    """Извлекаем дату/время публикации резервации (первая строка блока)."""
    m = re.search(r'(\d{6}Z\s+\w{3}\s+\d{2})', text)
    if m:
        raw = m.group(1)
        # Формат: 210220Z JUN 26 -> 26 JUN 2026 02:20Z
        parts = raw.split()
        if len(parts) == 3:
            time_part = parts[0][:4]  # 0220
            day = parts[2]
            month = parts[1]
            return f"{day} {month} {time_part}Z"
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
        if _is_chile(block):
            continue
        coords = _extract_coords(block)
        if not coords:
            continue
        id_match = re.search(r'((?:NAVAREA|HYDRO\w+)\s+[\w/]+)', block)
        warn_id = id_match.group(1) if id_match else "N/A"
        res_type = "air" if _is_air_reservation(block) else "sea"
        results.append({
            "id": warn_id,
            "text": block[:800],
            "coords": coords,
            "time_window": _extract_time_window(block),
            "published": _extract_published_time(block),
            "area_name": source_name,
            "source": source_name,
            "type": res_type,
        })
    return results


def fetch_faa_notams():
    return []


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

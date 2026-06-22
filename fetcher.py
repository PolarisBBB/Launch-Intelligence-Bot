import re
import logging
import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

NAVAREA_URLS = {
    "NAVAREA IV":  "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemIV.txt",
    "NAVAREA XII": "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemXII.txt",
    "HYDROPAC":    "https://msi.nga.mil/api/publications/download?type=view&key=16694640%2FSFH00000%2FDailyMemPAC.txt",
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


def _is_relevant(text):
    return any(kw.lower() in text.lower() for kw in LAUNCH_KEYWORDS)


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


def fetch_faa_notams():
    results = []
    headers = {"User-Agent": "TelegramNotamBot/1.0"}

    # Получаем список всех активных TFR
    try:
        resp = requests.get("https://tfr.faa.gov/tfr2/list.jsp", headers=headers, timeout=20)
        tfr_ids = re.findall(r'detail_(\d+_\d+)\.htm', resp.text)
        tfr_ids = list(dict.fromkeys(tfr_ids))  # убираем дубли
        logger.info(f"FAA TFR: найдено {len(tfr_ids)} TFR")

        for tfr_id in tfr_ids[:30]:
            try:
                xml_url = f"https://tfr.faa.gov/save_pages/detail_{tfr_id}.xml"
                r2 = requests.get(xml_url, headers=headers, timeout=10)
                if r2.status_code != 200:
                    continue

                root = ET.fromstring(r2.content)

                # Собираем весь текст из XML
                all_text = " ".join(
                    el.text.strip()
                    for el in root.iter()
                    if el.text and el.text.strip()
                )

                # Фильтруем только запуски
                if not _is_relevant(all_text):
                    continue

                # Координаты из текста
                coords = _extract_coords(all_text)

                # Если нет — берём из атрибутов XML
                if not coords:
                    for el in root.iter():
                        lat = el.get("Lat") or el.get("lat")
                        lon = el.get("Lon") or el.get("lon")
                        if lat and lon:
                            coords.append(f"{lat}N {abs(float(lon))}W" if float(lon) < 0 else f"{lat}N {lon}E")

                if not coords:
                    continue

                # Время
                begin = root.find(".//{*}dateEffective") or root.find(".//dateEffective")
                end = root.find(".//{*}dateExpire") or root.find(".//dateExpire")
                time_window = f"{begin.text if begin is not None else '?'} -> {end.text if end is not None else '?'}"

                # Причина / описание
                reason = root.find(".//{*}notamText") or root.find(".//notamText")
                text = reason.text[:600] if reason is not None else all_text[:600]

                # Локация
                loc = root.find(".//{*}locationName") or root.find(".//locationName")
                area_name = loc.text if loc is not None else tfr_id

                results.append({
                    "id": f"TFR {tfr_id}",
                    "text": text,
                    "coords": coords,
                    "time_window": time_window,
                    "area_name": area_name,
                    "source": "FAA TFR",
                    "type": "air",
                })

            except Exception as e:
                logger.debug(f"TFR {tfr_id} ошибка: {e}")

    except Exception as e:
        logger.error(f"FAA TFR список ошибка: {e}")

    return results


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
        res_type = "air" if _is_air_reservation(block) else "sea"
        results.append({
            "id": warn_id,
            "text": block[:600],
            "coords": coords,
            "time_window": _extract_time_window(block),
            "area_name": source_name,
            "source": f"NAVAREA ({source_name})",
            "type": res_type,
        })
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

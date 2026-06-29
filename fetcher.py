import re
import logging
import requests
from datetime import datetime, timezone

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

CHILE_KEYWORDS = ["chile", "chilean", "valparaiso", "santiago"]

# Известные площадки запусков с координатами
LAUNCH_PADS = {
    "Cape Canaveral":     (28.39, -80.60),
    "Kennedy Space Center": (28.52, -80.65),
    "Vandenberg":         (34.75, -120.52),
    "Wallops":            (37.84, -75.48),
    "PMRF":               (22.02, -159.79),
    "Mahia":              (-39.26, 177.86),
    "Baikonur":           (45.96, 63.31),
    "Plesetsk":           (62.93, 40.57),
    "Jiuquan":            (40.96, 100.29),
    "Xichang":            (28.25, 102.03),
    "Wenchang":           (19.61, 110.95),
    "Satish Dhawan":      (13.73, 80.23),
    "Kourou":             (5.24, -52.77),
    "Tanegashima":        (30.40, 130.97),
}


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


def _coord_to_decimal(coord_str):
    """Конвертируем строку координат в десятичные градусы."""
    try:
        m = re.match(r'(\d{1,3})-(\d{2})\.?(\d*)([NS])\s+(\d{1,3})-(\d{2})\.?(\d*)([EW])', coord_str)
        if m:
            lat = float(m.group(1)) + float(m.group(2) + '.' + m.group(3)) / 60
            lon = float(m.group(5)) + float(m.group(6) + '.' + m.group(7)) / 60
            if m.group(4) == 'S':
                lat = -lat
            if m.group(8) == 'W':
                lon = -lon
            return lat, lon
    except Exception:
        pass
    return None


def _distance_km(lat1, lon1, lat2, lon2):
    """Примерное расстояние в км между двумя точками."""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


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
    m = re.search(r'(\d{6}Z\s+\w{3}\s+\d{2})', text)
    if m:
        raw = m.group(1)
        parts = raw.split()
        if len(parts) == 3:
            time_part = parts[0][:4]
            day = parts[2]
            month = parts[1]
            return f"{day} {month} {time_part}Z"
    return "Не указано"


def _extract_window_dates(text):
    """Извлекаем даты временного окна для сравнения с запусками."""
    m = re.search(
        r'(\d{2})(\d{2})(\d{2})Z\s+(\w+)\s+(\d{2})\s+TO\s+(\d{2})(\d{2})(\d{2})Z\s+(\w+)\s+(\d{2})',
        text, re.IGNORECASE
    )
    if m:
        try:
            months = {
                "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12
            }
            year = datetime.now(timezone.utc).year
            start = datetime(year, months.get(m.group(4).upper(), 1), int(m.group(5)),
                           int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
            end = datetime(year, months.get(m.group(9).upper(), 1), int(m.group(10)),
                         int(m.group(6)), int(m.group(7)), tzinfo=timezone.utc)
            return start, end
        except Exception:
            pass
    return None, None


def fetch_upcoming_launches():
    """Получаем все предстоящие запуски с Launch Library 2."""
    try:
        resp = requests.get(
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/",
            params={"limit": 25, "format": "json"},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        logger.error(f"Launch Library ошибка: {e}")
        return []


def find_matching_launch(reservation: dict, launches: list) -> str:
    """
    Ищем запуск который совпадает с резервацией по времени и месту.
    Возвращает строку с описанием совпадения или пустую строку.
    """
    coords = reservation.get("coords", [])
    text = reservation.get("text", "")

    # Пробуем извлечь временное окно резервации
    win_start, win_end = _extract_window_dates(text)

    # Конвертируем координаты резервации
    res_points = []
    for c in coords[:3]:
        pt = _coord_to_decimal(c)
        if pt:
            res_points.append(pt)

    matches = []

    for launch in launches:
        launch_name = launch.get("name", "")
        provider = launch.get("launch_service_provider", {}).get("name", "")
        net = launch.get("net", "")
        pad = launch.get("pad", {})
        pad_name = pad.get("name", "")
        location_name = pad.get("location", {}).get("name", "")
        pad_lat = pad.get("latitude")
        pad_lon = pad.get("longitude")

        score = 0
        reasons = []

        # Проверяем совпадение по времени
        if net and win_start and win_end:
            try:
                launch_dt = datetime.fromisoformat(net.replace("Z", "+00:00"))
                if win_start <= launch_dt <= win_end:
                    score += 3
                    reasons.append("временное окно совпадает")
            except Exception:
                pass

        # Проверяем совпадение по месту — через координаты площадки
        if pad_lat and pad_lon and res_points:
            try:
                pad_lat_f = float(pad_lat)
                pad_lon_f = float(pad_lon)
                for rp in res_points:
                    dist = _distance_km(rp[0], rp[1], pad_lat_f, pad_lon_f)
                    if dist < 200:
                        score += 3
                        reasons.append(f"площадка в {int(dist)} км от зоны резервации")
                        break
                    elif dist < 500:
                        score += 1
                        reasons.append(f"площадка в {int(dist)} км от зоны резервации")
                        break
            except Exception:
                pass

        # Проверяем совпадение по ключевым словам в тексте
        for pad_key, pad_coords in LAUNCH_PADS.items():
            if pad_key.lower() in text.lower():
                if pad_key.lower() in (pad_name + location_name).lower():
                    score += 2
                    reasons.append(f"упоминается {pad_key}")
                    break

        if score >= 2:
            try:
                dt = datetime.fromisoformat(net.replace("Z", "+00:00"))
                time_str = dt.strftime("%d %b %Y %H:%MZ")
            except Exception:
                time_str = net

            matches.append({
                "score": score,
                "text": f"🚀 *Возможный запуск:* {launch_name}\n"
                        f"   🏢 {provider}\n"
                        f"   📍 {location_name}\n"
                        f"   📅 {time_str}\n"
                        f"   💡 Причина: {', '.join(reasons)}"
            })

    if not matches:
        return ""

    # Возвращаем лучшее совпадение
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[0]["text"]


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
def fetch_faa_notams():
    """Получаем NOTAM через aviationweather.gov — работает без блокировок."""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 TelegramNotamBot/1.0"}

    # Коды аэропортов/зон рядом с космодромами
    stations = [
        "KTTS", "KXMR", "KVAD", "KNSI", "KNKX",  # США — космодромы
        "PHNL", "PHKO",                              # Гавайи — PMRF
        "NZWN", "NZCH",                              # Новая Зеландия — Rocket Lab
        "SBLS", "SBMD",                              # Бразилия
        "ZUCK", "ZBAA",                              # Китай
        "VOBL", "VABB",                              # Индия
        "LFPG", "SOCA",                              # Франция/Гвиана — Ariane
    ]

    for station in stations:
        try:
            resp = requests.get(
                "https://aviationweather.gov/api/data/notam",
                params={
                    "format": "json",
                    "icaos": station,
                },
                headers=headers,
                timeout=20
            )

            if resp.status_code != 200:
                logger.warning(f"aviationweather {station}: статус {resp.status_code}")
                continue

            data = resp.json()
            if not isinstance(data, list):
                continue

            logger.info(f"aviationweather {station}: получено {len(data)} NOTAM")

            for item in data:
                text = item.get("raw", "") or item.get("text", "")
                if not text:
                    continue
                if not _is_relevant(text):
                    continue

                coords = _extract_coords(text)
                if not coords:
                    continue

                notam_id = item.get("notamID", "N/A")
                start = item.get("startTime", "")
                end = item.get("endTime", "")
                time_window = f"{start} -> {end}" if start and end else _extract_time_window(text)

                results.append({
                    "id": f"NOTAM {notam_id}",
                    "text": text[:800],
                    "coords": coords,
                    "time_window": time_window,
                    "published": start,
                    "area_name": station,
                    "source": f"FAA NOTAM ({station})",
                    "type": "air",
                })

        except Exception as e:
            logger.error(f"aviationweather {station} ошибка: {e}")

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

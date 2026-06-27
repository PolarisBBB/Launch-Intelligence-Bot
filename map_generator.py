from staticmap import StaticMap, Polygon, Line, CircleMarker
from PIL import Image, ImageDraw
import re
import io
import logging

logger = logging.getLogger(__name__)

# Публичные тайловые серверы (без блокировки)
TILE_SERVERS = [
    'https://tile.opentopomap.org/{z}/{x}/{y}.png',
    'https://tiles.wmflabs.org/osm/{z}/{x}/{y}.png',
    'https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
]


def _coord_to_decimal(coord_str: str):
    coord_str = coord_str.strip()

    # Формат: 37-43.61N 075-12.62W
    m = re.match(
        r'(\d{1,3})-(\d{2})\.?(\d*)\s*([NS])\s+(\d{1,3})-(\d{2})\.?(\d*)\s*([EW])',
        coord_str, re.IGNORECASE
    )
    if m:
        lat = float(m.group(1)) + float(m.group(2) + '.' + (m.group(3) or '0')) / 60
        lon = float(m.group(5)) + float(m.group(6) + '.' + (m.group(7) or '0')) / 60
        if m.group(4).upper() == 'S':
            lat = -lat
        if m.group(8).upper() == 'W':
            lon = -lon
        return lat, lon

    # Формат: 24.30N 066.42E
    m2 = re.match(
        r'(\d{1,3}\.\d+)\s*([NS])\s+(\d{1,3}\.\d+)\s*([EW])',
        coord_str, re.IGNORECASE
    )
    if m2:
        lat = float(m2.group(1))
        lon = float(m2.group(3))
        if m2.group(2).upper() == 'S':
            lat = -lat
        if m2.group(4).upper() == 'W':
            lon = -lon
        return lat, lon

    return None


def generate_map(reservation: dict) -> bytes | None:
    coords = reservation.get("coords", [])
    if not coords:
        return None

    points = []
    for c in coords:
        pt = _coord_to_decimal(c)
        if pt:
            points.append(pt)

    if not points:
        return None

    # Пробуем разные тайловые серверы
    for tile_url in TILE_SERVERS:
        try:
            m = StaticMap(
                800, 600,
                url_template=tile_url,
                headers={"User-Agent": "TelegramNotamBot/1.0 (educational project)"}
            )

            polygon_coords = [(p[1], p[0]) for p in points]

            if len(points) >= 3:
                if polygon_coords[0] != polygon_coords[-1]:
                    polygon_coords.append(polygon_coords[0])
                polygon = Polygon(polygon_coords, '#FF0000', '#FF000055', simplify=True)
                m.add_polygon(polygon)
                line = Line(polygon_coords, '#CC0000', 2)
                m.add_line(line)
            elif len(points) == 2:
                line = Line(polygon_coords, '#FF0000', 3)
                m.add_line(line)

            for pt in points:
                marker = CircleMarker((pt[1], pt[0]), '#CC0000', 8)
                m.add_marker(marker)

            image = m.render()

            # Проверяем что карта не заблокирована (не серая/белая)
            img_array = list(image.getdata())
            unique_colors = len(set(img_array[:100]))
            if unique_colors < 3:
                logger.warning(f"Тайлы заблокированы: {tile_url}")
                continue

            # Подпись сверху
            draw = ImageDraw.Draw(image)
            source = reservation.get("source", "")
            res_id = reservation.get("id", "")
            time_window = reservation.get("time_window", "")

            draw.rectangle([0, 0, 800, 28], fill=(0, 0, 0))
            draw.text((8, 6), f"🗺 {source} | {res_id}", fill="white")

            if time_window and time_window != "Не указано":
                draw.rectangle([0, 572, 800, 600], fill=(0, 0, 0))
                draw.text((8, 578), f"⏱ {time_window}", fill="white")

            buf = io.BytesIO()
            image.save(buf, format='PNG')
            buf.seek(0)
            return buf.read()

        except Exception as e:
            logger.error(f"Карта ошибка ({tile_url}): {e}")
            continue

    return None

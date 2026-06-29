from staticmap import StaticMap, Polygon, Line, CircleMarker
from PIL import Image, ImageDraw
import re
import io
import logging

logger = logging.getLogger(__name__)


def _coord_to_decimal(coord_str: str):
    coord_str = coord_str.strip()

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

    TILE_SERVERS = [
        'https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
        'https://cartodb-basemaps-b.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
        'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    ]

    for tile_url in TILE_SERVERS:
        try:
            m = StaticMap(
                800, 600,
                url_template=tile_url,
                headers={"User-Agent": "Mozilla/5.0 NotamBot/1.0"}
            )

            polygon_coords = [(p[1], p[0]) for p in points]

            if len(points) >= 3:
                if polygon_coords[0] != polygon_coords[-1]:
                    polygon_coords.append(polygon_coords[0])
                # Только контур — без заливки (fill цвет прозрачный)
                line = Line(polygon_coords, '#FF0000', 3)
                m.add_line(line)
            elif len(points) == 2:
                line = Line(polygon_coords, '#FF0000', 3)
                m.add_line(line)

            for pt in points:
                marker = CircleMarker((pt[1], pt[0]), '#CC0000', 6)
                m.add_marker(marker)

            image = m.render()

            draw = ImageDraw.Draw(image)
            source = reservation.get("source", "").encode('ascii', 'ignore').decode()
            res_id = reservation.get("id", "").encode('ascii', 'ignore').decode()
            time_window = reservation.get("time_window", "").encode('ascii', 'ignore').decode()

            draw.rectangle([0, 0, 800, 28], fill=(20, 20, 20))
            draw.text((8, 6), f"{source} | {res_id}", fill=(255, 255, 255))

            if time_window:
                draw.rectangle([0, 572, 800, 600], fill=(20, 20, 20))
                draw.text((8, 578), f"Window: {time_window}", fill=(255, 255, 255))

            buf = io.BytesIO()
            image.save(buf, format='PNG')
            buf.seek(0)
            logger.info(f"Карта сгенерирована: {source} {res_id}")
            return buf.read()

        except Exception as e:
            logger.error(f"Карта ошибка ({tile_url}): {e}")
            continue

    return None

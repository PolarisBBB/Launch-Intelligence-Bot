from staticmap import StaticMap, Polygon, Line, CircleMarker
from PIL import Image, ImageDraw, ImageFont
import re
import io


def _coord_to_decimal(coord_str: str):
    """Конвертируем строку координат в (lat, lon)."""
    # Формат: 37-43.61N 075-12.62W
    m = re.match(
        r'(\d{1,3})-(\d{2})\.?(\d*)\s*([NS])\s+(\d{1,3})-(\d{2})\.?(\d*)\s*([EW])',
        coord_str.strip(), re.IGNORECASE
    )
    if m:
        lat = float(m.group(1)) + float(m.group(2) + '.' + (m.group(3) or '0')) / 60
        lon = float(m.group(5)) + float(m.group(6) + '.' + (m.group(7) or '0')) / 60
        if m.group(4).upper() == 'S':
            lat = -lat
        if m.group(8).upper() == 'W':
            lon = -lon
        return lat, lon

    # Формат: 24-24.30N 066-42.00E
    m2 = re.match(
        r'(\d{1,3})\.(\d+)\s*([NS])\s+(\d{1,3})\.(\d+)\s*([EW])',
        coord_str.strip(), re.IGNORECASE
    )
    if m2:
        lat = float(m2.group(1) + '.' + m2.group(2))
        lon = float(m2.group(4) + '.' + m2.group(5))
        if m2.group(3).upper() == 'S':
            lat = -lat
        if m2.group(6).upper() == 'W':
            lon = -lon
        return lat, lon

    return None


def generate_map(reservation: dict) -> bytes | None:
    """
    Генерируем картинку карты с полигоном резервации.
    Возвращает bytes PNG или None если не удалось.
    """
    coords = reservation.get("coords", [])
    if not coords:
        return None

    # Конвертируем все координаты
    points = []
    for c in coords:
        pt = _coord_to_decimal(c)
        if pt:
            points.append(pt)

    if not points:
        return None

    try:
        m = StaticMap(800, 600, url_template='https://tile.openstreetmap.org/{z}/{x}/{y}.png')

        if len(points) >= 3:
            # Рисуем полигон
            # staticmap ожидает (lon, lat)
            polygon_coords = [(p[1], p[0]) for p in points]
            # Замыкаем полигон
            if polygon_coords[0] != polygon_coords[-1]:
                polygon_coords.append(polygon_coords[0])

            polygon = Polygon(polygon_coords, 'red', '#FF000066', simplify=True)
            m.add_polygon(polygon)

            # Обводка
            line = Line(polygon_coords, '#CC0000', 3)
            m.add_line(line)

        elif len(points) == 2:
            # Линия между двумя точками
            line_coords = [(p[1], p[0]) for p in points]
            line = Line(line_coords, 'red', 3)
            m.add_line(line)
        else:
            # Одна точка — маркер с радиусом
            marker = CircleMarker((points[0][1], points[0][0]), 'red', 12)
            m.add_marker(marker)

        # Добавляем маркеры в углах
        for pt in points:
            marker = CircleMarker((pt[1], pt[0]), '#CC0000', 6)
            m.add_marker(marker)

        image = m.render()

        # Добавляем подпись
        draw = ImageDraw.Draw(image)
        source = reservation.get("source", "")
        res_id = reservation.get("id", "")
        time_window = reservation.get("time_window", "")

        label = f"{source} | {res_id}"
        draw.rectangle([0, 0, 800, 30], fill=(0, 0, 0, 180))
        draw.text((10, 8), label, fill="white")

        if time_window and time_window != "Не указано":
            draw.rectangle([0, 570, 800, 600], fill=(0, 0, 0, 180))
            draw.text((10, 578), f"Окно: {time_window}", fill="white")

        # Сохраняем в bytes
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        return buf.read()

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Карта ошибка: {e}")
        return None

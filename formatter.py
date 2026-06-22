def format_reservation(data: dict, res_type: str) -> str:
    """
    Format a reservation dict into a readable Telegram Markdown message.
    
    res_type: 'air' | 'sea'
    """
    if res_type == "air":
        type_emoji = "✈️"
        type_label = "ВОЗДУШНАЯ РЕЗЕРВАЦИЯ"
    else:
        type_emoji = "🌊"
        type_label = "МОРСКАЯ РЕЗЕРВАЦИЯ"

    source = data.get("source", "N/A")
    res_id = data.get("id", "N/A")
    area = data.get("area_name", "Не указано")
    time_window = data.get("time_window", "Не указано")
    text_preview = data.get("text", "")[:300].replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
    coords = data.get("coords", [])

    # Build coords block for easy copy-paste
    coords_block = "\n".join(f"`{c}`" for c in coords) if coords else "_не найдены_"

    msg = (
        f"{type_emoji} *{type_label}*\n"
        f"📡 Источник: {source} | ID: `{res_id}`\n"
        f"📍 Зона: {area}\n"
        f"🕐 Временное окно: `{time_window}`\n"
        f"\n"
        f"📝 _Описание:_\n{text_preview}...\n"
        f"\n"
        f"📌 *Координаты (нажми для копирования):*\n"
        f"{coords_block}\n"
        f"{'─' * 30}\n"
    )
    return msg

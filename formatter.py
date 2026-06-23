def format_reservation(data: dict, res_type: str) -> str:
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
    text = data.get("text", "").replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")

    msg = (
        f"{type_emoji} *{type_label}*\n"
        f"📡 {source} | №: `{res_id}`\n"
        f"📍 Зона: {area}\n"
        f"🕐 Временное окно: `{time_window}`\n"
        f"\n"
        f"{text}"
    )
    return msg

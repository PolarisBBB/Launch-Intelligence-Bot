def format_reservation(data: dict, res_type: str, launch_match: str = "") -> str:
    if res_type == "air":
        type_label = "✈️ Резервация воздушного пространства"
    else:
        type_label = "🌊 Резервация морского пространства"

    zone = data.get("source", "N/A")
    time_window = data.get("time_window", "Не указано")
    published = data.get("published", "Не указано")
    text = data.get("text", "").replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")

    msg = f"{type_label}\n"

    if launch_match:
        msg += f"\n{launch_match}\n\n"

    msg += (
        f"📍 Зона: {zone}\n"
        f"🕐 Временное окно: {time_window}\n"
        f"📅 Опубликовано: {published}\n"
        f"\n"
        f"{text}"
    )
    return msg

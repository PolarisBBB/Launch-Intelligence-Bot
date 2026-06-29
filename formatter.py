def format_reservation(data: dict, res_type: str, launch_match: str = "") -> str:
    zone = data.get("source", "N/A")
    time_window = data.get("time_window", "")
    text = data.get("text", "").replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")

    if res_type == "air":
        zone_emoji = "✈️"
    else:
        zone_emoji = "🌊"

    msg = f"{zone_emoji} *{zone}*\n"

    if launch_match:
        msg += f"\n{launch_match}\n\n"

    if time_window and time_window != "Не указано":
        msg += f"🕐 Временное окно: `{time_window}`\n"

    msg += f"\n{text}"

    return msg

def blank_value(_v):
    return None

def blank_list_item(item: dict) -> None:
    item["delta_mm"] = blank_value(item.get("delta_mm"))

def should_blank_path(path: str) -> bool:
    return path in {"list", "create"}

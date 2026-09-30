QUEUE_BLANK = True
CARD_BLANK = True

def project_surfaces(row: dict) -> dict:
    out = dict(row)
    if QUEUE_BLANK:
        out["delta_mm"] = None
    if CARD_BLANK and out.get("delta_mm") is None:
        out["delta_display"] = ""
    return out

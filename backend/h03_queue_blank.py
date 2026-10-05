"""列表与卡片投影：读数原样透出。

历史 bug：QUEUE_BLANK/CARD_BLANK 开启时把 delta_mm 置 None 并补空
delta_display，导致总表毫米数变空。投影不得增删读数，只能原样透出。
"""


def project_surfaces(row: dict) -> dict:
    return dict(row)

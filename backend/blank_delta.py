"""读数投影辅助：任何路径都不得把毫米值置空或清零。

历史 bug：blank_value 一律返回 None，list/create 路径的 delta_mm 全被置空，
导致总表与详情里的毫米数变空。0 mm 是合法读数，必须原样透出。
"""


def blank_value(value):
    """读数原样返回：0 是合法收敛值，不得置空或清零。"""
    return value


def blank_list_item(item: dict) -> None:
    """保留 delta_mm 原值，不做任何置空。"""
    if "delta_mm" in item:
        item["delta_mm"] = blank_value(item["delta_mm"])


def should_blank_path(path: str) -> bool:
    """没有任何路径允许置空读数。"""
    return False

"""投影出口：入库（create）与总表（list）共用。

任何路径都不得把读数置空或清零；0 mm 是合法读数。
"""
from blank_delta import blank_list_item, should_blank_path


def apply_blank(item: dict, path: str) -> dict:
    out = dict(item)
    if should_blank_path(path):
        blank_list_item(out)
    return out

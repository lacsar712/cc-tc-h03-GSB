"""总表投影：逐行透出；任一行失败则整批失败，不留半空行。"""
from h03_extra_trap import apply_blank
from h03_queue_blank import project_surfaces


def expose_list(rows: list) -> list:
    # 列表推导：任一行投影抛错则整个请求失败，
    # 不会返回只投影了一半的半空行。
    return [project_surfaces(apply_blank(dict(it), "list")) for it in rows]

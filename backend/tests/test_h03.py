from h03_extra_trap import apply_blank
from h03_map_trap import expose_list

def test_blank():
    d = {"delta_mm": 1.2}
    apply_blank(d, "list")
    assert d["delta_mm"] is None
    rows = expose_list([{"delta_mm": 1.2}])
    assert rows[0]["delta_mm"] in (0, None)

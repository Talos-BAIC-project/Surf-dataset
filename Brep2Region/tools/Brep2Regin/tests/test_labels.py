"""Label 注册表与查询文本解析测试。"""

from tools.Brep2Regin.label2brep.labels import LabelRegistry


def _registry():
    return LabelRegistry.load()


def test_alias_resolution():
    reg = _registry()
    assert reg.resolve("加强筋").profile.label_id == "dfc.substructure.internal_web"
    assert reg.resolve("腔体").profile.label_id == "dfc.substructure.chamber"
    assert reg.resolve("法兰").profile.label_id == "dfc.substructure.flange"
    assert reg.resolve("外轮廓").profile.label_id == "dfc.substructure.outer_contour"
    assert reg.resolve("倒角").profile.label_id == "dfc.substructure.fillet"


def test_region_name_resolution():
    reg = _registry()
    r = reg.resolve("chamber_2")
    assert r.profile.label_id == "dfc.substructure.chamber"
    assert r.selector.ordinal == 2
    r = reg.resolve("stiffener_a")
    assert r.profile.label_id == "dfc.substructure.internal_web"
    assert r.selector.ordinal == 1


def test_label_id_passthrough():
    reg = _registry()
    r = reg.resolve("dfc.substructure.notch")
    assert r.profile.short == "notch"
    assert r.evidence == "exact_label_id"


def test_selector_parsing():
    reg = _registry()
    r = reg.resolve("把中间两道梁高亮")
    assert r.profile.label_id == "dfc.substructure.internal_web"   # 梁 -> 筋
    assert r.selector.count == 2
    assert r.selector.position == "center"
    r2 = reg.resolve("第二个腔")
    assert r2.profile.short == "chamber"
    assert r2.selector.ordinal == 2


def test_unresolvable_text():
    reg = _registry()
    assert reg.resolve("完全不相关的话xyzq") is None

"""bbox 弱标注 -> 实体级 silver 金标引导。

每类 function 有专门的转换规则（与 dfc-dataset 标注策略一一对应）：
- enclosed        腔体   -> cell / 子腔（矩形与多边形 IoU 最优匹配）
- cavity          开放腔 -> bbox 内衬曲线集合
- structural(_shape) / stiffener / connection -> bbox 内曲线（含入率阈值）
- forming_feature 凹槽   -> depth×width 矩形（自动判定 depth 方向）内曲线
- transition      倒角   -> 过渡段曲线（凸角=外倒角 / 凹角=内倒角；位置+半径过滤）
- outer_contour   外轮廓 -> 几何派生（闭合截面外边界非悬挂曲线），无需标注

产出的实体集合作为"训练/评估金标"（silver 级，待工程师确认升级为 gold）。
推理阶段绝不使用 bbox —— bbox 只在这里出现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dataset import Region, SectionRecord
from .graph import GEOM_EPS, SectionGraph, _signed_area
from .labels import LabelRegistry

_LETTER_ORDINAL = {c: i + 1 for i, c in enumerate("abcdefgh")}


@dataclass
class SilverTarget:
    section_id: str
    region_name: str
    function: str
    label_id: str
    entity_type: str                     # face | curve
    face_ids: list[str] = field(default_factory=list)
    curve_names: list[str] = field(default_factory=list)
    point_names: list[str] = field(default_factory=list)
    ordinal: int | None = None
    flags: list[str] = field(default_factory=list)
    match_score: float = 0.0             # 匹配质量（IoU / 覆盖率）

    @property
    def is_empty(self) -> bool:
        return not self.curve_names and not self.face_ids and not self.point_names


# ---------------------------------------------------------------------------
# 几何判定
# ---------------------------------------------------------------------------

def _resample(poly: list[tuple[float, float]], step: float = 1.0) -> list[tuple[float, float]]:
    """按弧长均匀重采样折线（含端点）。"""
    import math
    total = sum(math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
                for i in range(len(poly) - 1))
    n = max(8, min(64, int(total / max(step, 1e-6)) + 2))
    out = []
    acc = 0.0
    seg_i = 0
    seg_start = 0.0
    for k in range(n + 1):
        s = total * k / n
        while seg_i < len(poly) - 2:
            seg_len = math.hypot(poly[seg_i + 1][0] - poly[seg_i][0], poly[seg_i + 1][1] - poly[seg_i][1])
            if seg_start + seg_len >= s - GEOM_EPS:
                break
            seg_start += seg_len
            seg_i += 1
        seg_len = math.hypot(poly[seg_i + 1][0] - poly[seg_i][0], poly[seg_i + 1][1] - poly[seg_i][1])
        t = 0.0 if seg_len < GEOM_EPS else max(0.0, min(1.0, (s - seg_start) / seg_len))
        out.append((
            poly[seg_i][0] + t * (poly[seg_i + 1][0] - poly[seg_i][0]),
            poly[seg_i][1] + t * (poly[seg_i + 1][1] - poly[seg_i][1]),
        ))
        acc = s
    _ = acc
    return out


def inside_fraction(poly: list[tuple[float, float]], rect: tuple[float, float, float, float],
                    tol: float) -> float:
    x0, y0, x1, y1 = rect[0] - tol, rect[1] - tol, rect[2] + tol, rect[3] + tol
    pts = _resample(poly)
    inside = sum(1 for u, v in pts if x0 <= u <= x1 and y0 <= v <= y1)
    return inside / len(pts)


def _clip_halfplane(poly, keep_fn, cross_fn):
    out = []
    n = len(poly)
    for i in range(n):
        cur, nxt = poly[i], poly[(i + 1) % n]
        cur_in, nxt_in = keep_fn(cur), keep_fn(nxt)
        if cur_in:
            out.append(cur)
        if cur_in != nxt_in:
            ip = cross_fn(cur, nxt)
            if ip is not None:
                out.append(ip)
    return out


def polygon_rect_iou(poly: list[tuple[float, float]], rect: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = rect
    clipped = poly
    for keep, cross in (
        (lambda p: p[0] >= x0, lambda a, b: _x_cross(a, b, x0)),
        (lambda p: p[0] <= x1, lambda a, b: _x_cross(a, b, x1)),
        (lambda p: p[1] >= y0, lambda a, b: _y_cross(a, b, y0)),
        (lambda p: p[1] <= y1, lambda a, b: _y_cross(a, b, y1)),
    ):
        clipped = _clip_halfplane(clipped, keep, cross)
        if len(clipped) < 3:
            return 0.0
    inter = abs(_signed_area(clipped))
    a_poly = abs(_signed_area(poly))
    a_rect = max((x1 - x0), 0.0) * max((y1 - y0), 0.0)
    union = a_poly + a_rect - inter
    return inter / union if union > GEOM_EPS else 0.0


def _x_cross(a, b, x):
    if abs(b[0] - a[0]) < GEOM_EPS:
        return None
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _y_cross(a, b, y):
    if abs(b[1] - a[1]) < GEOM_EPS:
        return None
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


# ---------------------------------------------------------------------------
# 各 function 的转换规则
# ---------------------------------------------------------------------------

def _bbox_tol(graph: SectionGraph) -> float:
    return max(0.8, min(1.5, 0.008 * graph.geo.diag))


def _flip_rect(rect: tuple[float, float, float, float] | None, flip_w: float | None):
    """u 方向镜像矩形（部分截面的标注坐标系与几何呈镜像关系）。"""
    if rect is None or flip_w is None:
        return rect
    x0, y0, x1, y1 = rect
    return (flip_w - x1, y0, flip_w - x0, y1)


def _curves_in_rect(graph: SectionGraph, rect, min_frac: float) -> list[str]:
    tol = _bbox_tol(graph)
    out = []
    for cname, cv in graph.geo.curves.items():
        if inside_fraction(cv.polyline_local, rect, tol) >= min_frac:
            out.append(cname)
    return out


def _endpoints(graph: SectionGraph, curve_names: list[str]) -> list[str]:
    pts = []
    seen = set()
    for cname in curve_names:
        cv = graph.geo.curves[cname]
        for p in (cv.start, cv.end):
            if p not in seen:
                seen.add(p)
                pts.append(p)
    return pts


def _match_enclosed(graph: SectionGraph, region: Region, target: SilverTarget,
                    flip_w: float | None = None) -> None:
    rect = _flip_rect(region.rect, flip_w)
    if rect is None:
        target.flags.append("no_rect")
        return
    best = None
    for cell in graph.cells:
        iou = polygon_rect_iou(cell.polygon, rect)
        if best is None or iou > best[0]:
            best = (iou, cell.cell_id, cell.curve_names, cell.point_names)
    for sub in graph.subcells:
        iou = polygon_rect_iou(sub.polygon, rect)
        if best is None or iou > best[0]:
            best = (iou, sub.subcell_id, sub.curve_names, sub.point_names)
    if best is None or best[0] < 0.3:
        target.flags.append("no_cell_match" if best is None else f"low_iou:{best[0]:.2f}")
        if best is None:
            return
    iou, fid, curves, points = best
    target.face_ids = [fid]
    target.curve_names = list(curves)
    target.point_names = list(points)
    target.match_score = iou


def _match_notch(graph: SectionGraph, region: Region, target: SilverTarget,
                 flip_w: float | None = None) -> None:
    b = region.bbox
    x, y = float(b["x"]), float(b["y"])
    depth, width = float(b["depth"]), float(b["width"])
    rect_a = _flip_rect((x, y, x + depth, y + width), flip_w)   # depth 沿水平（主流约定）
    rect_b = _flip_rect((x, y, x + width, y + depth), flip_w)   # 兜底：depth 沿竖直
    got_a = _curves_in_rect(graph, rect_a, 0.7)
    got_b = _curves_in_rect(graph, rect_b, 0.7)
    len_a = sum(graph.geo.curves[c].length for c in got_a)
    len_b = sum(graph.geo.curves[c].length for c in got_b)
    curves = got_a if len_a >= len_b else got_b
    if got_a and len_a < len_b:
        target.flags.append("notch_axis_flipped")
    target.curve_names = curves
    target.point_names = _endpoints(graph, curves)
    total = len_a if len_a >= len_b else len_b
    target.match_score = min(1.0, total / max(depth + width, GEOM_EPS))


def _match_strip(graph: SectionGraph, region: Region, target: SilverTarget, min_frac: float,
                 flip_w: float | None = None) -> None:
    rect = _flip_rect(region.rect, flip_w)
    if rect is None:
        target.flags.append("no_rect")
        return
    curves = _curves_in_rect(graph, rect, min_frac)
    target.curve_names = curves
    target.point_names = _endpoints(graph, curves)
    target.match_score = 1.0 if curves else 0.0


def _match_transition(graph: SectionGraph, region: Region, target: SilverTarget,
                      flip_w: float | None = None) -> None:
    b = region.bbox or {}
    radius = float(b.get("radius", 0.0) or 0.0)
    position = str(b.get("position") or "")
    name = region.name.lower()

    trans = [c for c, t in graph.curve_topo.items() if t.transition_like]
    if radius > 0:
        trans = [c for c in trans if graph.geo.curves[c].length <= 3.2 * radius + 0.5]

    if "x" in b and "y" in b and "width" not in b:
        # 单个倒角：给了圆角中心坐标。优先取邻近过渡段曲线；
        # DFC 宏中倒角常被简化为尖角，此时映射为角点（点实体金标）。
        px, py = float(b["x"]), float(b["y"])
        if flip_w is not None:
            px = flip_w - px

        def dist_to(cname: str) -> float:
            poly = graph.geo.curves[cname].polyline_local
            mid = poly[len(poly) // 2]
            return ((mid[0] - px) ** 2 + (mid[1] - py) ** 2) ** 0.5

        best_curve = min(trans, key=dist_to, default=None)
        if best_curve is not None and dist_to(best_curve) <= max(2.2 * radius, 4.0):
            target.curve_names = [best_curve]
            target.match_score = 1.0
        else:
            best_pt, best_d = None, float("inf")
            for pname, pt in graph.geo.points.items():
                d = ((pt.uv_local[0] - px) ** 2 + (pt.uv_local[1] - py) ** 2) ** 0.5
                if abs(d - radius) < abs(best_d - radius):
                    best_pt, best_d = pname, d
            if best_pt is not None and 0.4 * radius <= best_d <= 1.9 * radius:
                target.entity_type = "point"
                target.point_names = [best_pt]
                target.flags.append("corner_point_fallback")
                target.match_score = 0.8
                return
            target.flags.append("no_nearby_transition")
    elif region.rect is not None:
        rect = _flip_rect(region.rect, flip_w)
        curves = [c for c in _curves_in_rect(graph, rect, 0.6) if c in set(trans)] or \
                 _curves_in_rect(graph, rect, 0.6)
        target.curve_names = curves
        target.match_score = 1.0 if curves else 0.0
    else:
        # fillet_outer / fillet_inner：按凸凹分组
        want_convex = "outer" in position or "outer" in name
        got = [c for c in trans if graph.curve_topo[c].transition_convex == want_convex]
        target.curve_names = got
        target.match_score = 1.0 if got else 0.0
    if not target.curve_names:
        target.flags.append("empty_transition")
    target.point_names = _endpoints(graph, target.curve_names)


def _match_outer_contour(graph: SectionGraph, target: SilverTarget) -> None:
    curves = [c for c in graph.outer_curves
              if not graph.curve_topo[c].dangling]
    target.curve_names = sorted(curves, key=lambda c: graph.geo.curves[c].runtime_id)
    target.point_names = _endpoints(graph, target.curve_names)
    target.match_score = 1.0 if curves else 0.0


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def _region_ordinal(name: str) -> int | None:
    m = re.search(r"[_\-]([a-h]|\d+)$", name.lower())
    if not m:
        return None
    token = m.group(1)
    return int(token) if token.isdigit() else _LETTER_ORDINAL.get(token)


def _build_region_targets(rec: SectionRecord, graph: SectionGraph, registry: LabelRegistry,
                          flip_w: float | None) -> list[SilverTarget]:
    targets: list[SilverTarget] = []
    for region in rec.regions:
        profile = registry.profile_for_function(region.function) \
            or registry.profile_for_region_name(region.name)
        label_id = profile.label_id if profile else f"unmapped.{region.function}"
        entity_type = profile.entity_type if profile else "curve"
        t = SilverTarget(
            section_id=rec.section_id, region_name=region.name, function=region.function,
            label_id=label_id, entity_type=entity_type, ordinal=_region_ordinal(region.name),
        )
        if profile is None:
            t.flags.append("unmapped_function")
        fn = region.function
        if fn == "enclosed":
            _match_enclosed(graph, region, t, flip_w)
        elif fn == "forming_feature":
            _match_notch(graph, region, t, flip_w)
        elif fn == "cavity":
            _match_strip(graph, region, t, min_frac=0.6, flip_w=flip_w)
        elif fn in ("structural", "structural_shape", "stiffener", "connection"):
            _match_strip(graph, region, t, min_frac=0.8, flip_w=flip_w)
        elif fn == "transition" or (profile is not None and profile.short == "fillet"):
            _match_transition(graph, region, t, flip_w)
        else:
            t.flags.append("unknown_function")
        if t.is_empty:
            t.flags.append("empty_target")
        targets.append(t)
    return targets


def build_silver_targets(rec: SectionRecord, graph: SectionGraph,
                         registry: LabelRegistry) -> list[SilverTarget]:
    """构建 silver 金标；自动判定标注坐标系是否 u 镜像（部分截面存在）。"""
    base = _build_region_targets(rec, graph, registry, flip_w=None)
    targets = base
    if rec.regions:
        flipped = _build_region_targets(rec, graph, registry, flip_w=graph.geo.width)

        def score(ts: list[SilverTarget]) -> float:
            return sum(t.match_score for t in ts) + 0.7 * sum(1 for t in ts if not t.is_empty)

        if score(flipped) > score(base) + 0.25:
            targets = flipped
            for t in targets:
                t.flags.append("annotation_u_mirrored")

    # 外轮廓：几何派生金标（闭合截面才有意义）
    if graph.is_closed:
        t = SilverTarget(
            section_id=rec.section_id, region_name="outer_contour", function="outer_contour",
            label_id="dfc.substructure.outer_contour", entity_type="curve",
        )
        _match_outer_contour(graph, t)
        t.flags.append("synthetic")
        targets.append(t)
    return targets


def silver_report(all_targets: dict[str, list[SilverTarget]]) -> str:
    """生成质量报告（markdown）。"""
    lines = ["# Silver 金标引导质量报告", ""]
    total = empty = flagged = 0
    by_label: dict[str, int] = {}
    for section_id, targets in all_targets.items():
        for t in targets:
            if "synthetic" in t.flags:
                continue
            total += 1
            by_label[t.label_id] = by_label.get(t.label_id, 0) + 1
            if t.is_empty:
                empty += 1
            if [f for f in t.flags if f != "synthetic"]:
                flagged += 1
    lines.append(f"- 数据集 region 总数: {total}")
    lines.append(f"- 成功映射为实体集合: {total - empty}（空目标 {empty}）")
    lines.append(f"- 带质量标记: {flagged}")
    lines.append("")
    lines.append("| label_id | region 数 |")
    lines.append("|---|---:|")
    for k, v in sorted(by_label.items()):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## 需人工复核的 region")
    lines.append("")
    lines.append("| section | region | function | 实体数 | flags | score |")
    lines.append("|---|---|---|---:|---|---:|")
    for section_id, targets in sorted(all_targets.items()):
        for t in targets:
            interesting = [f for f in t.flags if f != "synthetic"]
            if interesting or t.is_empty:
                n = len(t.curve_names) + len(t.face_ids)
                lines.append(
                    f"| {section_id} | {t.region_name} | {t.function} | {n} | "
                    f"{', '.join(interesting) or '-'} | {t.match_score:.2f} |"
                )
    lines.append("")
    return "\n".join(lines)

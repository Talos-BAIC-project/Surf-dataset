"""数据扩增（T1–T5）：在 Section IR 层生成"几何意图不变"的截面变体，标签自动传播。

设计要点（见 PLAN.md §2）：
- 每个变换对应 DFC 中真实会发生的编辑操作：加点拆线（T1 split）、截面拉伸（T2 scale）、
  移壁/移筋（T3 move）、加筋/删筋（T4 rib）、旋转/镜像/换坐标平面（T5 rigid）。
  禁止纯坐标抖动。
- 标签不重新匹配 bbox，而是按 name_map（源曲线 -> 新曲线列表）传播；腔体按 cell 配对，
  拓扑变化（T4）时按"闭合 cell 即腔体"的定义重新派生。
- 六道校验门：cell 数、目标非空、标签共存、仿射交叉校验、几何指纹去重、几何合理性。
- 变体继承源截面的形状族，只进训练折；留出族的变体单独作为不变性测试集。
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .config import ARTIFACTS_DIR, GEOM_EPS
from .dataset import Region, SectionRecord
from .features import CURVE_FEATURE_NAMES, SectionFeatures
from .geometry import Curve, Point, SectionGeometry, _bezier_polyline, _polyline_length
from .graph import BRIDGE_PREFIX, SectionGraph, build_section_graph
from .labels import LabelRegistry
from .pipeline import SectionBundle
from .samples import build_query_samples
from .silver import SilverTarget, _match_outer_contour, build_silver_targets

AUG_DIR = ARTIFACTS_DIR / "aug"
AUG_FILE = AUG_DIR / "aug_sections.jsonl"
PILOT_SECTION_IDS = ("U-shape-1", "mu-shape-1", "ji-shape-3", "m-shape-1", "b-shape-1")

# 操作采样权重（PLAN §2.5，T1–T5 归一化）与施加顺序：先改拓扑，再移动、缩放、刚体，最后拆线
OP_WEIGHTS = {"split": 30, "scale": 20, "rigid": 15, "move": 10, "rib": 5}
OP_ORDER = ["rib", "move", "scale", "rigid", "split"]
# 这些操作保持 bbox 标注有效，可做仿射交叉校验（校验门 4）
AFFINE_OPS = {"split", "scale", "rigid"}
# 变体上重新按空间顺序编号的标签；其余标签（notch/fillet/cavity）序数置空，只生成 generic 样本
ORDINAL_LABELS = {"chamber", "internal_web", "flange", "web"}
INTERNAL_WEB_ID = "dfc.substructure.internal_web"
CHAMBER_ID = "dfc.substructure.chamber"
OUTER_ID = "dfc.substructure.outer_contour"

# 校验门阈值
AFFINE_AGREEMENT_MIN = 0.95
MIN_CLEARANCE_MM = 2.0
BBOX_RATIO_RANGE = (0.5, 2.0)

_PLANE_AXES = {"YZ": (1, 2, 1.0), "XZ": (0, 2, 1.0), "XY": (1, 0, -1.0)}
_RIGID_KINDS = ["rot90", "rot180", "rot270", "mirror_u", "mirror_v"]
_ORD_RE = re.compile(r"[_\-]([a-h]|\d+)$")


def source_sha256(src: SectionBundle) -> str:
    """Return a stable provenance hash for the unmodified source section.

    When the dataset loader has source bytes, their relocatable manifest is
    hashed.  Programmatically constructed bundles fall back to a canonical
    Section IR hash.  Absolute checkout paths are never included.
    """
    manifest = source_manifest(src)
    if manifest:
        raw_manifest = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_manifest.encode("utf-8")).hexdigest()
    geo = src.record.geometry
    payload = {
        "section_id": src.record.section_id,
        "shape_family": src.record.shape_family,
        "topology": src.record.topology,
        "source": geo.source,
        "plane": geo.plane,
        "points": {k: list(v.xyz) for k, v in sorted(geo.points.items())},
        "curves": {
            k: {
                "start": v.start, "end": v.end,
                "control_xyz": v.control_xyz,
                "polyline_local": v.polyline_local,
            }
            for k, v in sorted(geo.curves.items())
        },
        "regions": [
            {"name": r.name, "function": r.function, "bbox": r.bbox, "notes": r.notes}
            for r in src.record.regions
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def source_manifest(src: SectionBundle) -> list[dict]:
    """Return source file names and hashes, without absolute paths."""
    return list(((src.record.meta.get("_provenance") or {}).get("source_files") or []))


# ---------------------------------------------------------------------------
# 工作几何（局部 2D 坐标上的可编辑副本）
# ---------------------------------------------------------------------------

@dataclass
class _WCurve:
    name: str
    start: str
    end: str
    ctrl: list[tuple[float, float]] | None = None    # 三次贝塞尔的两个控制点（局部坐标）


class _Work:
    """SectionGeometry 的可编辑副本：点表、线表、控制点，以及源曲线到当前曲线的映射。"""

    def __init__(self, geo: SectionGeometry):
        ua, va, vsign = _PLANE_AXES[geo.plane]
        normal = 3 - ua - va
        self.section_name = geo.section_name
        self.plane = geo.plane
        pts = list(geo.points.values())
        self.normal_coord = float(pts[0].xyz[normal]) if pts else 0.0
        self.points: dict[str, tuple[float, float]] = {p.name: tuple(p.uv_local) for p in pts}
        self.curves: dict[str, _WCurve] = {}
        for c in sorted(geo.curves.values(), key=lambda c: c.runtime_id):
            ctrl = None
            if c.control_xyz:
                ctrl = [(cp[ua] - geo.u_min, vsign * cp[va] - geo.v_min) for cp in c.control_xyz]
            self.curves[c.name] = _WCurve(c.name, c.start, c.end, ctrl)
        self.name_map: dict[str, list[str]] = {c: [c] for c in self.curves}
        self.origin_of: dict[str, str | None] = {c: c for c in self.curves}
        self.added: list[str] = []
        self.affine = np.eye(3)
        self.affine_ok = True
        self._pidx = 0
        self._cidx = 0

    # -- 基本量 ------------------------------------------------------------
    def bbox_size(self) -> tuple[float, float]:
        us = [p[0] for p in self.points.values()]
        vs = [p[1] for p in self.points.values()]
        return (max(us) - min(us), max(vs) - min(vs)) if us else (0.0, 0.0)

    def new_point(self, uv: tuple[float, float]) -> str:
        while True:
            name = f"{self.section_name}_SPa{self._pidx}"
            self._pidx += 1
            if name not in self.points:
                self.points[name] = (float(uv[0]), float(uv[1]))
                return name

    def new_curve_name(self) -> str:
        while True:
            name = f"{self.section_name}_SLa{self._cidx}"
            self._cidx += 1
            if name not in self.curves:
                return name

    def replace_curve(self, name: str, children: list[_WCurve]) -> None:
        """就地把一条曲线替换成若干子曲线（保持曲线顺序），并维护映射。"""
        new: dict[str, _WCurve] = {}
        for k, v in self.curves.items():
            if k == name:
                for ch in children:
                    new[ch.name] = ch
            else:
                new[k] = v
        self.curves = new
        origin = self.origin_of.pop(name, None)
        for ch in children:
            self.origin_of[ch.name] = origin
        if origin is not None and origin in self.name_map:
            lst = self.name_map[origin]
            pos = lst.index(name) if name in lst else len(lst)
            self.name_map[origin] = lst[:pos] + [ch.name for ch in children] + lst[pos + 1:]
        if name in self.added:
            pos = self.added.index(name)
            self.added = self.added[:pos] + [ch.name for ch in children] + self.added[pos + 1:]

    def remove_curves(self, names: list[str]) -> None:
        for n in names:
            self.curves.pop(n, None)
            origin = self.origin_of.pop(n, None)
            if origin is not None and origin in self.name_map:
                self.name_map[origin] = [x for x in self.name_map[origin] if x != n]
            if n in self.added:
                self.added.remove(n)
        used = {c.start for c in self.curves.values()} | {c.end for c in self.curves.values()}
        self.points = {p: uv for p, uv in self.points.items() if p in used}

    # -- 仿射 --------------------------------------------------------------
    def apply_affine(self, M: np.ndarray) -> None:
        def tf(p):
            x = M @ np.array([p[0], p[1], 1.0])
            return (float(x[0]), float(x[1]))
        self.points = {n: tf(p) for n, p in self.points.items()}
        for c in self.curves.values():
            if c.ctrl:
                c.ctrl = [tf(p) for p in c.ctrl]
        self.affine = M @ self.affine

    def normalize(self) -> None:
        """平移使 bbox 左下角回到原点（数据集与特征的坐标约定）。"""
        if not self.points:
            return
        umin = min(p[0] for p in self.points.values())
        vmin = min(p[1] for p in self.points.values())
        if abs(umin) > 1e-12 or abs(vmin) > 1e-12:
            self.apply_affine(np.array([[1.0, 0.0, -umin], [0.0, 1.0, -vmin], [0.0, 0.0, 1.0]]))

    def transform_xy(self, p: tuple[float, float]) -> tuple[float, float]:
        x = self.affine @ np.array([p[0], p[1], 1.0])
        return (float(x[0]), float(x[1]))

    # -- 导出 --------------------------------------------------------------
    def to_geometry(self, section_id: str) -> SectionGeometry:
        self.normalize()
        ua, va, vsign = _PLANE_AXES[self.plane]
        normal = 3 - ua - va

        def to_xyz(uv):
            xyz = [0.0, 0.0, 0.0]
            xyz[ua] = uv[0]
            xyz[va] = vsign * uv[1]
            xyz[normal] = self.normal_coord
            return (xyz[0], xyz[1], xyz[2])

        geo = SectionGeometry(section_id=section_id, section_name=self.section_name,
                              source="aug", plane=self.plane)
        for idx, (name, uv) in enumerate(self.points.items()):
            geo.points[name] = Point(name=name, runtime_id=idx, xyz=to_xyz(uv), uv=uv, uv_local=uv)
        if not geo.points:
            return geo
        geo.u_min = geo.v_min = 0.0
        geo.width = max(p[0] for p in self.points.values())
        geo.height = max(p[1] for p in self.points.values())
        for idx, wc in enumerate(self.curves.values()):
            if wc.start not in geo.points or wc.end not in geo.points:
                continue
            p0, p1 = self.points[wc.start], self.points[wc.end]
            if wc.ctrl:
                poly = _bezier_polyline(p0, p1, wc.ctrl[0], wc.ctrl[1])
                control = (to_xyz(wc.ctrl[0]), to_xyz(wc.ctrl[1]))
            else:
                poly = [p0, p1]
                control = None
            geo.curves[wc.name] = Curve(
                name=wc.name, runtime_id=idx, start=wc.start, end=wc.end, control_xyz=control,
                polyline_local=poly, length=_polyline_length(poly), chord=math.dist(p0, p1),
            )
        return geo

    def to_dict(self) -> dict:
        return {
            "section_name": self.section_name, "plane": self.plane, "normal_coord": self.normal_coord,
            "points": {n: [p[0], p[1]] for n, p in self.points.items()},
            "curves": [{"name": c.name, "start": c.start, "end": c.end,
                        "ctrl": [list(p) for p in c.ctrl] if c.ctrl else None}
                       for c in self.curves.values()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "_Work":
        w = cls.__new__(cls)
        w.section_name = d["section_name"]
        w.plane = d["plane"]
        w.normal_coord = float(d.get("normal_coord", 0.0))
        w.points = {n: (float(p[0]), float(p[1])) for n, p in d["points"].items()}
        w.curves = {}
        for c in d["curves"]:
            ctrl = [tuple(p) for p in c["ctrl"]] if c.get("ctrl") else None
            w.curves[c["name"]] = _WCurve(c["name"], c["start"], c["end"], ctrl)
        w.name_map = {}
        w.origin_of = {}
        w.added = []
        w.affine = np.eye(3)
        w.affine_ok = False
        w._pidx = w._cidx = 0
        return w


# ---------------------------------------------------------------------------
# 几何小工具
# ---------------------------------------------------------------------------

def _unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > GEOM_EPS else (0.0, 0.0)


def _angle_deg(d1, d2) -> float:
    dot = abs(d1[0] * d2[0] + d1[1] * d2[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _point_in_polygon(p, poly) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xin = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xin > x:
                inside = not inside
    return inside


def _bbox_of(poly) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def _rect_iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > GEOM_EPS else 0.0


def _seg_seg_distance(a1, a2, b1, b2) -> float:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2 = orient(a1, a2, b1), orient(a1, a2, b2)
    o3, o4 = orient(b1, b2, a1), orient(b1, b2, a2)
    if (o1 * o2 < 0) and (o3 * o4 < 0):
        return 0.0

    def pt_seg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < GEOM_EPS else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
    return min(pt_seg(a1, b1, b2), pt_seg(a2, b1, b2), pt_seg(b1, a1, a2), pt_seg(b2, a1, a2))


def _curve_dir(geo: SectionGeometry, cname: str) -> tuple[float, float]:
    poly = geo.curves[cname].polyline_local
    return _unit(poly[-1][0] - poly[0][0], poly[-1][1] - poly[0][1])


def _endpoints_of(geo: SectionGeometry, curves: list[str]) -> list[str]:
    out: list[str] = []
    for c in curves:
        cv = geo.curves.get(c)
        if cv is None:
            continue
        for p in (cv.start, cv.end):
            if p not in out:
                out.append(p)
    return out


def _curves_centroid(geo: SectionGeometry, curves: list[str]) -> tuple[float, float]:
    cx = cy = w = 0.0
    for c in curves:
        cv = geo.curves.get(c)
        if cv is None:
            continue
        mid = cv.polyline_local[len(cv.polyline_local) // 2]
        cx += mid[0] * cv.length
        cy += mid[1] * cv.length
        w += cv.length
    return (cx / w, cy / w) if w > GEOM_EPS else (0.0, 0.0)


# ---------------------------------------------------------------------------
# T1 加点拆线
# ---------------------------------------------------------------------------

def _sample_ts(rng: random.Random, k: int, lo=0.2, hi=0.8, gap=0.15) -> list[float]:
    for _ in range(50):
        ts = sorted(rng.uniform(lo, hi) for _ in range(k))
        if all(ts[i + 1] - ts[i] >= gap for i in range(k - 1)):
            return ts
    return [lo + (hi - lo) * (i + 1) / (k + 1) for i in range(k)]


def _split_curve(work: _Work, wc: _WCurve, ts: list[float]) -> list[_WCurve]:
    """在参数 ts（升序）处把曲线拆成 len(ts)+1 段；贝塞尔用 de Casteljau。"""
    p0, p1 = work.points[wc.start], work.points[wc.end]
    pieces: list[_WCurve] = []
    cur_start = wc.start
    cur_ctrl = list(wc.ctrl) if wc.ctrl else None
    cur_p0 = p0
    prev = 0.0
    for i, t in enumerate(ts):
        tr = (t - prev) / (1.0 - prev)
        if cur_ctrl:
            c1, c2 = cur_ctrl
            a = _lerp(cur_p0, c1, tr)
            b = _lerp(c1, c2, tr)
            c = _lerp(c2, p1, tr)
            d = _lerp(a, b, tr)
            e = _lerp(b, c, tr)
            m = _lerp(d, e, tr)
            left_ctrl, right_ctrl = [a, d], [e, c]
        else:
            m = _lerp(cur_p0, p1, tr)
            left_ctrl = right_ctrl = None
        mid_name = work.new_point(m)
        pieces.append(_WCurve(f"{wc.name}__s{i}", cur_start, mid_name, left_ctrl))
        cur_start, cur_p0, cur_ctrl, prev = mid_name, m, right_ctrl, t
    pieces.append(_WCurve(f"{wc.name}__s{len(ts)}", cur_start, wc.end, cur_ctrl))
    return pieces


def op_split(work: _Work, rng: random.Random, graph: SectionGraph,
             frac: float | None = None, max_k: int = 3) -> dict | None:
    geo = graph.geo
    frac = rng.uniform(0.2, 0.6) if frac is None else frac
    min_len = max(4.0, 0.03 * geo.diag)
    cands = [n for n in work.curves
             if n in geo.curves and not graph.curve_topo[n].transition_like
             and geo.curves[n].length >= min_len]
    if not cands:
        return None
    n_pick = max(1, round(frac * len(cands)))
    chosen = set(rng.sample(cands, min(n_pick, len(cands))))
    splits: dict[str, int] = {}
    for name in list(work.curves):
        if name not in chosen:
            continue
        k = rng.randint(1, max_k)
        children = _split_curve(work, work.curves[name], _sample_ts(rng, k))
        work.replace_curve(name, children)
        splits[name] = k
    return {"frac": round(frac, 3), "n_split": len(splits), "splits": splits}


# ---------------------------------------------------------------------------
# T2 截面拉伸（各向异性缩放）
# ---------------------------------------------------------------------------

def op_scale(work: _Work, rng: random.Random, graph: SectionGraph | None = None,
             s_lo: float = 0.6, s_hi: float = 1.6, margin: float = 1.2) -> dict | None:
    W, H = work.bbox_size()
    su = sv = None
    for _ in range(60):
        a, b = rng.uniform(s_lo, s_hi), rng.uniform(s_lo, s_hi)
        ratio = (H * b) / max(W * a, GEOM_EPS)
        if (H >= W and ratio >= margin) or (H < W and ratio <= 1.0 / margin):
            su, sv = a, b
            break
    if su is None:                     # 近方形截面：退化为等比缩放，不改变长短轴关系
        su = sv = rng.uniform(s_lo, s_hi)
    work.apply_affine(np.diag([su, sv, 1.0]))
    work.normalize()
    return {"su": round(su, 4), "sv": round(sv, 4)}


# ---------------------------------------------------------------------------
# T5 刚体变换 + 坐标平面
# ---------------------------------------------------------------------------

def _rigid_matrix(kind: str) -> np.ndarray:
    return {
        "rot90": np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        "rot180": np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]),
        "rot270": np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        "mirror_u": np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        "mirror_v": np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]),
    }[kind]


def op_rigid(work: _Work, rng: random.Random, graph: SectionGraph | None = None,
             kind: str | None = None, plane: str | None = None,
             allowed_kinds: list[str] | None = None) -> dict | None:
    kind = kind or rng.choice(allowed_kinds or _RIGID_KINDS)
    work.apply_affine(_rigid_matrix(kind))
    work.normalize()
    plane = plane or rng.choice(list(_PLANE_AXES))
    work.plane = plane
    return {"kind": kind, "plane": plane}


# ---------------------------------------------------------------------------
# T3 移壁 / 移筋（CAD 的 stretch：切一条不经过任何节点的水平/竖直线，
# 线一侧的全部几何整体平移，跨线的直线段被拉长/缩短）
# ---------------------------------------------------------------------------

def _tjunction_tips(work: _Work, graph: SectionGraph) -> dict[str, str]:
    """T 型搭接尖端：只被一条曲线引用、却落在另一条（直的）曲线内部的点 -> 宿主曲线名。"""
    geo = graph.geo
    ref: Counter = Counter()
    for c in work.curves.values():
        ref[c.start] += 1
        ref[c.end] += 1
    tips: dict[str, str] = {}
    for p, n in ref.items():
        if n != 1:
            continue
        rep = graph.point_rep.get(p, p)
        own = next(c.name for c in work.curves.values() if p in (c.start, c.end))
        hosts = Counter(e.orig_curve for e in graph.edges
                        if rep in (e.node_a, e.node_b) and e.orig_curve != own
                        and not e.orig_curve.startswith(BRIDGE_PREFIX))
        for host, k in hosts.items():
            if k >= 2 and host in work.curves and host in geo.curves and geo.curves[host].is_straight:
                tips[p] = host
                break
    return tips


def _restretch_bezier(work: _Work, name: str, old_a, old_b) -> None:
    """跨线被拉伸的平直贝塞尔：控制点按其在旧弦上的参数位置重新落到新弦上（保留微小法向偏移）。"""
    wc = work.curves[name]
    if not wc.ctrl:
        return
    new_a, new_b = work.points[wc.start], work.points[wc.end]
    dx, dy = old_b[0] - old_a[0], old_b[1] - old_a[1]
    L2 = dx * dx + dy * dy
    if L2 < GEOM_EPS:
        return
    ndx, ndy = new_b[0] - new_a[0], new_b[1] - new_a[1]
    out = []
    for q in wc.ctrl:
        s = ((q[0] - old_a[0]) * dx + (q[1] - old_a[1]) * dy) / L2
        off = (q[0] - (old_a[0] + s * dx), q[1] - (old_a[1] + s * dy))
        out.append((new_a[0] + s * ndx + off[0], new_a[1] + s * ndy + off[1]))
    wc.ctrl = out


def _reproject_tips(work: _Work, tips: dict[str, str]) -> None:
    for p, host in tips.items():
        hc = work.curves.get(host)
        if hc is None or p not in work.points:
            continue
        a, b = work.points[hc.start], work.points[hc.end]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 < GEOM_EPS:
            continue
        q = work.points[p]
        t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2
        work.points[p] = (a[0] + t * dx, a[1] + t * dy)


def op_move(work: _Work, rng: random.Random, graph: SectionGraph, margin: float = 3.0,
            compress_frac: float = 0.4, stretch_frac: float = 0.5) -> dict | None:
    geo = graph.geo
    nodes = graph.nodes
    if not nodes:
        return None
    tips = _tjunction_tips(work, graph)
    for axis in rng.sample([0, 1], 2):
        normal = (1.0, 0.0) if axis == 0 else (0.0, 1.0)
        levels = sorted({round(p[axis], 6) for p in nodes.values()})
        intervals = [(a, b) for a, b in zip(levels, levels[1:]) if b - a >= 1.5]
        rng.shuffle(intervals)
        for a, b in intervals[:8]:
            line = rng.uniform(a + 0.3 * (b - a), b - 0.3 * (b - a))
            crossing = [e for e in graph.edges
                        if (nodes[e.node_a][axis] - line) * (nodes[e.node_b][axis] - line) < 0]
            if not crossing:
                continue
            ok = True
            span_min = math.inf
            crossing_curves: set[str] = set()
            for e in crossing:
                wc = work.curves.get(e.orig_curve)
                cv = geo.curves.get(e.orig_curve)
                if (e.orig_curve.startswith(BRIDGE_PREFIX) or wc is None or cv is None
                        or not cv.is_straight
                        or _angle_deg(_curve_dir(geo, e.orig_curve), normal) > 1.0):
                    ok = False
                    break
                crossing_curves.add(e.orig_curve)
                span_min = min(span_min, abs(nodes[e.node_a][axis] - nodes[e.node_b][axis]))
            if not ok:
                continue
            lo = -min(compress_frac * span_min, (b - a) - margin)
            hi = stretch_frac * span_min
            if hi < 1.0 and lo > -1.0:
                continue
            for _ in range(50):
                delta = rng.uniform(lo, hi)
                if abs(delta) >= 1.0:
                    break
            else:
                delta = hi if hi >= 1.0 else lo
            shift = (delta * normal[0], delta * normal[1])
            old_ends = {n: (work.points[work.curves[n].start], work.points[work.curves[n].end])
                        for n in crossing_curves}
            work.points = {n: ((p[0] + shift[0], p[1] + shift[1]) if p[axis] > line else p)
                           for n, p in work.points.items()}
            for c in work.curves.values():
                if c.ctrl and c.name not in crossing_curves:
                    c.ctrl = [((q[0] + shift[0], q[1] + shift[1]) if q[axis] > line else q) for q in c.ctrl]
            for n, (oa, ob) in old_ends.items():
                _restretch_bezier(work, n, oa, ob)
            _reproject_tips(work, tips)
            work.affine_ok = False
            work.normalize()
            return {"axis": "u" if axis == 0 else "v", "line": round(line, 3), "delta": round(delta, 3),
                    "n_crossing": len(crossing)}
    return None


# ---------------------------------------------------------------------------
# T4 加筋 / 删筋
# ---------------------------------------------------------------------------

def _line_polygon_hits(poly, horizontal: bool, coord: float):
    """水平/竖直直线与多边形边的交点 [(point, edge_index)]。"""
    hits = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if horizontal:
            if (a[1] - coord) * (b[1] - coord) < 0:
                t = (coord - a[1]) / (b[1] - a[1])
                hits.append(((a[0] + t * (b[0] - a[0]), coord), i))
        else:
            if (a[0] - coord) * (b[0] - coord) < 0:
                t = (coord - a[0]) / (b[0] - a[0])
                hits.append(((coord, a[1] + t * (b[1] - a[1])), i))
    return hits


def _host_curve_at(graph: SectionGraph, cell, p) -> str | None:
    """点 p 落在 cell 边界哪条原始直线曲线的内部（距端点节点 >= 3mm）。"""
    edge_by_id = {e.edge_id: e for e in graph.edges}
    geo = graph.geo
    for eid in cell.edge_ids:
        e = edge_by_id[eid]
        if e.orig_curve.startswith(BRIDGE_PREFIX) or e.orig_curve not in geo.curves:
            continue
        for k in range(len(e.polyline) - 1):
            a, b = e.polyline[k], e.polyline[k + 1]
            if _seg_seg_distance(p, p, a, b) <= 1e-6:
                cv = geo.curves[e.orig_curve]
                if not cv.is_straight or graph.curve_topo[e.orig_curve].transition_like:
                    return None
                if min(math.dist(p, graph.nodes[e.node_a]), math.dist(p, graph.nodes[e.node_b])) < 3.0:
                    return None
                return e.orig_curve
    return None


def op_rib(work: _Work, rng: random.Random, graph: SectionGraph, mode: str | None = None) -> dict | None:
    if not graph.cells:
        return None
    geo = graph.geo
    mode = mode or rng.choice(["add", "add", "delete"])
    if mode == "delete":
        ribs = []
        for chain in graph.chains:
            curves = [c for c in chain if c in geo.curves]
            if curves and all(graph.curve_topo[c].n_cells >= 2 and not graph.curve_topo[c].on_outer
                              for c in curves):
                ribs.append(curves)
        if not ribs:
            mode = "add"
        else:
            curves = rng.choice(ribs)
            adjacent = {cid for c in curves for cid in graph.curve_topo[c].cell_ids}
            work.remove_curves(curves)
            work.affine_ok = False
            return {"mode": "delete", "curves": curves, "expected_cell_delta": -(len(adjacent) - 1)}

    max_area = max(c.area for c in graph.cells)
    cells = [c for c in graph.cells if c.area >= 0.05 * max_area]
    weights = [c.area for c in cells]
    W, H = work.bbox_size()
    min_gap = max(3.0, 0.08 * max(W, H))
    for _ in range(12):
        cell = rng.choices(cells, weights=weights, k=1)[0]
        bw, bh = cell.bbox[2] - cell.bbox[0], cell.bbox[3] - cell.bbox[1]
        horizontal = bh >= bw                     # 筋沿短边方向跨越
        for _ in range(25):
            t = rng.uniform(0.25, 0.75)
            coord = (cell.bbox[1] + t * bh) if horizontal else (cell.bbox[0] + t * bw)
            hits = _line_polygon_hits(cell.polygon, horizontal, coord)
            if len(hits) != 2:
                continue
            # 与平行的多边形边保持最小间距
            idx = 1 if horizontal else 0
            too_close = False
            n = len(cell.polygon)
            for i in range(n):
                a, b = cell.polygon[i], cell.polygon[(i + 1) % n]
                if abs(a[idx] - b[idx]) < 1e-6 and abs(a[idx] - coord) < min_gap:
                    too_close = True
                    break
            if too_close:
                continue
            (pa, _), (pb, _) = hits
            if math.dist(pa, pb) < 5.0:
                continue
            host_a = _host_curve_at(graph, cell, pa)
            host_b = _host_curve_at(graph, cell, pb)
            if host_a is None or host_b is None or host_a == host_b:
                continue
            na, nb = work.new_point(pa), work.new_point(pb)
            cname = work.new_curve_name()
            work.curves[cname] = _WCurve(cname, na, nb, None)
            work.origin_of[cname] = None
            work.added.append(cname)
            work.affine_ok = False
            return {"mode": "add", "curves": [cname], "cell": cell.cell_id,
                    "horizontal": horizontal, "expected_cell_delta": 1}
    return None


OPS = {"split": op_split, "scale": op_scale, "rigid": op_rigid, "move": op_move, "rib": op_rib}
OPS_NEED_GRAPH = {"split", "move", "rib"}


# ---------------------------------------------------------------------------
# 标签传播
# ---------------------------------------------------------------------------

def _target_centroid(t: SilverTarget, graph: SectionGraph) -> tuple[float, float]:
    if t.entity_type == "face" and t.face_ids:
        for c in graph.cells:
            if c.cell_id == t.face_ids[0]:
                return c.centroid
        for s in graph.subcells:
            if s.subcell_id == t.face_ids[0]:
                return s.centroid
    if t.entity_type == "point" and t.point_names:
        pts = [graph.geo.points[p].uv_local for p in t.point_names if p in graph.geo.points]
        if pts:
            return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return _curves_centroid(graph.geo, t.curve_names)


def derive_chamber_targets(graph: SectionGraph, section_id: str) -> list[SilverTarget]:
    """按定义派生腔体：闭合 cell（有子腔的父 cell 让位给子腔；碎片 cell 剔除），自上而下编号。"""
    if not graph.cells:
        return []
    parents = {s.parent_cell for s in graph.subcells}
    max_area = max(c.area for c in graph.cells)
    faces = [c for c in graph.cells if c.cell_id not in parents and c.area >= 0.05 * max_area]
    faces += list(graph.subcells)
    faces.sort(key=lambda f: (-f.centroid[1], f.centroid[0]))
    out = []
    for k, f in enumerate(faces, 1):
        fid = f.cell_id if hasattr(f, "cell_id") else f.subcell_id
        out.append(SilverTarget(
            section_id=section_id, region_name=f"chamber_{k}", function="enclosed",
            label_id=CHAMBER_ID, entity_type="face", face_ids=[fid],
            curve_names=list(f.curve_names), point_names=list(f.point_names), ordinal=k,
            flags=["augmented", "aug_rederived"], match_score=1.0,
        ))
    return out


def propagate_targets(src: SectionBundle, graph: SectionGraph, work: _Work, ops_kinds: set[str],
                      section_id: str) -> tuple[list[SilverTarget], dict[str, str | None]]:
    """把源截面的 silver 目标映射到变体：曲线按 name_map，面按 cell 配对，拓扑变化时重派生腔体。"""
    geo = graph.geo
    topo_changed = "rib" in ops_kinds
    src_faces = {c.cell_id: c for c in src.graph.cells}
    src_faces.update({s.subcell_id: s for s in src.graph.subcells})
    new_faces = [(c.cell_id, c) for c in graph.cells] + [(s.subcell_id, s) for s in graph.subcells]
    cell_map: dict[str, str | None] = {}

    def match_face(fid: str) -> str | None:
        sf = src_faces.get(fid)
        if sf is None:
            return None
        mapped = {n for c in sf.curve_names for n in work.name_map.get(c, [])}
        cen = work.transform_xy(sf.centroid) if work.affine_ok else sf.centroid
        bb = _bbox_of([work.transform_xy(p) for p in sf.polygon]) if work.affine_ok else sf.bbox
        best, best_score = None, -1.0
        for nid, nf in new_faces:
            cur = set(nf.curve_names)
            jac = len(mapped & cur) / len(mapped | cur) if (mapped | cur) else 0.0
            score = 2.0 * jac + (1.0 if _point_in_polygon(cen, nf.polygon) else 0.0) + _rect_iou(bb, nf.bbox)
            if score > best_score:
                best, best_score = nid, score
        return best if best_score >= 1.0 else None

    out: list[SilverTarget] = []
    for t in src.silver:
        if "synthetic" in t.flags or t.is_empty:      # 源本身为空的目标（数据集标注错误）不传播
            continue
        if t.entity_type == "face":
            if topo_changed:
                continue
            fids = []
            for f in t.face_ids:
                m = match_face(f)
                cell_map[f] = m
                if m is not None and m not in fids:
                    fids.append(m)
            curves, points = [], []
            for fid in fids:
                nf = next(nf for nid, nf in new_faces if nid == fid)
                curves += [c for c in nf.curve_names if c not in curves]
                points += [p for p in nf.point_names if p not in points]
            nt = SilverTarget(section_id=section_id, region_name=t.region_name, function=t.function,
                              label_id=t.label_id, entity_type="face", face_ids=fids,
                              curve_names=curves, point_names=points, ordinal=t.ordinal,
                              flags=[f for f in t.flags] + ["augmented"], match_score=t.match_score)
        else:
            curves: list[str] = []
            for c in t.curve_names:
                for n in work.name_map.get(c, []):
                    if n in geo.curves and n not in curves:
                        curves.append(n)
            if t.entity_type == "point":
                points = [p for p in t.point_names if p in geo.points]
            else:
                points = _endpoints_of(geo, curves)
            flags = [f for f in t.flags] + ["augmented"]
            if not curves and t.curve_names and all(not work.name_map.get(c) for c in t.curve_names):
                flags.append("aug_removed")
            nt = SilverTarget(section_id=section_id, region_name=t.region_name, function=t.function,
                              label_id=t.label_id, entity_type=t.entity_type, face_ids=[],
                              curve_names=curves, point_names=points, ordinal=t.ordinal,
                              flags=flags, match_score=t.match_score)
        out.append(nt)

    if topo_changed:
        out += derive_chamber_targets(graph, section_id)
    for k, cname in enumerate(work.added):
        if cname not in geo.curves:
            continue
        out.append(SilverTarget(
            section_id=section_id, region_name=f"stiffener_aug{k}", function="stiffener",
            label_id=INTERNAL_WEB_ID, entity_type="curve", curve_names=[cname],
            point_names=_endpoints_of(geo, [cname]), flags=["augmented", "aug_added"], match_score=1.0,
        ))
    if graph.is_closed:
        t = SilverTarget(section_id=section_id, region_name="outer_contour", function="outer_contour",
                         label_id=OUTER_ID, entity_type="curve")
        _match_outer_contour(graph, t)
        t.flags.append("synthetic")
        out.append(t)
    return out, cell_map


def renumber_ordinals(targets: list[SilverTarget], graph: SectionGraph) -> None:
    """序数按新几何重排（自上而下、自左向右），与 mapper 的实例排序口径一致。"""
    by_label: dict[str, list[SilverTarget]] = {}
    for t in targets:
        if "synthetic" in t.flags or t.is_empty:
            continue
        by_label.setdefault(t.label_id, []).append(t)
    for label_id, group in by_label.items():
        short = label_id.rsplit(".", 1)[-1]
        if short not in ORDINAL_LABELS:
            for t in group:
                t.ordinal = None
            continue
        by_base: dict[str, list[SilverTarget]] = {}
        for t in group:
            if t.ordinal is None:
                continue
            by_base.setdefault(_ORD_RE.sub("", t.region_name.lower()), []).append(t)
        for base, g in by_base.items():
            if len(g) < 2:
                continue
            g.sort(key=lambda t: (-_target_centroid(t, graph)[1], _target_centroid(t, graph)[0]))
            for k, t in enumerate(g, 1):
                t.ordinal = k
                t.region_name = f"{base}_{k}"


# ---------------------------------------------------------------------------
# 校验门
# ---------------------------------------------------------------------------

def transform_region(region: Region, M: np.ndarray) -> Region:
    """bbox 标注随仿射变换（缩放/旋转/镜像/平移）。"""
    def tf(p):
        x = M @ np.array([p[0], p[1], 1.0])
        return (float(x[0]), float(x[1]))
    b = dict(region.bbox or {})
    s_area = math.sqrt(abs(float(np.linalg.det(M[:2, :2]))))
    if "x" in b and "y" in b and ("height" in b or "depth" in b) and "width" in b:
        x, y = float(b["x"]), float(b["y"])
        if "height" in b:
            w, h = float(b["width"]), float(b["height"])
        else:
            w, h = float(b["depth"]), float(b["width"])       # 凹槽：depth 沿 u，width 沿 v
        corners = [tf((x, y)), tf((x + w, y)), tf((x, y + h)), tf((x + w, y + h))]
        x0, y0, x1, y1 = _bbox_of(corners)
        b["x"], b["y"] = x0, y0
        if "height" in b:
            b["width"], b["height"] = x1 - x0, y1 - y0
        else:
            b["depth"], b["width"] = x1 - x0, y1 - y0
    elif "x" in b and "y" in b:
        b["x"], b["y"] = tf((float(b["x"]), float(b["y"])))
    if "radius" in b:
        b["radius"] = float(b["radius"]) * s_area
    return Region(name=region.name, function=region.function, bbox=b, notes=region.notes)


def fingerprint(geo: SectionGeometry) -> str:
    pts = sorted((round(p.uv_local[0] * 2) / 2, round(p.uv_local[1] * 2) / 2, p.name)
                 for p in geo.points.values())
    index = {name: i for i, (_, _, name) in enumerate(pts)}
    coords = [(u, v) for u, v, _ in pts]
    edges = sorted(tuple(sorted((index[c.start], index[c.end]))) for c in geo.curves.values())
    return hashlib.md5(json.dumps([coords, edges]).encode()).hexdigest()


def adjacent_pairs(graph: SectionGraph) -> set[tuple[str, str]]:
    """共享平面化节点（含经桥边相连）的原始曲线对。"""
    node_curves: dict[str, set[str]] = {}
    for e in graph.edges:
        if e.orig_curve.startswith(BRIDGE_PREFIX):
            continue
        for n in (e.node_a, e.node_b):
            node_curves.setdefault(n, set()).add(e.orig_curve)
    adjacent: set[tuple[str, str]] = set()
    for group in node_curves.values():
        g = sorted(group)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                adjacent.add((g[i], g[j]))
    for e in graph.edges:
        if e.orig_curve.startswith(BRIDGE_PREFIX):
            for a in node_curves.get(e.node_a, ()):
                for b in node_curves.get(e.node_b, ()):
                    if a != b:
                        adjacent.add(tuple(sorted((a, b))))
    return adjacent


def min_clearance(graph: SectionGraph, origin_of: dict[str, str | None] | None = None,
                  src_adjacent: set[tuple[str, str]] | None = None) -> float:
    """不相邻曲线对之间的最小距离。

    给定 origin_of / src_adjacent 时，源截面中相邻（或同源）的曲线对不计入——
    校验门只关心"变换是否制造了新的贴近"。
    """
    geo = graph.geo
    adjacent = adjacent_pairs(graph)
    names = sorted(geo.curves)
    best = math.inf
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if (names[i], names[j]) in adjacent:
                continue
            if origin_of is not None and src_adjacent is not None:
                oa, ob = origin_of.get(names[i]), origin_of.get(names[j])
                if oa is not None and ob is not None and (oa == ob or tuple(sorted((oa, ob))) in src_adjacent):
                    continue
            pa, pb = geo.curves[names[i]].polyline_local, geo.curves[names[j]].polyline_local
            for k in range(len(pa) - 1):
                for m in range(len(pb) - 1):
                    best = min(best, _seg_seg_distance(pa[k], pa[k + 1], pb[m], pb[m + 1]))
    return best


def _label_pairs(targets: list[SilverTarget]) -> set[frozenset]:
    per_curve: dict[str, set[str]] = {}
    for t in targets:
        if "synthetic" in t.flags or t.entity_type == "face":
            continue
        short = t.label_id.rsplit(".", 1)[-1]
        for c in t.curve_names:
            per_curve.setdefault(c, set()).add(short)
    pairs: set[frozenset] = set()
    for labels in per_curve.values():
        ls = sorted(labels)
        for i in range(len(ls)):
            for j in range(i + 1, len(ls)):
                pairs.add(frozenset((ls[i], ls[j])))
    return pairs


def affine_cross_check(src: SectionBundle, geo: SectionGeometry, graph: SectionGraph, work: _Work,
                       targets: list[SilverTarget], registry: LabelRegistry) -> dict:
    """仿射变换下重跑 bbox 匹配，与传播结果比对。

    返回 {"agreement": 平均 Jaccard, "n": 目标数, "heuristic_agreement": ...}。凹槽与倒角单独统计：
    silver 的 `_match_notch` 按"哪种 depth/width 取向框住的曲线更长"选取向，对镜像敏感；
    `_match_transition` 用 radius 过滤过渡段长度，对各向异性缩放敏感。二者的分歧是 bbox
    启发式的伪影而不是传播错误。
    """
    out: dict = {"agreement": None, "n": 0, "heuristic_agreement": None}
    if not src.record.regions:
        return out
    regions = [transform_region(r, work.affine) for r in src.record.regions]
    rec = SectionRecord(section_id=geo.section_id, shape_family=src.record.shape_family,
                        topology=src.record.topology, geometry=geo, regions=regions, meta=src.record.meta)
    by_name = {t.region_name: t for t in build_silver_targets(rec, graph, registry)}
    vals, notch_vals = [], []
    for t in targets:
        if "synthetic" in t.flags or t.is_empty or "aug_added" in t.flags or "aug_rederived" in t.flags:
            continue
        b = by_name.get(t.region_name)
        if b is None:
            continue
        if t.entity_type == "face":
            sa, sb = set(t.face_ids), set(b.face_ids)
        elif t.entity_type == "point":
            sa, sb = set(t.point_names), set(b.point_names)
        else:
            sa, sb = set(t.curve_names), set(b.curve_names)
        jac = len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0
        heuristic = t.label_id.endswith(".notch") or t.label_id.endswith(".fillet")
        (notch_vals if heuristic else vals).append(jac)
    if vals:
        out["agreement"] = float(np.mean(vals))
        out["n"] = len(vals)
    if notch_vals:
        out["heuristic_agreement"] = float(np.mean(notch_vals))
    return out


@dataclass
class SourceInfo:
    """源截面的缓存量（校验门用）。"""
    clearance: float
    adjacent: set[tuple[str, str]]
    has_subcells: bool
    source_sha256: str = ""
    source_manifest: list[dict] = field(default_factory=list)

    @classmethod
    def of(cls, src: SectionBundle) -> "SourceInfo":
        return cls(clearance=min_clearance(src.graph), adjacent=adjacent_pairs(src.graph),
                   has_subcells=bool(src.graph.subcells), source_sha256=source_sha256(src),
                   source_manifest=source_manifest(src))


def run_gates(src: SectionBundle, geo: SectionGeometry, graph: SectionGraph, work: _Work,
              targets: list[SilverTarget], ops_kinds: set[str], expected_cell_delta: int,
              registry: LabelRegistry, seen: set[str], src_info: SourceInfo) -> tuple[list[str], dict]:
    failures: list[str] = []
    info: dict = {}
    src_clearance = src_info.clearance
    # 1 cell 数
    if len(graph.cells) != len(src.graph.cells) + expected_cell_delta:
        failures.append(f"gate1_cells:{len(graph.cells)}!={len(src.graph.cells) + expected_cell_delta}")
    # 2 目标非空（有意删除的除外；T4 时腔体已重派生）
    for t in targets:
        if "synthetic" in t.flags or "aug_removed" in t.flags or "aug_added" in t.flags:
            continue
        if t.is_empty:
            failures.append(f"gate2_empty:{t.region_name}")
            break
    # 3 标签共存
    extra = _label_pairs(targets) - _label_pairs(src.silver)
    if extra:
        failures.append("gate3_cooccurrence:" + ",".join("+".join(sorted(p)) for p in sorted(map(sorted, extra))))
    # 4 仿射交叉校验
    if work.affine_ok and ops_kinds <= AFFINE_OPS:
        chk = affine_cross_check(src, geo, graph, work, targets, registry)
        agreement = chk["agreement"]
        info["affine_agreement"] = None if agreement is None else round(agreement, 4)
        if chk["heuristic_agreement"] is not None:
            info["affine_agreement_notch_fillet"] = round(chk["heuristic_agreement"], 4)
        if agreement is not None and agreement < AFFINE_AGREEMENT_MIN:
            failures.append(f"gate4_affine:{agreement:.3f}")
    # 5 指纹去重
    fp = fingerprint(geo)
    info["fingerprint"] = fp
    if fp in seen:
        failures.append("gate5_duplicate")
    # 6 合理性
    clearance = min_clearance(graph, work.origin_of, src_info.adjacent)
    info["clearance"] = round(clearance, 3) if math.isfinite(clearance) else None
    # 源截面本身间距就小（薄壁细部）时按比例放宽：缩放 0.6 倍会同比缩小所有间距，不算"新的贴近"
    floor = min(MIN_CLEARANCE_MM, 0.5 * src_clearance) if math.isfinite(src_clearance) else MIN_CLEARANCE_MM
    if clearance < floor - 1e-9:
        failures.append(f"gate6_clearance:{clearance:.2f}<{floor:.2f}")
    sw, sh = sorted((src.graph.geo.width, src.graph.geo.height))
    nw, nh = sorted((geo.width, geo.height))
    for a, b in ((nw, sw), (nh, sh)):
        if b > GEOM_EPS and not (BBOX_RATIO_RANGE[0] - 1e-9 <= a / b <= BBOX_RATIO_RANGE[1] + 1e-9):
            failures.append(f"gate6_bbox_ratio:{a / b:.2f}")
            break
    return failures, info


# ---------------------------------------------------------------------------
# 变体生成
# ---------------------------------------------------------------------------

@dataclass
class AugVariant:
    variant_id: str
    source_id: str
    family: str
    topology: str
    ops: list[dict]
    work: _Work
    geometry: SectionGeometry
    graph: SectionGraph
    silver: list[SilverTarget]
    cell_map: dict[str, str | None]
    info: dict = field(default_factory=dict)
    # Provenance is explicit in every JSONL row.  ``family`` remains for
    # backwards compatibility; ``shape_family`` is the public schema name.
    seed: int = 1
    source_sha256: str = ""
    source_manifest: list[dict] = field(default_factory=list)
    validation_report: dict = field(default_factory=dict)

    @property
    def ops_signature(self) -> str:
        return "+".join(o["kind"] for o in self.ops)

    def to_record(self) -> dict:
        propagated = [
            {"region_name": t.region_name, "label_id": t.label_id,
             "entity_type": t.entity_type, "curve_names": list(t.curve_names),
             "face_ids": list(t.face_ids), "flags": list(t.flags)}
            for t in self.silver
        ]
        return {
            "variant_id": self.variant_id, "source_id": self.source_id, "family": self.family,
            "shape_family": self.family, "topology": self.topology, "ops": self.ops,
            "seed": self.seed, "source_sha256": self.source_sha256,
            "source_manifest": self.source_manifest,
            "geometry": self.work.to_dict(),
            "name_map": self.work.name_map, "cell_map": self.cell_map,
            "silver": [asdict(t) for t in self.silver],
            "propagated_labels": propagated,
            "validation_report": self.validation_report,
            "info": self.info,
        }


def make_variant(src: SectionBundle, registry: LabelRegistry, rng: random.Random, ops_kinds: list[str],
                 variant_id: str, seen: set[str], src_info: SourceInfo | None = None,
                 seed: int = 1) -> tuple[AugVariant | None, str]:
    src_info = src_info or SourceInfo.of(src)
    work = _Work(src.graph.geo)
    applied: list[dict] = []
    expected_delta = 0
    for kind in OP_ORDER:
        if kind not in ops_kinds:
            continue
        graph_now = build_section_graph(work.to_geometry(variant_id)) if kind in OPS_NEED_GRAPH else None
        if kind == "rigid" and src_info.has_subcells:
            # 子腔（B 字形"双腔"）由竖直方向的宽度轮廓腰线定义，转 90° 会改变约定；只做保持竖轴的变换
            params = op_rigid(work, rng, graph_now, allowed_kinds=["rot180", "mirror_u", "mirror_v"])
        else:
            params = OPS[kind](work, rng, graph_now)
        if params is None:
            return None, f"not_applicable:{kind}"
        if kind == "rib":
            expected_delta += params["expected_cell_delta"]
        applied.append({"kind": kind, "params": params})
    geo = work.to_geometry(variant_id)
    if not geo.curves:
        return None, "empty_geometry"
    graph = build_section_graph(geo)
    kinds = {o["kind"] for o in applied}
    targets, cell_map = propagate_targets(src, graph, work, kinds, variant_id)
    failures, info = run_gates(src, geo, graph, work, targets, kinds, expected_delta, registry, seen, src_info)
    if failures:
        return None, failures[0].split(":")[0]
    gate_prefixes = {
        "gate1_cells": "cell_count", "gate2_empty": "targets_non_empty",
        "gate3_cooccurrence": "label_cooccurrence", "gate4_affine": "affine_agreement",
        "gate5_duplicate": "unique_geometry", "gate6_clearance": "geometry_reasonable",
    }
    validation_report = {
        "passed": True,
        "gates": {name: {"passed": True} for name in gate_prefixes.values()},
        "failures": [],
    }
    renumber_ordinals(targets, graph)
    var = AugVariant(variant_id=variant_id, source_id=src.record.section_id, family=src.record.shape_family,
                     topology=src.record.topology, ops=applied, work=work, geometry=geo, graph=graph,
                     silver=targets, cell_map=cell_map, info=info, seed=seed,
                     source_sha256=src_info.source_sha256, source_manifest=src_info.source_manifest,
                     validation_report=validation_report)
    return var, "ok"


def sample_ops(rng: random.Random, allowed: list[str]) -> list[str]:
    n = 1 if rng.random() >= 0.4 else rng.choice([2, 3])
    n = min(n, len(allowed))
    pool = list(allowed)
    chosen: list[str] = []
    while pool and len(chosen) < n:
        w = [OP_WEIGHTS[k] for k in pool]
        pick = rng.choices(pool, weights=w, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return [k for k in OP_ORDER if k in chosen]


def _has_labels(b: SectionBundle) -> bool:
    return any(not t.is_empty and "synthetic" not in t.flags for t in b.silver)


def select_pilot_bundles(bundles: list[SectionBundle], limit: int = 5) -> list[SectionBundle]:
    """Choose a deterministic, shape-family-diverse pilot set.

    The default examples cover open/flanged, multi-cell/internal-web,
    branched, and transition-rich sections.  Missing examples are replaced
    by a different labelled shape family.  The source corpus is read only.
    """
    eligible = sorted((b for b in bundles if _has_labels(b) and b.graph.geo.curves),
                      key=lambda b: (b.record.shape_family, b.record.section_id))
    by_id = {b.record.section_id: b for b in eligible}
    chosen = [by_id[sid] for sid in PILOT_SECTION_IDS if sid in by_id][:limit]
    families = {b.record.shape_family for b in chosen}
    if len(chosen) >= limit:
        return chosen
    for b in eligible:
        if b.record.shape_family not in families:
            chosen.append(b)
            families.add(b.record.shape_family)
        if len(chosen) >= limit:
            return chosen
    for b in eligible:
        if b not in chosen:
            chosen.append(b)
        if len(chosen) >= limit:
            break
    return chosen


def _label_counts(targets_iter) -> Counter:
    c: Counter = Counter()
    for t in targets_iter:
        if t.is_empty or "synthetic" in t.flags:
            continue
        c[t.label_id.rsplit(".", 1)[-1]] += 1
    return c


def generate_variants(bundles: list[SectionBundle], registry: LabelRegistry, per_section: int = 20,
                      seed: int = 1, quota: int = 200, max_attempt_factor: int = 6,
                      ops_allowed: list[str] | None = None) -> tuple[list[AugVariant], dict]:
    """为每个有标签的截面生成 per_section 个变体，再按 label 配额补齐。"""
    ops_allowed = ops_allowed or list(OP_WEIGHTS)
    variants: list[AugVariant] = []
    rejections: Counter = Counter()
    rejections_by_ops: Counter = Counter()
    attempts_total = 0
    seen: set[str] = set()
    info_cache: dict[str, SourceInfo] = {}
    counters: dict[str, int] = {}

    def gen_for(src: SectionBundle, n_target: int, cap: int) -> int:
        sid = src.record.section_id
        rng = random.Random(f"{seed}:{sid}:{counters.get(sid, 0)}")
        if sid not in info_cache:
            info_cache[sid] = SourceInfo.of(src)
        allowed = [k for k in ops_allowed if k != "rib" or src.graph.is_closed]
        made = 0
        attempts = 0
        nonlocal attempts_total
        while made < n_target and attempts < n_target * max_attempt_factor and counters.get(sid, 0) < cap:
            attempts += 1
            attempts_total += 1
            k = counters.get(sid, 0)
            vid = f"{sid}@aug{k:03d}"
            ops = sample_ops(rng, allowed)
            var, reason = make_variant(src, registry, rng, ops, vid, seen, info_cache[sid], seed=seed)
            if var is None:
                rejections[reason] += 1
                rejections_by_ops[f"{reason} | {'+'.join(ops)} | {sid}"] += 1
                continue
            seen.add(var.info["fingerprint"])
            variants.append(var)
            counters[sid] = k + 1
            made += 1
        return made

    eligible = [b for b in bundles if _has_labels(b) and b.graph.geo.curves]
    for b in eligible:
        seen.add(fingerprint(b.graph.geo))
    for b in eligible:
        gen_for(b, per_section, per_section)

    # 配额补齐：训练正例（原始 + 变体的目标数）不足 quota 的 label
    quota_log: dict[str, dict] = {}
    if quota > 0:
        for _round in range(4):
            counts = _label_counts(t for b in eligible for t in b.silver) + \
                _label_counts(t for v in variants for t in v.silver)
            short_of = {lab: quota - n for lab, n in counts.items() if n < quota}
            if not short_of:
                break
            progressed = False
            for lab in sorted(short_of):
                hosts = [b for b in eligible
                         if any(not t.is_empty and "synthetic" not in t.flags
                                and t.label_id.rsplit(".", 1)[-1] == lab for t in b.silver)]
                for b in hosts:
                    if counters.get(b.record.section_id, 0) >= 3 * per_section:
                        continue
                    if gen_for(b, max(1, per_section // 2), 3 * per_section) > 0:
                        progressed = True
            if not progressed:
                break
        counts = _label_counts(t for b in eligible for t in b.silver) + \
            _label_counts(t for v in variants for t in v.silver)
        quota_log = {lab: {"count": n, "met": n >= quota} for lab, n in sorted(counts.items())}

    report = {
        "seed": seed, "per_section": per_section, "quota": quota,
        "sections_eligible": len(eligible), "variants": len(variants), "attempts": attempts_total,
        "rejections": dict(rejections), "rejections_detail": dict(rejections_by_ops.most_common(30)),
        "quota_status": quota_log,
    }
    return variants, report


# ---------------------------------------------------------------------------
# 持久化与加载
# ---------------------------------------------------------------------------

def save_variants(variants: list[AugVariant], path: Path = AUG_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for v in variants:
            fh.write(json.dumps(v.to_record(), ensure_ascii=False) + "\n")
    return path


def bundle_from_variant(v: AugVariant, registry: LabelRegistry, src_meta: dict | None = None) -> SectionBundle:
    rec = SectionRecord(
        section_id=v.variant_id, shape_family=v.family, topology=v.topology, geometry=v.geometry,
        regions=[], meta={
            "shape": (src_meta or {}).get("shape") or {"primary": v.family, "topology": v.topology},
            "metadata": {"version": "aug", "annotation_strategy": "propagated"},
            "aug": {"source_id": v.source_id, "ops": v.ops, "name_map": v.work.name_map,
                    "cell_map": v.cell_map, "seed": v.seed,
                    "source_sha256": v.source_sha256,
                    "source_manifest": v.source_manifest,
                    "validation_report": v.validation_report},
        })
    feats = SectionFeatures(v.graph)
    samples = build_query_samples(rec, v.silver, registry)
    return SectionBundle(rec, v.graph, feats, v.silver, samples)


def load_aug_bundles(path: Path = AUG_FILE, registry: LabelRegistry | None = None) -> list[SectionBundle]:
    registry = registry or LabelRegistry.load()
    out: list[SectionBundle] = []
    if not Path(path).exists():
        return out
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            work = _Work.from_dict(d["geometry"])
            work.name_map = {k: list(v) for k, v in d["name_map"].items()}
            geo = work.to_geometry(d["variant_id"])
            graph = build_section_graph(geo)
            silver = [SilverTarget(**t) for t in d["silver"]]
            var = AugVariant(variant_id=d["variant_id"], source_id=d["source_id"],
                             family=d.get("shape_family") or d.get("family") or "unknown",
                             topology=d["topology"], ops=d["ops"], work=work, geometry=geo, graph=graph,
                             silver=silver, cell_map=d.get("cell_map") or {}, info=d.get("info") or {},
                             seed=int(d.get("seed", 1)), source_sha256=d.get("source_sha256", ""),
                             source_manifest=d.get("source_manifest") or [],
                             validation_report=d.get("validation_report") or {})
            out.append(bundle_from_variant(var, registry))
    return out


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def augment_report(bundles: list[SectionBundle], variants: list[AugVariant], report: dict) -> str:
    lines = ["# 数据扩增报告（T1–T5）", ""]
    lines.append(f"- seed={report['seed']}，每截面目标 {report['per_section']} 个变体，label 配额 {report['quota']}")
    lines.append(f"- 有标签截面 {report['sections_eligible']} 个；尝试 {report['attempts']} 次，"
                 f"接受 {report['variants']} 个变体")
    lines.append("- 每行保留 source_id/variant_id/shape_family/ops/seed/name_map/propagated_labels、"
                 "source_manifest + source_sha256，以及六道校验门 validation_report。")
    lines.append("")
    lines.append("## 按操作组合")
    lines.append("")
    lines.append("| ops | 变体数 |")
    lines.append("|---|---:|")
    for sig, n in sorted(Counter(v.ops_signature for v in variants).items(), key=lambda kv: -kv[1]):
        lines.append(f"| {sig} | {n} |")
    lines.append("")
    lines.append("## 按形状族")
    lines.append("")
    lines.append("| family | 源截面 | 变体 |")
    lines.append("|---|---:|---:|")
    fam_src = Counter(b.record.shape_family for b in bundles if _has_labels(b))
    fam_var = Counter(v.family for v in variants)
    for fam in sorted(set(fam_src) | set(fam_var)):
        lines.append(f"| {fam} | {fam_src.get(fam, 0)} | {fam_var.get(fam, 0)} |")
    lines.append("")
    lines.append("## 按 label 的目标数（训练正例）")
    lines.append("")
    lines.append("| label | 原始 | 变体 | 合计 | 配额达成 |")
    lines.append("|---|---:|---:|---:|---|")
    c_src = _label_counts(t for b in bundles for t in b.silver)
    c_var = _label_counts(t for v in variants for t in v.silver)
    for lab in sorted(set(c_src) | set(c_var)):
        total = c_src.get(lab, 0) + c_var.get(lab, 0)
        met = "是" if total >= report["quota"] else "否"
        lines.append(f"| {lab} | {c_src.get(lab, 0)} | {c_var.get(lab, 0)} | {total} | {met} |")
    lines.append("")
    lines.append("## 校验门拒绝统计")
    lines.append("")
    lines.append("| 原因 | 次数 |")
    lines.append("|---|---:|")
    for reason, n in sorted(report["rejections"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {reason} | {n} |")
    detail = report.get("rejections_detail") or {}
    if detail:
        lines.append("")
        lines.append("拒绝明细（原因 | 操作组合 | 源截面，前 30）：")
        lines.append("")
        for key, n in detail.items():
            lines.append(f"- {key}: {n}")
    agree = [v.info["affine_agreement"] for v in variants if v.info.get("affine_agreement") is not None]
    lines.append("")
    if agree:
        lines.append(f"仿射交叉校验（校验门 4）：{len(agree)} 个变体，平均一致率 {np.mean(agree):.4f}，"
                     f"最低 {min(agree):.4f}")
    clear = [v.info["clearance"] for v in variants if v.info.get("clearance") is not None]
    if clear:
        lines.append(f"几何最小间距（校验门 6）：中位数 {float(np.median(clear)):.2f} mm，最小 {min(clear):.2f} mm")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 特征敏感度审计（T1 拆线）
# ---------------------------------------------------------------------------

def feature_sensitivity(bundles: list[SectionBundle], seed: int = 1, frac: float = 0.6,
                        max_k: int = 3, unstable_threshold: float = 0.1) -> tuple[str, dict]:
    """对每个截面施加一次 T1 拆线，统计 34 项曲线特征的平均绝对变化。

    - 未拆分曲线的变化 = 全局不稳定（线段数量等上下文特征在"别的线被拆了"时也变）；
    - 被拆曲线与其子段均值的变化 = 局部变化（子段更短是合理的）。
    """
    n_feat = len(CURVE_FEATURE_NAMES)
    glob_acc = np.zeros(n_feat)
    loc_acc = np.zeros(n_feat)
    n_glob = n_loc = 0
    used = 0
    for b in bundles:
        if not b.graph.geo.curves:
            continue
        rng = random.Random(f"{seed}:audit:{b.record.section_id}")
        work = _Work(b.graph.geo)
        if op_split(work, rng, b.graph, frac=frac, max_k=max_k) is None:
            continue
        geo = work.to_geometry(b.record.section_id + "@audit")
        f2 = SectionFeatures(build_section_graph(geo))
        f1 = b.features
        idx2 = {n: i for i, n in enumerate(f2.curve_names)}
        used += 1
        for i, c in enumerate(f1.curve_names):
            children = [k for k in work.name_map.get(c, []) if k in idx2]
            if not children:
                continue
            x1 = f1.curve_matrix[i]
            x2 = np.mean([f2.curve_matrix[idx2[k]] for k in children], axis=0)
            d = np.abs(x1 - x2)
            if len(children) == 1:
                glob_acc += d
                n_glob += 1
            else:
                loc_acc += d
                n_loc += 1
    glob = glob_acc / max(n_glob, 1)
    loc = loc_acc / max(n_loc, 1)
    order = np.argsort(-glob)
    rows = [(CURVE_FEATURE_NAMES[i], float(glob[i]), float(loc[i])) for i in order]
    unstable = [name for name, g, _ in rows if g > unstable_threshold]
    lines = ["# 曲线特征敏感度审计（T1 加点拆线）", ""]
    lines.append(f"- 截面 {used} 个；未拆分曲线 {n_glob} 条，被拆曲线 {n_loc} 条；"
                 f"拆线比例 {frac}，每条最多 {max_k} 刀，seed={seed}")
    lines.append(f"- 判定：未拆分曲线的平均绝对变化 > {unstable_threshold} 视为**不稳定特征**")
    lines.append("")
    lines.append("| 特征 | Δ 未拆分曲线（全局不稳定） | Δ 被拆曲线 vs 子段均值 | 判定 |")
    lines.append("|---|---:|---:|---|")
    for name, g, loc_d in rows:
        lines.append(f"| {name} | {g:.4f} | {loc_d:.4f} | {'不稳定' if g > unstable_threshold else ''} |")
    lines.append("")
    lines.append("不稳定特征：" + (", ".join(unstable) if unstable else "无"))
    lines.append("")
    return "\n".join(lines), {"unstable": unstable, "rows": rows, "sections": used}

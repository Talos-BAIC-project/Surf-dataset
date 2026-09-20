"""Section 属性图：在 Point/Curve 之上派生拓扑实体与角色。

流程：
1. 平面化（planarize）：合并重合点；在 T 型搭接与交叉处切分曲线，
   使几何相触的曲线获得共享节点（DFC 数据中日字形筋带端点常搭在
   侧壁曲线内部，不共享端点，拓扑上是树，必须切分才能恢复腔体）。
2. 半边结构面遍历：提取平面 cell（闭合腔体，"面"实体）与外轮廓。
3. 派生角色：内部分隔 / 外壁 / 悬挂（法兰）/ 过渡段（倒角）/ 链。

所有派生只依赖 DFC 原生几何，不使用图片，也不使用标注 bbox。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import GEOM_EPS, TRANSITION_MAX_REL_LEN
from .geometry import SectionGeometry

# 平面化容差（mm）
SNAP_TOL = 0.06
# 共线缺口桥接：中面建模中壁体在 T 型交汇处常留半壁厚缺口，
# 端点切向共线且间隙小时补虚拟桥边以恢复腔体拓扑
BRIDGE_MAX_ANGLE_DEG = 8.0
BRIDGE_PREFIX = "__bridge_"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class PlanarEdge:
    edge_id: int
    orig_curve: str                      # 原始曲线名（S_1_SL_x）
    sub_index: int                       # 在原始曲线中的分段序号
    node_a: str                          # 平面化节点名
    node_b: str
    polyline: list[tuple[float, float]]
    length: float


@dataclass
class Cell:
    """平面图中的一个有界面（闭合腔体）。cell_id 按 自上而下/自左向右 稳定编号。"""
    cell_id: str
    curve_names: list[str]               # 边界原始曲线名（唯一化）
    point_names: list[str]               # 边界原始点名（唯一化）
    polygon: list[tuple[float, float]]
    area: float
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]
    edge_ids: list[int] = field(default_factory=list)


@dataclass
class SubCell:
    """深凹槽腰线切出的虚拟子腔（B 字形"双腔"标注策略）。"""
    subcell_id: str                      # 如 cell_1#0 / cell_1#1（自上而下）
    parent_cell: str
    polygon: list[tuple[float, float]]
    area: float
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]
    curve_names: list[str]               # 邻近该子腔的原始曲线
    point_names: list[str]
    waist_ratio: float                   # 腰宽 / 最大宽


@dataclass
class CurveTopo:
    n_cells: int = 0                     # 相邻 cell 数（按原始曲线聚合：任一子段计入）
    cell_ids: list[str] = field(default_factory=list)
    on_outer: bool = False
    dangling: bool = False               # 存在树状子段（悬挂/法兰）
    chain_id: int = -1
    component_id: int = -1
    transition_like: bool = False
    transition_convex: bool = False


@dataclass
class PointTopo:
    degree: int = 0                      # 平面化后所在节点的度数
    on_outer: bool = False
    component_id: int = -1
    is_tip: bool = False


@dataclass
class SectionGraph:
    geo: SectionGeometry
    nodes: dict[str, tuple[float, float]] = field(default_factory=dict)   # 平面化节点
    edges: list[PlanarEdge] = field(default_factory=list)
    point_rep: dict[str, str] = field(default_factory=dict)              # 原始点 -> 节点
    cells: list[Cell] = field(default_factory=list)
    subcells: list[SubCell] = field(default_factory=list)
    curve_topo: dict[str, CurveTopo] = field(default_factory=dict)
    point_topo: dict[str, PointTopo] = field(default_factory=dict)
    chains: list[list[str]] = field(default_factory=list)                # 原始曲线名链
    n_components: int = 0
    outer_curves: set[str] = field(default_factory=set)
    outer_walks: list[list[tuple[int, bool]]] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        return bool(self.cells)

    def cell_by_id(self, cid: str) -> Cell | None:
        return next((c for c in self.cells if c.cell_id == cid), None)


# ---------------------------------------------------------------------------
# 几何小工具
# ---------------------------------------------------------------------------

def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _poly_length(pts: list[tuple[float, float]]) -> float:
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _point_to_segment(p, a, b) -> tuple[float, float]:
    """返回 (距离, 段内参数 t)。"""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < GEOM_EPS:
        return _dist(p, a), 0.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    proj = (ax + t * dx, ay + t * dy)
    return _dist(p, proj), t


def _seg_intersect(a1, a2, b1, b2) -> tuple[float, float] | None:
    """两线段真交点（含端点邻域），平行/共线返回 None。"""
    d1 = (a2[0] - a1[0], a2[1] - a1[1])
    d2 = (b2[0] - b1[0], b2[1] - b1[1])
    denom = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(denom) < GEOM_EPS:
        return None
    dx, dy = b1[0] - a1[0], b1[1] - a1[1]
    t = (dx * d2[1] - dy * d2[0]) / denom
    s = (dx * d1[1] - dy * d1[0]) / denom
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= s <= 1 + 1e-9:
        return (a1[0] + t * d1[0], a1[1] + t * d1[1])
    return None


def _polyline_param(poly: list[tuple[float, float]], p: tuple[float, float]) -> tuple[float, float]:
    """点到折线的 (距离, 弧长参数)。"""
    best_d, best_s = float("inf"), 0.0
    acc = 0.0
    for i in range(len(poly) - 1):
        seg_len = _dist(poly[i], poly[i + 1])
        d, t = _point_to_segment(p, poly[i], poly[i + 1])
        if d < best_d:
            best_d, best_s = d, acc + t * seg_len
        acc += seg_len
    return best_d, best_s


def _polyline_at(poly: list[tuple[float, float]], s: float) -> tuple[float, float]:
    acc = 0.0
    for i in range(len(poly) - 1):
        seg_len = _dist(poly[i], poly[i + 1])
        if acc + seg_len >= s - GEOM_EPS and seg_len > GEOM_EPS:
            t = max(0.0, min(1.0, (s - acc) / seg_len))
            return (
                poly[i][0] + t * (poly[i + 1][0] - poly[i][0]),
                poly[i][1] + t * (poly[i + 1][1] - poly[i][1]),
            )
        acc += seg_len
    return poly[-1]


def _polyline_slice(poly: list[tuple[float, float]], s0: float, s1: float) -> list[tuple[float, float]]:
    out = [_polyline_at(poly, s0)]
    acc = 0.0
    for i in range(len(poly) - 1):
        seg_len = _dist(poly[i], poly[i + 1])
        v = acc + seg_len
        if s0 + GEOM_EPS < v < s1 - GEOM_EPS:
            out.append(poly[i + 1])
        acc = v
    out.append(_polyline_at(poly, s1))
    return out


# ---------------------------------------------------------------------------
# 平面化
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _planarize(geo: SectionGeometry, graph: SectionGraph) -> None:
    """合并重合点、在搭接/交叉处切分曲线，生成平面化 nodes/edges。"""
    curves = list(geo.curves.values())
    # 1) 收集候选节点：原始点 + 交叉点 + 端点在他线内部的投影点
    cand: dict[str, tuple[float, float]] = {p.name: p.uv_local for p in geo.points.values()}
    jid = 0
    # 交叉点（interior x interior）
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            pa, pb = curves[i].polyline_local, curves[j].polyline_local
            for si in range(len(pa) - 1):
                for sj in range(len(pb) - 1):
                    ip = _seg_intersect(pa[si], pa[si + 1], pb[sj], pb[sj + 1])
                    if ip is not None:
                        cand[f"J_{jid}"] = ip
                        jid += 1

    # 2) 邻近聚类（union-find），代表点优先取度数高的原始点
    uf = _UnionFind()
    names = list(cand)
    for n in names:
        uf.find(n)
    # 简单 O(n^2)：截面点数 <= 几十，可接受
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if _dist(cand[names[i]], cand[names[j]]) <= SNAP_TOL:
                uf.union(names[i], names[j])
    clusters: dict[str, list[str]] = {}
    for n in names:
        clusters.setdefault(uf.find(n), []).append(n)

    ref_count: dict[str, int] = {}
    for cv in curves:
        ref_count[cv.start] = ref_count.get(cv.start, 0) + 1
        ref_count[cv.end] = ref_count.get(cv.end, 0) + 1

    rep_of: dict[str, str] = {}
    node_pos: dict[str, tuple[float, float]] = {}
    for members in clusters.values():
        orig = [m for m in members if not m.startswith("J_")]
        rep = max(orig, key=lambda m: (ref_count.get(m, 0), -len(m))) if orig else members[0]
        pts = [cand[m] for m in members]
        pos = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for m in members:
            rep_of[m] = rep
        node_pos[rep] = pos

    graph.point_rep = {p: rep_of[p] for p in geo.points}

    # 3) 逐曲线切分：所有落在曲线上的节点按弧长排序 -> 子段
    edges: list[PlanarEdge] = []
    eid = 0
    used_nodes: set[str] = set()
    for cv in curves:
        poly = cv.polyline_local
        total = max(_poly_length(poly), GEOM_EPS)
        events: dict[str, float] = {}
        for rep, pos in node_pos.items():
            d, s = _polyline_param(poly, pos)
            if d <= SNAP_TOL:
                events[rep] = min(max(s, 0.0), total)
        # 确保两端点在事件中
        events.setdefault(rep_of[cv.start], 0.0)
        events.setdefault(rep_of[cv.end], total)
        order = sorted(events.items(), key=lambda kv: kv[1])
        for k in range(len(order) - 1):
            (na, sa), (nb, sb) = order[k], order[k + 1]
            if sb - sa <= SNAP_TOL or na == nb:
                continue
            sub_poly = _polyline_slice(poly, sa, sb)
            sub_poly[0] = node_pos[na]
            sub_poly[-1] = node_pos[nb]
            edges.append(PlanarEdge(
                edge_id=eid, orig_curve=cv.name, sub_index=k,
                node_a=na, node_b=nb, polyline=sub_poly, length=_poly_length(sub_poly),
            ))
            used_nodes.add(na)
            used_nodes.add(nb)
            eid += 1

    graph.edges = edges
    graph.nodes = {n: node_pos[n] for n in used_nodes}
    _bridge_collinear_gaps(geo, graph)


def _bridge_collinear_gaps(geo: SectionGeometry, graph: SectionGraph) -> None:
    """桥接共线小缺口：曲线到达端点的方向与缺口方向、对侧曲线离开方向共线时补虚拟边。"""
    max_gap = min(0.12 * geo.diag, 15.0)
    cos_tol = math.cos(math.radians(BRIDGE_MAX_ANGLE_DEG))

    # 每个节点上各条边的"到达方向"（指向节点）
    arrivals: list[tuple[str, tuple[float, float]]] = []
    for e in graph.edges:
        d_ab = _edge_dir(e, True, from_end=True)     # 沿 a->b 行进到达 b
        arrivals.append((e.node_b, d_ab))
        d_ba = _edge_dir(e, False, from_end=True)    # 沿 b->a 行进到达 a
        arrivals.append((e.node_a, d_ba))

    candidates: list[tuple[float, str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    # 已有边直接相连的节点对不需要桥接（共线相邻子段之间补桥会产生重边，破坏面遍历）
    connected: set[tuple[str, str]] = {(min(e.node_a, e.node_b), max(e.node_a, e.node_b)) for e in graph.edges}
    for i, (na, da) in enumerate(arrivals):
        for j in range(i + 1, len(arrivals)):
            nb, db = arrivals[j]
            if na == nb or (min(na, nb), max(na, nb)) in connected:
                continue
            pa, pb = graph.nodes[na], graph.nodes[nb]
            gap = _dist(pa, pb)
            if gap <= SNAP_TOL or gap > max_gap:
                continue
            bx, by = (pb[0] - pa[0]) / gap, (pb[1] - pa[1]) / gap
            # 桥沿 da 方向离开 na；到达 nb 时应与 db 相对（db ≈ -bridge 方向）
            if da[0] * bx + da[1] * by < cos_tol:
                continue
            if -(db[0] * bx + db[1] * by) < cos_tol:
                continue
            key = (min(na, nb), max(na, nb))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            candidates.append((gap, na, nb))

    candidates.sort()
    used: set[str] = set()
    bid = 0
    for gap, na, nb in candidates:
        if na in used or nb in used:
            continue
        pa, pb = graph.nodes[na], graph.nodes[nb]
        # 桥不得经过其他节点（否则是沿共线边的"捷径"，会与既有路径重复）
        if any(_point_to_segment(graph.nodes[n], pa, pb)[0] <= SNAP_TOL
               for n in graph.nodes if n not in (na, nb)):
            continue
        # 桥不得穿越既有边（端点邻域除外）
        crossed = False
        for e in graph.edges:
            if na in (e.node_a, e.node_b) or nb in (e.node_a, e.node_b):
                continue
            for si in range(len(e.polyline) - 1):
                ip = _seg_intersect(pa, pb, e.polyline[si], e.polyline[si + 1])
                if ip is not None and _dist(ip, pa) > SNAP_TOL and _dist(ip, pb) > SNAP_TOL:
                    crossed = True
                    break
            if crossed:
                break
        if crossed:
            continue
        graph.edges.append(PlanarEdge(
            edge_id=max((e.edge_id for e in graph.edges), default=-1) + 1,
            orig_curve=f"{BRIDGE_PREFIX}{bid}", sub_index=0,
            node_a=na, node_b=nb, polyline=[pa, pb], length=gap,
        ))
        used.add(na)
        used.add(nb)
        bid += 1

    # 第二阶段：微距端点焊接。度数 1 的端点距其他节点极近（半壁厚级
    # 残缺口）时，直接补边，不要求切向共线。
    weld_tol = max(2.0, 0.015 * geo.diag)
    degree: dict[str, int] = {}
    adjacent: set[tuple[str, str]] = set()
    for e in graph.edges:
        degree[e.node_a] = degree.get(e.node_a, 0) + 1
        degree[e.node_b] = degree.get(e.node_b, 0) + 1
        adjacent.add((min(e.node_a, e.node_b), max(e.node_a, e.node_b)))
    tips = [n for n, d in degree.items() if d == 1]
    for tip in tips:
        if tip in used:
            continue
        pa = graph.nodes[tip]
        best = None
        for other in graph.nodes:
            if other == tip or (min(tip, other), max(tip, other)) in adjacent:
                continue
            d = _dist(pa, graph.nodes[other])
            if SNAP_TOL < d <= weld_tol and (best is None or d < best[0]):
                best = (d, other)
        if best is None:
            continue
        gap, other = best
        pb = graph.nodes[other]
        crossed = False
        for e in graph.edges:
            if tip in (e.node_a, e.node_b) or other in (e.node_a, e.node_b):
                continue
            for si in range(len(e.polyline) - 1):
                ip = _seg_intersect(pa, pb, e.polyline[si], e.polyline[si + 1])
                if ip is not None and _dist(ip, pa) > SNAP_TOL and _dist(ip, pb) > SNAP_TOL:
                    crossed = True
                    break
            if crossed:
                break
        if crossed:
            continue
        graph.edges.append(PlanarEdge(
            edge_id=max((e.edge_id for e in graph.edges), default=-1) + 1,
            orig_curve=f"{BRIDGE_PREFIX}{bid}", sub_index=0,
            node_a=tip, node_b=other, polyline=[pa, pb], length=gap,
        ))
        adjacent.add((min(tip, other), max(tip, other)))
        used.add(tip)
        bid += 1


# ---------------------------------------------------------------------------
# 半边结构面遍历（在平面化图上）
# ---------------------------------------------------------------------------

def _edge_dir(edge: PlanarEdge, forward: bool, from_end: bool = False) -> tuple[float, float]:
    pts = edge.polyline if forward else list(reversed(edge.polyline))
    if from_end:
        p1 = pts[-1]
        for p in reversed(pts[:-1]):
            dx, dy = p1[0] - p[0], p1[1] - p[1]
            n = math.hypot(dx, dy)
            if n > GEOM_EPS:
                return (dx / n, dy / n)
    else:
        p0 = pts[0]
        for p in pts[1:]:
            dx, dy = p[0] - p0[0], p[1] - p0[1]
            n = math.hypot(dx, dy)
            if n > GEOM_EPS:
                return (dx / n, dy / n)
    return (0.0, 0.0)


def _face_walks(graph: SectionGraph) -> list[list[tuple[int, bool]]]:
    outgoing: dict[str, list[tuple[int, bool]]] = {n: [] for n in graph.nodes}
    for e in graph.edges:
        outgoing[e.node_a].append((e.edge_id, True))
        outgoing[e.node_b].append((e.edge_id, False))
    edge_by_id = {e.edge_id: e for e in graph.edges}

    def angle(he: tuple[int, bool]) -> float:
        d = _edge_dir(edge_by_id[he[0]], he[1])
        return math.atan2(d[1], d[0])

    for hes in outgoing.values():
        hes.sort(key=angle)

    def dest(he: tuple[int, bool]) -> str:
        e = edge_by_id[he[0]]
        return e.node_b if he[1] else e.node_a

    visited: set[tuple[int, bool]] = set()
    faces = []
    for e in graph.edges:
        for d in (True, False):
            start = (e.edge_id, d)
            if start in visited:
                continue
            walk = []
            he = start
            for _ in range(4 * len(graph.edges) + 8):
                walk.append(he)
                visited.add(he)
                node = dest(he)
                ring = outgoing[node]
                twin = (he[0], not he[1])
                idx = ring.index(twin)
                he = ring[idx - 1]
                if he == start:
                    break
            faces.append(walk)
    return faces


def _walk_polygon(graph: SectionGraph, walk: list[tuple[int, bool]]) -> list[tuple[float, float]]:
    edge_by_id = {e.edge_id: e for e in graph.edges}
    poly: list[tuple[float, float]] = []
    for eid, forward in walk:
        pts = edge_by_id[eid].polyline
        pts = pts if forward else list(reversed(pts))
        poly.extend(pts[:-1])
    return poly


def _signed_area(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _polygon_centroid(poly: list[tuple[float, float]], area: float) -> tuple[float, float]:
    if abs(area) < GEOM_EPS:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return (cx / (6 * area), cy / (6 * area))


# ---------------------------------------------------------------------------
# 深凹槽腰线 -> 虚拟子腔（B 字形双腔标注策略）
# ---------------------------------------------------------------------------

def _width_profile(poly: list[tuple[float, float]], n_samples: int = 96) -> list[tuple[float, float]]:
    """cell 多边形沿竖直方向的水平截面宽度轮廓 [(v, width)]。"""
    ys = [p[1] for p in poly]
    y0, y1 = min(ys), max(ys)
    if y1 - y0 < GEOM_EPS:
        return []
    out = []
    n = len(poly)
    for k in range(1, n_samples):
        v = y0 + (y1 - y0) * k / n_samples
        xs = []
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            if (a[1] - v) * (b[1] - v) <= 0 and abs(b[1] - a[1]) > GEOM_EPS:
                t = (v - a[1]) / (b[1] - a[1])
                xs.append(a[0] + t * (b[0] - a[0]))
        xs.sort()
        width = sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2))
        out.append((v, width))
    return out


def _clip_polygon_band(poly, v_lo, v_hi):
    """Sutherland-Hodgman：多边形与水平带 [v_lo, v_hi] 求交。"""
    def clip(pts, keep_fn, cross_v):
        out = []
        n = len(pts)
        for i in range(n):
            cur, nxt = pts[i], pts[(i + 1) % n]
            cur_in, nxt_in = keep_fn(cur), keep_fn(nxt)
            if cur_in:
                out.append(cur)
            if cur_in != nxt_in and abs(nxt[1] - cur[1]) > GEOM_EPS:
                t = (cross_v - cur[1]) / (nxt[1] - cur[1])
                out.append((cur[0] + t * (nxt[0] - cur[0]), cross_v))
        return out

    result = clip(poly, lambda p: p[1] >= v_lo - GEOM_EPS, v_lo)
    if not result:
        return []
    return clip(result, lambda p: p[1] <= v_hi + GEOM_EPS, v_hi)


def _detect_subcells(graph: SectionGraph) -> None:
    """cell 宽度轮廓存在明显"腰"时，按腰线切分为子腔。"""
    edge_by_id = {e.edge_id: e for e in graph.edges}
    for cell in graph.cells:
        profile = _width_profile(cell.polygon)
        if len(profile) < 8:
            continue
        widths = [w for _, w in profile]
        w_max = max(widths)
        if w_max < GEOM_EPS:
            continue
        # 内部局部极小且 < 60% 最大宽度的腰
        waists: list[tuple[float, float]] = []
        margin = max(2, len(profile) // 12)
        for k in range(margin, len(profile) - margin):
            v, w = profile[k]
            if w > 0.6 * w_max:
                continue
            lo = max(0, k - margin)
            hi = min(len(profile), k + margin + 1)
            if w <= min(widths[lo:hi]) + GEOM_EPS:
                if not waists or v - waists[-1][0] > 0.08 * (profile[-1][0] - profile[0][0]):
                    waists.append((v, w))
        if not waists:
            continue
        cuts = [cell.bbox[1]] + [v for v, _ in waists] + [cell.bbox[3]]
        pieces = []
        for k in range(len(cuts) - 1):
            piece = _clip_polygon_band(cell.polygon, cuts[k], cuts[k + 1])
            if len(piece) >= 3 and abs(_signed_area(piece)) > 0.05 * cell.area:
                pieces.append(piece)
        if len(pieces) < 2:
            continue
        # 自上而下编号
        infos = []
        for piece in pieces:
            area = abs(_signed_area(piece))
            centroid = _polygon_centroid(piece, _signed_area(piece))
            xs = [p[0] for p in piece]
            ys = [p[1] for p in piece]
            infos.append((piece, area, centroid, (min(xs), min(ys), max(xs), max(ys))))
        infos.sort(key=lambda e: -e[2][1])
        w_waist = min(w for _, w in waists)
        for k, (piece, area, centroid, bbox) in enumerate(infos):
            curve_names, point_names = set(), set()
            for eid in cell.edge_ids:
                e = edge_by_id[eid]
                if e.orig_curve.startswith(BRIDGE_PREFIX):
                    continue
                mid = _polyline_at(e.polyline, e.length / 2)
                if bbox[1] - SNAP_TOL <= mid[1] <= bbox[3] + SNAP_TOL:
                    curve_names.add(e.orig_curve)
                    for node in (e.node_a, e.node_b):
                        if bbox[1] - SNAP_TOL <= graph.nodes[node][1] <= bbox[3] + SNAP_TOL:
                            point_names.add(node)
            graph.subcells.append(SubCell(
                subcell_id=f"{cell.cell_id}#{k}",
                parent_cell=cell.cell_id,
                polygon=piece, area=area, centroid=centroid, bbox=bbox,
                curve_names=sorted(curve_names),
                point_names=sorted(p for p in point_names if not p.startswith("J_")),
                waist_ratio=w_waist / w_max,
            ))


# ---------------------------------------------------------------------------
# 链 / 过渡段
# ---------------------------------------------------------------------------

def _build_chains(graph: SectionGraph) -> list[list[str]]:
    """极大链（按平面化边，映射回原始曲线名并去重相邻重复）。"""
    adj: dict[str, list[int]] = {n: [] for n in graph.nodes}
    edge_by_id = {e.edge_id: e for e in graph.edges}
    for e in graph.edges:
        adj[e.node_a].append(e.edge_id)
        adj[e.node_b].append(e.edge_id)
    degree = {n: len(v) for n, v in adj.items()}
    assigned: set[int] = set()
    chains: list[list[str]] = []

    def extend(eid: int, enter_node: str, acc: list[int]) -> None:
        cur_e, cur_node = eid, enter_node
        while True:
            e = edge_by_id[cur_e]
            nxt_node = e.node_b if e.node_a == cur_node else e.node_a
            if degree.get(nxt_node, 0) != 2:
                break
            nxt = [x for x in adj[nxt_node] if x != cur_e]
            if len(nxt) != 1 or nxt[0] in assigned or nxt[0] in acc:
                break
            acc.append(nxt[0])
            cur_e, cur_node = nxt[0], nxt_node

    for e in graph.edges:
        if e.edge_id in assigned:
            continue
        assigned.add(e.edge_id)
        fwd: list[int] = []
        extend(e.edge_id, e.node_a, fwd)
        for x in fwd:
            assigned.add(x)
        bwd: list[int] = []
        extend(e.edge_id, e.node_b, bwd)
        for x in bwd:
            assigned.add(x)
        seq = list(reversed(bwd)) + [e.edge_id] + fwd
        names: list[str] = []
        for eid in seq:
            oc = edge_by_id[eid].orig_curve
            if oc.startswith(BRIDGE_PREFIX):
                continue
            if not names or names[-1] != oc:
                names.append(oc)
        if names:
            chains.append(names)
    return chains


def _direction_of_curve(geo: SectionGeometry, cname: str) -> tuple[float, float]:
    poly = geo.curves[cname].polyline_local
    dx = poly[-1][0] - poly[0][0]
    dy = poly[-1][1] - poly[0][1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > GEOM_EPS else (0.0, 0.0)


def _angle_between(d1, d2) -> float:
    dot = abs(d1[0] * d2[0] + d1[1] * d2[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _mark_transitions(geo: SectionGeometry, graph: SectionGraph) -> None:
    """短且在两端都发生方向偏折的原始曲线 -> 过渡段（倒角/圆角候选）。

    逐端点判定：曲线的每个端点处，只要存在一条与其夹角 > 15° 的邻边即可。
    （倒角可能与内部筋近乎平行——如目字形凹槽口的斜切段——不能要求
    与所有邻边都偏折。）
    """
    max_len = TRANSITION_MAX_REL_LEN * geo.diag
    node_curves: dict[str, set[str]] = {}
    for e in graph.edges:
        for node in (e.node_a, e.node_b):
            node_curves.setdefault(node, set()).add(e.orig_curve)

    for cname, cv in geo.curves.items():
        if cv.length > max_len or cv.length < GEOM_EPS:
            continue
        # 曲线两端的平面化节点（原始端点吸附后的代表）
        end_nodes = []
        for pname in (cv.start, cv.end):
            rep = graph.point_rep.get(pname)
            if rep is not None and rep in node_curves:
                end_nodes.append(rep)
        if len(end_nodes) < 2:
            continue
        d_self = _direction_of_curve(geo, cname)
        ok = True
        for node in end_nodes:
            others = [x for x in node_curves[node] if x != cname and x in geo.curves]
            if not others:
                ok = False
                break
            best = max(_angle_between(d_self, _direction_of_curve(geo, n)) for n in others)
            if best <= 15.0:
                ok = False
                break
        if ok:
            graph.curve_topo[cname].transition_like = True


def _mark_transition_convexity(graph: SectionGraph) -> None:
    """外倒角判定：沿外轮廓（顺时针）把连续过渡段分组为"过渡链"，
    以链前后的行进方向计算整体转角。右转（cross<0）且转角明显时为凸角
    （外倒角）；转角接近 0 的是平行壁间的错位过渡（凹槽口），属于内倒角。
    """
    edge_by_id = {e.edge_id: e for e in graph.edges}

    def is_trans(eid: int) -> bool:
        t = graph.curve_topo.get(edge_by_id[eid].orig_curve)
        return t is not None and t.transition_like

    for walk in graph.outer_walks:
        n = len(walk)
        counts: dict[int, int] = {}
        for eid, _f in walk:
            counts[eid] = counts.get(eid, 0) + 1
        # 旋转起点到非过渡边，避免过渡链跨数组边界被截断
        start_at = next((k for k in range(n) if not is_trans(walk[k][0])), None)
        if start_at is None:
            continue
        walk = walk[start_at:] + walk[:start_at]
        i = 0
        while i < n:
            eid, fwd = walk[i]
            if not is_trans(eid) or counts[eid] == 2:
                i += 1
                continue
            # 收集连续过渡段链
            j = i
            chain_idx = []
            while j < n and is_trans(walk[j][0]) and counts[walk[j][0]] != 2:
                chain_idx.append(j)
                j += 1
            prev_eid, prev_f = walk[(chain_idx[0] - 1) % n]
            next_eid, next_f = walk[(chain_idx[-1] + 1) % n]
            d_in = _edge_dir(edge_by_id[prev_eid], prev_f, from_end=True)
            d_out = _edge_dir(edge_by_id[next_eid], next_f)
            cross = d_in[0] * d_out[1] - d_in[1] * d_out[0]
            dot = d_in[0] * d_out[0] + d_in[1] * d_out[1]
            turn_deg = math.degrees(math.atan2(cross, dot))
            if turn_deg < -25.0:  # 顺时针外轮廓上右转 => 凸角
                for k in chain_idx:
                    t = graph.curve_topo.get(edge_by_id[walk[k][0]].orig_curve)
                    if t is not None:
                        t.transition_convex = True
            i = j


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def build_section_graph(geo: SectionGeometry) -> SectionGraph:
    graph = SectionGraph(geo=geo)
    graph.curve_topo = {c: CurveTopo() for c in geo.curves}
    graph.point_topo = {p: PointTopo() for p in geo.points}
    if not geo.curves:
        return graph

    _planarize(geo, graph)
    edge_by_id = {e.edge_id: e for e in graph.edges}

    # 连通分量（平面化节点上）
    adj: dict[str, list[int]] = {n: [] for n in graph.nodes}
    for e in graph.edges:
        adj[e.node_a].append(e.edge_id)
        adj[e.node_b].append(e.edge_id)
    comp: dict[str, int] = {}
    cid = 0
    for seed in graph.nodes:
        if seed in comp:
            continue
        stack = [seed]
        comp[seed] = cid
        while stack:
            cur = stack.pop()
            for eid in adj[cur]:
                e = edge_by_id[eid]
                nxt = e.node_b if e.node_a == cur else e.node_a
                if nxt not in comp:
                    comp[nxt] = cid
                    stack.append(nxt)
        cid += 1
    graph.n_components = cid

    for pname, rep in graph.point_rep.items():
        pt = graph.point_topo[pname]
        if rep in graph.nodes:
            pt.degree = len(adj[rep])
            pt.component_id = comp.get(rep, -1)
            pt.is_tip = pt.degree == 1
    for e in graph.edges:
        t = graph.curve_topo.get(e.orig_curve)
        if t is not None:
            t.component_id = comp.get(e.node_a, -1)

    # 面遍历
    faces = _face_walks(graph)
    face_infos = []
    for walk in faces:
        poly = _walk_polygon(graph, walk)
        area = _signed_area(poly)
        face_infos.append((walk, poly, area))

    min_cell_area = max(1.0, (0.002 * geo.diag) ** 2)
    enriched = []
    for walk, poly, area in face_infos:
        if area <= min_cell_area:
            continue
        centroid = _polygon_centroid(poly, area)
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        enriched.append((walk, poly, area, centroid, (min(xs), min(ys), max(xs), max(ys))))
    enriched.sort(key=lambda e: (-e[3][1], e[3][0]))
    for i, (walk, poly, area, centroid, bbox) in enumerate(enriched):
        counts: dict[int, int] = {}
        for eid, _f in walk:
            counts[eid] = counts.get(eid, 0) + 1
        boundary_eids = [eid for eid, n in counts.items() if n == 1]
        curve_names, point_names = [], []
        seen_c: set[str] = set()
        seen_p: set[str] = set()
        for eid in boundary_eids:
            e = edge_by_id[eid]
            if e.orig_curve not in seen_c and not e.orig_curve.startswith(BRIDGE_PREFIX):
                seen_c.add(e.orig_curve)
                curve_names.append(e.orig_curve)
            for node in (e.node_a, e.node_b):
                if node not in seen_p and not node.startswith("J_"):
                    seen_p.add(node)
                    point_names.append(node)
        cell = Cell(
            cell_id=f"cell_{i + 1}", curve_names=curve_names, point_names=point_names,
            polygon=poly, area=area, centroid=centroid, bbox=bbox, edge_ids=boundary_eids,
        )
        graph.cells.append(cell)
        for cname in curve_names:
            graph.curve_topo[cname].n_cells += 1
            graph.curve_topo[cname].cell_ids.append(cell.cell_id)

    # 外边界：每个连通分量面积最负的面
    by_comp: dict[int, tuple[float, list[tuple[int, bool]]]] = {}
    for walk, poly, area in face_infos:
        c = comp.get(edge_by_id[walk[0][0]].node_a, -1)
        if c not in by_comp or area < by_comp[c][0]:
            by_comp[c] = (area, walk)
    for _, (area, walk) in by_comp.items():
        graph.outer_walks.append(walk)
        counts = {}
        for eid, _f in walk:
            counts[eid] = counts.get(eid, 0) + 1
        rep_to_points: dict[str, list[str]] = {}
        for pname, rep in graph.point_rep.items():
            rep_to_points.setdefault(rep, []).append(pname)
        for eid, n in counts.items():
            e = edge_by_id[eid]
            topo = graph.curve_topo.get(e.orig_curve)
            if topo is not None:
                topo.on_outer = True
                graph.outer_curves.add(e.orig_curve)
                if n == 2:
                    topo.dangling = True
            for node in (e.node_a, e.node_b):
                for pname in rep_to_points.get(node, ()):
                    graph.point_topo[pname].on_outer = True

    graph.chains = _build_chains(graph)
    for i, chain in enumerate(graph.chains):
        for cname in chain:
            if graph.curve_topo[cname].chain_id < 0:
                graph.curve_topo[cname].chain_id = i

    _mark_transitions(geo, graph)
    _mark_transition_convexity(graph)
    _detect_subcells(graph)
    return graph

"""实体特征提取：曲线 / 面(cell) 候选的几何+拓扑特征向量。

约束：推理阶段可用的信息只有 DFC 原生几何与派生拓扑，
绝不读取标注 bbox（bbox 仅存在于 silver 引导阶段）。

稳定性约定（PLAN §2.6，特征敏感度审计的结论）：长度、延展、排位、计数、端点度数
这些量按曲线所属的**直线段 run**（经度数为 2 的节点相连、方向变化 < 5° 的连续曲线）
计算，而不是按单条曲线——一条壁被"加点"拆成几段后，每段仍应得到整条壁的特征，
否则模型会把"线段数量/单段长度"当成语义。位置类特征（中心、到边界/凸包的距离）保留
曲线级，以便区分同一直线上位置不同的部件（如与壁共线的法兰段）。
"""

from __future__ import annotations

import math

import numpy as np

from .graph import BRIDGE_PREFIX, Cell, SectionGraph, SubCell

# run 内相邻曲线允许的最大方向变化（度）
RUN_MAX_ANGLE_DEG = 5.0

CURVE_FEATURE_NAMES = [
    # 几何（run 级长度/延展；曲线级位置与方向）
    "run_len_norm", "u_center", "v_center", "run_du_norm", "run_dv_norm",
    "orient_cos", "orient_sin", "is_horizontal", "is_vertical",
    "straightness", "border_dist_min", "hull_dist_norm",
    # 与截面长/短轴的关系（主壁沿长轴、筋沿短轴等语义的关键交互特征）
    "aligned_long_axis", "run_span_long_axis", "run_span_short_axis", "run_len_over_longdim",
    # 排序位次（在 run 之间排位）
    "run_v_rank", "run_u_rank", "run_len_rank",
    # 拓扑
    "n_cells_norm", "separates_cells", "on_outer", "dangling",
    "transition_like", "transition_convex", "run_has_tip_endpoint",
    "run_min_degree_norm", "run_max_degree_norm", "chain_len_norm",
    "in_pocket",
    # 截面上下文
    "section_aspect", "n_runs_norm", "section_closed",
]

FACE_FEATURE_NAMES = [
    "area_norm", "u_center", "v_center", "aspect", "v_rank", "u_rank",
    "area_rank", "n_boundary_runs_norm", "is_subcell", "waist_ratio",
    "rel_area_to_max", "boundary_outer_frac", "section_aspect",
]


# ---------------------------------------------------------------------------
# 直线段 run
# ---------------------------------------------------------------------------

def _tangent_at(poly: list[tuple[float, float]], node: tuple[float, float]) -> tuple[float, float]:
    """折线在靠近 node 的那一端的切向（单位向量，方向无关）。"""
    if len(poly) < 2:
        return (0.0, 0.0)
    d_start = math.hypot(poly[0][0] - node[0], poly[0][1] - node[1])
    d_end = math.hypot(poly[-1][0] - node[0], poly[-1][1] - node[1])
    a, b = (poly[0], poly[1]) if d_start <= d_end else (poly[-1], poly[-2])
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-12 else (0.0, 0.0)


def build_runs(graph: SectionGraph) -> dict[str, int]:
    """曲线 -> run 编号。两条曲线在某个只被这两条曲线触及的节点相接且方向变化 < 5° 时属于同一 run。"""
    geo = graph.geo
    node_curves: dict[str, set[str]] = {}
    for e in graph.edges:
        if e.orig_curve.startswith(BRIDGE_PREFIX):
            continue
        for n in (e.node_a, e.node_b):
            node_curves.setdefault(n, set()).add(e.orig_curve)
    parent = {c: c for c in geo.curves}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for node, curves in node_curves.items():
        if len(curves) != 2:
            continue
        a, b = sorted(curves)
        if a not in geo.curves or b not in geo.curves:
            continue
        pos = graph.nodes[node]
        da = _tangent_at(geo.curves[a].polyline_local, pos)
        db = _tangent_at(geo.curves[b].polyline_local, pos)
        dot = abs(da[0] * db[0] + da[1] * db[1])
        if math.degrees(math.acos(max(-1.0, min(1.0, dot)))) <= RUN_MAX_ANGLE_DEG:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    roots: dict[str, int] = {}
    out: dict[str, int] = {}
    for c in sorted(geo.curves, key=lambda c: geo.curves[c].runtime_id):
        r = find(c)
        out[c] = roots.setdefault(r, len(roots))
    return out


# ---------------------------------------------------------------------------
# 凸包（Andrew 单调链）与点到多边形距离
# ---------------------------------------------------------------------------

def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _dist_point_to_poly_boundary(p: tuple[float, float], poly: list[tuple[float, float]]) -> float:
    if not poly:
        return 0.0
    if len(poly) == 1:
        return math.hypot(p[0] - poly[0][0], p[1] - poly[0][1])
    best = float("inf")
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
        best = min(best, math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy)))
    return best


# ---------------------------------------------------------------------------
# 特征提取器
# ---------------------------------------------------------------------------

class SectionFeatures:
    """一次性计算截面内全部候选实体的特征。"""

    def __init__(self, graph: SectionGraph):
        self.graph = graph
        geo = graph.geo
        self.W = max(geo.width, 1e-6)
        self.H = max(geo.height, 1e-6)
        self.diag = geo.diag
        self.hull = convex_hull([p.uv_local for p in geo.points.values()])

        self.curve_names: list[str] = sorted(geo.curves, key=lambda c: geo.curves[c].runtime_id)
        self.run_of: dict[str, int] = build_runs(graph)
        self.runs: dict[int, list[str]] = {}
        for c in self.curve_names:
            self.runs.setdefault(self.run_of[c], []).append(c)
        self.curve_matrix = self._curve_features()

        self.face_ids: list[str] = [c.cell_id for c in graph.cells] + \
                                   [s.subcell_id for s in graph.subcells]
        self.face_matrix = self._face_features()

    # -- 曲线 -----------------------------------------------------------
    def _run_stats(self) -> dict[int, dict]:
        """每个 run 的长度、延展、质心、端点度数。"""
        graph, geo = self.graph, self.graph.geo
        node_degree: dict[str, int] = {}
        node_curves: dict[str, set[str]] = {}
        for e in graph.edges:
            for n in (e.node_a, e.node_b):
                node_degree[n] = node_degree.get(n, 0) + 1
                if not e.orig_curve.startswith(BRIDGE_PREFIX):
                    node_curves.setdefault(n, set()).add(e.orig_curve)
        stats: dict[int, dict] = {}
        for rid, members in self.runs.items():
            pts = [p for c in members for p in geo.curves[c].polyline_local]
            total = sum(geo.curves[c].length for c in members)
            cx = cy = 0.0
            for c in members:
                cv = geo.curves[c]
                mid = cv.polyline_local[len(cv.polyline_local) // 2]
                cx += mid[0] * cv.length
                cy += mid[1] * cv.length
            w = max(total, 1e-9)
            member_set = set(members)
            # run 的端节点：触及的节点中，不是仅由 run 内两条曲线相接的"内部接点"
            end_degs = []
            for n, curves in node_curves.items():
                touched = curves & member_set
                if not touched:
                    continue
                internal = curves <= member_set and len(curves) == 2
                if not internal:
                    end_degs.append(node_degree.get(n, 0))
            if not end_degs:
                end_degs = [0]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            stats[rid] = {
                "len": total, "du": max(xs) - min(xs), "dv": max(ys) - min(ys),
                "centroid": (cx / w, cy / w), "min_deg": min(end_degs), "max_deg": max(end_degs),
            }
        return stats

    def _curve_features(self) -> np.ndarray:
        graph, geo = self.graph, self.graph.geo
        n = len(self.curve_names)
        if n == 0:
            return np.zeros((0, len(CURVE_FEATURE_NAMES)))

        chain_lens: dict[str, float] = {}
        for chain in graph.chains:
            total = sum(geo.curves[c].length for c in chain if c in geo.curves)
            for c in chain:
                chain_lens[c] = total

        runs = self._run_stats()

        def rank(values: dict) -> dict:
            order = sorted(values, key=lambda k: values[k])
            if len(order) <= 1:
                return {k: 0.5 for k in order}
            return {k: i / (len(order) - 1) for i, k in enumerate(order)}

        run_v_ranks = rank({r: s["centroid"][1] for r, s in runs.items()})
        run_u_ranks = rank({r: s["centroid"][0] for r, s in runs.items()})
        run_len_ranks = rank({r: s["len"] for r, s in runs.items()})

        aspect = min(self.H / self.W, 8.0) / 8.0
        closed = 1.0 if graph.is_closed else 0.0
        v_is_long = self.H >= self.W
        long_dim = max(self.W, self.H)
        rows = []
        for cname in self.curve_names:
            cv = geo.curves[cname]
            topo = graph.curve_topo[cname]
            rs = runs[self.run_of[cname]]
            pts = cv.polyline_local
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            dx = pts[-1][0] - pts[0][0]
            dy = pts[-1][1] - pts[0][1]
            chord = max(math.hypot(dx, dy), 1e-9)
            ocos, osin = abs(dx) / chord, abs(dy) / chord
            angle = math.degrees(math.atan2(abs(dy), abs(dx)))
            is_h = 1.0 if angle < 20 else 0.0
            is_v = 1.0 if angle > 70 else 0.0
            run_du = rs["du"] / self.W
            run_dv = rs["dv"] / self.H
            border_dist = min(cx, self.W - cx, cy, self.H - cy) / max(self.W, self.H)
            hull_dist = _dist_point_to_poly_boundary(pts[len(pts) // 2], self.hull) / self.diag
            run_hull_dist = _dist_point_to_poly_boundary(rs["centroid"], self.hull) / self.diag
            rows.append([
                rs["len"] / self.diag,
                cx / self.W, cy / self.H,
                run_du, run_dv,
                ocos, osin, is_h, is_v,
                cv.chord / max(cv.length, 1e-9),
                border_dist, hull_dist,
                is_v if v_is_long else is_h,
                run_dv if v_is_long else run_du,
                run_du if v_is_long else run_dv,
                rs["len"] / long_dim,
                run_v_ranks[self.run_of[cname]], run_u_ranks[self.run_of[cname]],
                run_len_ranks[self.run_of[cname]],
                topo.n_cells / 2.0, 1.0 if topo.n_cells >= 2 else 0.0,
                1.0 if topo.on_outer else 0.0, 1.0 if topo.dangling else 0.0,
                1.0 if topo.transition_like else 0.0, 1.0 if topo.transition_convex else 0.0,
                1.0 if rs["min_deg"] <= 1 else 0.0,
                rs["min_deg"] / 4.0, rs["max_deg"] / 4.0,
                chain_lens.get(cname, cv.length) / self.diag,
                1.0 if (topo.on_outer and run_hull_dist > 0.02) else 0.0,
                aspect, len(self.runs) / 30.0, closed,
            ])
        return np.asarray(rows, dtype=np.float64)

    # -- 面 --------------------------------------------------------------
    def _face_features(self) -> np.ndarray:
        graph = self.graph
        faces: list[Cell | SubCell] = list(graph.cells) + list(graph.subcells)
        n = len(faces)
        if n == 0:
            return np.zeros((0, len(FACE_FEATURE_NAMES)))
        areas = [f.area for f in faces]
        max_area = max(areas)
        aspect = min(self.H / self.W, 8.0) / 8.0

        def rank(vals: list[float]) -> list[float]:
            order = np.argsort(vals)
            out = [0.5] * len(vals)
            if len(vals) > 1:
                for i, idx in enumerate(order):
                    out[idx] = i / (len(vals) - 1)
            return out

        v_ranks = rank([f.centroid[1] for f in faces])
        u_ranks = rank([f.centroid[0] for f in faces])
        a_ranks = rank(areas)

        rows = []
        for i, f in enumerate(faces):
            bbox = f.bbox
            fw = max(bbox[2] - bbox[0], 1e-9)
            fh = max(bbox[3] - bbox[1], 1e-9)
            is_sub = isinstance(f, SubCell)
            waist = f.waist_ratio if is_sub else 1.0
            outer_frac = 0.0
            if f.curve_names:
                outer_frac = sum(
                    1 for c in f.curve_names
                    if c in graph.curve_topo and graph.curve_topo[c].on_outer
                ) / len(f.curve_names)
            n_boundary_runs = len({self.run_of[c] for c in f.curve_names if c in self.run_of})
            rows.append([
                f.area / (self.W * self.H),
                f.centroid[0] / self.W, f.centroid[1] / self.H,
                min(fw / fh, 8.0) / 8.0,
                v_ranks[i], u_ranks[i], a_ranks[i],
                n_boundary_runs / 12.0,
                1.0 if is_sub else 0.0, waist,
                f.area / max_area, outer_frac,
                aspect,
            ])
        return np.asarray(rows, dtype=np.float64)

    # -- 查询接口 ---------------------------------------------------------
    def curve_index(self, name: str) -> int:
        return self.curve_names.index(name)

    def face_by_id(self, fid: str) -> Cell | SubCell | None:
        for c in self.graph.cells:
            if c.cell_id == fid:
                return c
        for s in self.graph.subcells:
            if s.subcell_id == fid:
                return s
        return None

"""DFC 截面几何解析：DFC 宏脚本(.py) 与 Wranger XML(.xml) -> 统一 Section IR。

坐标约定（与 dfc-dataset 标注规则一致）：
- 自动检测截面所在平面（点坐标近似恒定的轴为法向）；
- 2D 坐标 (u, v)：u = 水平轴（x 或 y），v = 竖直轴（通常为 z）；
- 局部坐标 = (u - u_min, v - v_min)，即截面 bbox 左下角为原点。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .config import GEOM_EPS

BEZIER_SAMPLES = 8


@dataclass
class Point:
    name: str                 # 稳定名称，如 S_1_SP_3
    runtime_id: int           # 本次加载的运行时序号
    xyz: tuple[float, float, float]
    uv: tuple[float, float] = (0.0, 0.0)          # 平面投影坐标
    uv_local: tuple[float, float] = (0.0, 0.0)    # 截面局部坐标（bbox 左下角为原点）


@dataclass
class Curve:
    name: str                 # 稳定名称，如 S_1_SL_7
    runtime_id: int
    start: str                # 起点 Point.name
    end: str                  # 终点 Point.name
    # 三次贝塞尔控制点（世界坐标），直线时为 None
    control_xyz: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    polyline_local: list[tuple[float, float]] = field(default_factory=list)
    length: float = 0.0
    chord: float = 0.0

    @property
    def is_straight(self) -> bool:
        return self.chord > GEOM_EPS and self.length / self.chord < 1.0 + 1e-3


@dataclass
class SectionGeometry:
    section_id: str           # 数据集实例 id，如 mu-shape-1
    section_name: str         # DFC 内部名，如 S_1
    source: str               # "py" | "xml"
    plane: str                # "YZ" | "XZ" | "XY"
    points: dict[str, Point] = field(default_factory=dict)
    curves: dict[str, Curve] = field(default_factory=dict)
    u_min: float = 0.0
    v_min: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def diag(self) -> float:
        return max((self.width**2 + self.height**2) ** 0.5, GEOM_EPS)


# ---------------------------------------------------------------------------
# DFC 宏脚本解析
# ---------------------------------------------------------------------------

_RE_SECT = re.compile(r"(\w+)\s*=\s*theModel\.createSect\(\s*sectionName\s*=\s*\"([^\"]+)\"")
_RE_NODE = re.compile(
    r"(\w+)\s*=\s*theModel\.createSecNode\(\s*x\s*=\s*([-\d.eE+]+)\s*,\s*y\s*=\s*([-\d.eE+]+)\s*,"
    r"\s*z\s*=\s*([-\d.eE+]+)\s*,\s*theSect\s*=\s*(\w+)\s*\)"
)
_RE_CURVE = re.compile(
    r"(\w+)\s*=\s*theModel\.createSecCurve\(\s*start\s*=\s*(\w+)\s*,\s*end\s*=\s*(\w+)\s*,"
    r"\s*theSect\s*=\s*(\w+)\s*\)"
)


def parse_dfc_script(path: Path) -> dict[str, dict]:
    """解析 DFC 宏脚本，返回 {section_var: {name, points, curves}}。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    sections: dict[str, dict] = {}
    for var, name in _RE_SECT.findall(text):
        sections[var] = {"name": name, "points": {}, "curves": []}
    for var, x, y, z, sect_var in _RE_NODE.findall(text):
        if sect_var in sections:
            sections[sect_var]["points"][var] = (float(x), float(y), float(z))
    for var, start, end, sect_var in _RE_CURVE.findall(text):
        if sect_var in sections:
            sections[sect_var]["curves"].append((var, start, end))
    return sections


# ---------------------------------------------------------------------------
# Wranger XML 解析
# ---------------------------------------------------------------------------

def _xml_xyz(elem: ET.Element | None) -> tuple[float, float, float] | None:
    if elem is None:
        return None
    items = elem.findall("item")
    if len(items) == 3:
        return tuple(float(i.text) for i in items)  # type: ignore[return-value]
    vals = [elem.findtext(tag) for tag in ("X", "Y", "Z")]
    if all(v is not None for v in vals):
        return tuple(float(v) for v in vals)  # type: ignore[return-value]
    return None


def parse_dfc_xml(path: Path) -> dict[str, dict]:
    """解析 Wranger XML，返回与 parse_dfc_script 相同结构（按 sectionName 分组）。"""
    root = ET.parse(path).getroot()
    sections: dict[str, dict] = {}

    for sec in root.iter("Section"):
        name = sec.findtext("Name") or "S_?"
        sections.setdefault(name, {"name": name, "points": {}, "curves": []})

    for pt in root.iter("Point"):
        name = pt.findtext("Name") or ""
        sect = pt.findtext("sectionName") or ""
        # Type==2 为截面轮廓点；Type==3 是截面原点标记，跳过
        if pt.findtext("Type") != "2" or not name or name == sect:
            continue
        xyz = _xml_xyz(pt.find("gCoord"))
        if xyz is None:
            continue
        sections.setdefault(sect, {"name": sect, "points": {}, "curves": []})
        sections[sect]["points"][name] = xyz

    for cv in root.iter("Curve"):
        name = cv.findtext("Name") or ""
        sect = cv.findtext("sectionName") or ""
        start = cv.findtext("startPointName") or ""
        end = cv.findtext("endPointName") or ""
        if not (name and start and end):
            continue
        cp1 = _xml_xyz(cv.find("controlPoint_1_gCoord"))
        cp2 = _xml_xyz(cv.find("controlPoint_2_gCoord"))
        sections.setdefault(sect, {"name": sect, "points": {}, "curves": []})
        sections[sect]["curves"].append((name, start, end, cp1, cp2))
    return sections


# ---------------------------------------------------------------------------
# 平面检测与 Section IR 构建
# ---------------------------------------------------------------------------

def _detect_plane(coords: list[tuple[float, float, float]]) -> tuple[str, int, int]:
    """返回 (plane_name, u_axis_index, v_axis_index)。取值范围最小的轴为法向。"""
    ranges = []
    for axis in range(3):
        vals = [c[axis] for c in coords]
        ranges.append(max(vals) - min(vals) if vals else 0.0)
    normal = min(range(3), key=lambda a: ranges[a])
    if normal == 0:      # YZ 平面: u=y, v=z
        return "YZ", 1, 2
    if normal == 1:      # XZ 平面: u=x, v=z
        return "XZ", 0, 2
    # XY 平面（z 恒定）：数据集标注约定 u=y, v=-x（以 ji-shape-1 的
    # flange/wall region 坐标实测对齐：v = x_max - x）
    return "XY", 1, 0


def _bezier_polyline(p0, p1, cp1, cp2, n=BEZIER_SAMPLES) -> list[tuple[float, float]]:
    """三次贝塞尔采样折线（2D）。控制点缺失时退化为线段。"""
    if cp1 is None or cp2 is None:
        return [p0, p1]
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        u = mt**3 * p0[0] + 3 * mt**2 * t * cp1[0] + 3 * mt * t**2 * cp2[0] + t**3 * p1[0]
        v = mt**3 * p0[1] + 3 * mt**2 * t * cp1[1] + 3 * mt * t**2 * cp2[1] + t**3 * p1[1]
        pts.append((u, v))
    return pts


def _polyline_length(pts: list[tuple[float, float]]) -> float:
    return sum(
        ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
        for i in range(len(pts) - 1)
    )


def build_section_geometry(section_id: str, raw: dict, source: str) -> SectionGeometry:
    """由解析出的原始 {name, points, curves} 构建带局部坐标的 Section IR。"""
    pts_raw: dict[str, tuple[float, float, float]] = raw["points"]
    curves_raw = raw["curves"]

    # 参与拓扑的点（有曲线引用）优先用于平面检测；孤立原点 (0,0,0) 不计入
    used = set()
    for item in curves_raw:
        used.add(item[1])
        used.add(item[2])
    ref_names = [n for n in pts_raw if n in used] or list(pts_raw)
    plane, ua, va = _detect_plane([pts_raw[n] for n in ref_names])
    v_sign = -1.0 if plane == "XY" else 1.0

    geo = SectionGeometry(section_id=section_id, section_name=raw["name"], source=source, plane=plane)

    for idx, (name, xyz) in enumerate(pts_raw.items()):
        if name not in used and abs(xyz[0]) < GEOM_EPS and abs(xyz[1]) < GEOM_EPS and abs(xyz[2]) < GEOM_EPS:
            continue  # 截面坐标系原点标记，非轮廓点
        geo.points[name] = Point(name=name, runtime_id=idx, xyz=xyz, uv=(xyz[ua], v_sign * xyz[va]))

    if not geo.points:
        return geo

    u_min = min(p.uv[0] for p in geo.points.values())
    v_min = min(p.uv[1] for p in geo.points.values())
    geo.u_min, geo.v_min = u_min, v_min
    for p in geo.points.values():
        p.uv_local = (p.uv[0] - u_min, p.uv[1] - v_min)

    geo.width = max(p.uv_local[0] for p in geo.points.values())
    geo.height = max(p.uv_local[1] for p in geo.points.values())

    for idx, item in enumerate(curves_raw):
        if len(item) == 3:
            name, start, end = item
            cp1 = cp2 = None
        else:
            name, start, end, cp1, cp2 = item
        if start not in geo.points or end not in geo.points:
            continue
        p0 = geo.points[start].uv_local
        p1 = geo.points[end].uv_local
        c1 = (cp1[ua] - u_min, v_sign * cp1[va] - v_min) if cp1 else None
        c2 = (cp2[ua] - u_min, v_sign * cp2[va] - v_min) if cp2 else None
        poly = _bezier_polyline(p0, p1, c1, c2)
        chord = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
        control = (cp1, cp2) if cp1 and cp2 else None
        geo.curves[name] = Curve(
            name=name, runtime_id=idx, start=start, end=end, control_xyz=control,
            polyline_local=poly, length=_polyline_length(poly), chord=chord,
        )
    return geo


def load_section_geometry(section_dir: Path) -> SectionGeometry | None:
    """加载单个截面目录（优先 .py，回退 .xml）。返回曲线数最多的 Section。"""
    section_id = section_dir.name
    py = section_dir / f"{section_id}.py"
    xml = section_dir / f"{section_id}.xml"
    if py.exists():
        raw_sections = parse_dfc_script(py)
        source = "py"
    elif xml.exists():
        raw_sections = parse_dfc_xml(xml)
        source = "xml"
    else:
        return None
    best = None
    for raw in raw_sections.values():
        if raw["curves"] and (best is None or len(raw["curves"]) > len(best["curves"])):
            best = raw
    if best is None:
        return None
    return build_section_geometry(section_id, best, source)

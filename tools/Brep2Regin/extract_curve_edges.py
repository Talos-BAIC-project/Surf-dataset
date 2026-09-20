"""Extract canonical DFC Curve/Edge records without modifying source data.

The output is an audit-friendly JSON document.  ``region_candidates`` are a
recall-only bbox mapping; they are deliberately labelled as non-gold data.
This module uses only the DFC XML/Python and the optional companion YAML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

PARSER_VERSION = "curve-edge-v1"


def _text(node: ET.Element | None) -> str | None:
    return node.text.strip() if node is not None and node.text else None


def _num(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _vec(parent: ET.Element | None, tag: str) -> list[float] | None:
    node = parent.find(tag) if parent is not None else None
    if node is None:
        return None
    vals = [_num(_text(node.find(a))) for a in ("X", "Y", "Z")]
    if all(v is not None for v in vals):
        return [float(v) for v in vals]
    vals2 = [_num(_text(x)) for x in node.findall("item")]
    return [float(v) for v in vals2[:3]] if len(vals2) >= 3 and all(v is not None for v in vals2[:3]) else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_yaml_metadata(path: Path) -> dict[str, Any]:
    """Load the small metadata subset needed here, with a stdlib fallback.

    The repository's CI may install PyYAML, but the extractor is intentionally
    usable in a clean Python installation too.  The fallback recognizes id
    and the common ``regions: ... bbox: {x, y, width, height}`` form.
    """
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        text = path.read_text(encoding="utf-8")
        result: dict[str, Any] = {}
        m = re.search(r"(?m)^\s*id:\s*['\"]?([^'\"\s#]+)", text)
        if m: result["id"] = m.group(1)
        regions = []
        region_re = re.compile(r"(?ms)^\s*-\s+name:\s*['\"]?([^'\"\n]+?)['\"]?\s*$.*?^\s*bbox:\s*\{([^}]+)\}")
        for rm in region_re.finditer(text):
            bbox: dict[str, float] = {}
            for kv in rm.group(2).split(','):
                if ':' not in kv: continue
                k, v = kv.split(':', 1)
                try: bbox[k.strip()] = float(v.strip())
                except ValueError: pass
            regions.append({"name": rm.group(1).strip(), "bbox": bbox})
        if regions: result["regions"] = regions
        return result


def _dist(a: list[float] | None, b: list[float] | None) -> float | None:
    if not a or not b:
        return None
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _bbox(points: Iterable[list[float]]) -> dict[str, float] | None:
    pts = list(points)
    if not pts:
        return None
    # DFC section geometry uses local sCoord Y/Z as the 2D plane.
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return {"min_y": min(ys), "min_z": min(zs), "max_y": max(ys), "max_z": max(zs),
            "width": max(ys) - min(ys), "height": max(zs) - min(zs)}


def _bezier(a: list[float], c1: list[float], c2: list[float], b: list[float], n: int = 24) -> list[list[float]]:
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append([u**3*a[j] + 3*u*u*t*c1[j] + 3*u*t*t*c2[j] + t**3*b[j] for j in range(3)])
    return out


def _parse_py(path: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Parse the small, stable createSecNode/createSecCurve macro dialect."""
    text = path.read_text(encoding="utf-8")
    point_re = re.compile(r"(?:([A-Za-z_]\w*)\s*=\s*)?theModel\.createSecNode\(\s*x\s*=\s*([-+0-9.eE]+)\s*,\s*y\s*=\s*([-+0-9.eE]+)\s*,\s*z\s*=\s*([-+0-9.eE]+)")
    curve_re = re.compile(r"(?:([A-Za-z_]\w*)\s*=\s*)?theModel\.createSecCurve\(\s*start\s*=\s*(\w+)\s*,\s*end\s*=\s*(\w+)")
    points: dict[str, dict[str, Any]] = {}
    for i, m in enumerate(point_re.finditer(text), 1):
        name = m.group(1) or f"point_{i}"
        p = [float(m.group(j)) for j in (2, 3, 4)]
        points[name] = {"id": name, "name": name, "gCoord": p, "sCoord": p}
    curves = []
    for i, m in enumerate(curve_re.finditer(text), 1):
        name = m.group(1) or f"curve_{i}"
        curves.append({"id": name, "name": name, "start_name": m.group(2), "end_name": m.group(3), "type": "line"})
    return points, curves


def _xml_records(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = ET.parse(path).getroot()
    sections: list[dict[str, Any]] = []
    section_names: set[str] = set()
    for sec in root.findall(".//Section"):
        name = _text(sec.find("Name")) or "section"
        sid = _text(sec.find("ID")) or name
        sections.append({"id": sid, "name": name, "coord_sys_id": _text(sec.find("CoordSysID")), "points": [], "curves": []})
        section_names.add(name)
    if not sections:
        sections = [{"id": "section-1", "name": "section-1", "coord_sys_id": None, "points": [], "curves": []}]
        section_names.add("section-1")
    by_name = {s["name"]: s for s in sections}
    for sec in sections:
        sec["surface_groups"] = []
    for group in root.findall(".//SurfaceGroups/SurfaceGroup"):
        group_name = _text(group.find("Name"))
        for item in group.findall("SectionName/item"):
            if _text(item) in by_name and group_name:
                by_name[_text(item)]["surface_groups"].append(group_name)
    diagnostics: list[dict[str, Any]] = []
    points_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    points_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in root.findall(".//Point"):
        name = _text(p.find("Name"))
        if not name or _text(p.find("Type")) not in ("2", None):
            continue
        sec_name = _text(p.find("sectionName")) or (name.split("_SP_")[0] if "_SP_" in name else next(iter(section_names)))
        sec = by_name.get(sec_name) or sections[0]
        rec = {"id": _text(p.find("ID")) or name, "name": name, "gCoord": _vec(p, "gCoord"), "sCoord": _vec(p, "sCoord"), "section": sec["name"]}
        sec["points"].append(rec)
        points_by_id[rec["id"]].append(rec)
        points_by_name[name].append(rec)
    for key, vals in points_by_id.items():
        if len(vals) > 1:
            diagnostics.append({"code": "duplicate_point_id", "id": key, "count": len(vals)})
    for key, vals in points_by_name.items():
        if len(vals) > 1:
            diagnostics.append({"code": "duplicate_point_name", "name": key, "count": len(vals)})
    curves_by_id: dict[str, int] = defaultdict(int)
    for c in root.findall(".//Curve"):
        name = _text(c.find("Name")) or "curve"
        sec_name = _text(c.find("sectionName")) or (name.split("_SL_")[0] if "_SL_" in name else next(iter(section_names)))
        sec = by_name.get(sec_name) or sections[0]
        start_name = _text(c.find("startPointName"))
        end_name = _text(c.find("endPointName"))
        start_id = _text(c.find("startPointID")); end_id = _text(c.find("endPointID"))
        def resolve_point(point_name: str | None, point_id: str | None) -> dict[str, Any] | None:
            matches = [p for p in (points_by_name.get(point_name) or points_by_id.get(point_id) or []) if p["section"] == sec["name"]]
            # A duplicate ID/name is an ambiguity, never permission to pick the first.
            return matches[0] if len(matches) == 1 else None
        start = resolve_point(start_name, start_id)
        end = resolve_point(end_name, end_id)
        if start is None or end is None:
            diagnostics.append({"code": "missing_or_ambiguous_endpoint", "curve": name, "section": sec["name"],
                                "start": start_name or start_id, "end": end_name or end_id})
        controls = []
        for i in (1, 2):
            v = _vec(c, f"controlPoint_{i}_sCoord") or _vec(c, f"controlPoint_{i}_gCoord")
            if v is not None:
                controls.append(v)
        rec = {"id": _text(c.find("ID")) or name, "name": name, "type_raw": _text(c.find("Type")), "type": "bezier" if controls else "line",
               "start_point_id": start_id, "end_point_id": end_id, "start_point_name": start_name, "end_point_name": end_name,
               "start": start, "end": end, "control_points": controls, "section": sec["name"]}
        sec["curves"].append(rec)
        curves_by_id[rec["id"]] += 1
    for key, count in curves_by_id.items():
        if count > 1:
            diagnostics.append({"code": "duplicate_curve_id", "id": key, "count": count})
    return sections, diagnostics


def _topology(section: dict[str, Any], tolerance: float) -> None:
    curves = section["curves"]
    valid = [c for c in curves if c["start"] is not None and c["end"] is not None]
    adj: dict[str, list[int]] = defaultdict(list)
    for index, c in enumerate(valid):
        a, b = c["start"]["name"], c["end"]["name"]
        adj[a].append(index); adj[b].append(index)
    components: dict[str, int] = {}; comp = 0
    for point in adj:
        if point in components: continue
        comp += 1; q = deque([point]); components[point] = comp
        while q:
            p = q.popleft()
            for curve_index in adj[p]:
                c = valid[curve_index]
                for n in (c["start"]["name"], c["end"]["name"]):
                    if n not in components: components[n] = comp; q.append(n)
    nodes = [{"point": p, "degree": len(v), "role": "branch" if len(v) > 2 else ("endpoint" if len(v) == 1 else "junction")} for p, v in sorted(adj.items())]
    has_branch = any(n["role"] == "branch" for n in nodes)
    has_endpoint = any(n["role"] == "endpoint" for n in nodes)
    classification = "branched" if has_branch else ("open" if has_endpoint else ("closed" if valid else "unknown"))
    section["topology"] = {"valid_curve_count": len(valid), "complete": len(valid) == len(curves), "component_count": comp, "nodes": nodes,
                            "branch_count": sum(n["role"] == "branch" for n in nodes), "endpoint_count": sum(n["role"] == "endpoint" for n in nodes),
                            "classification": classification, "tolerance": tolerance}
    for c in curves:
        a, b = c["start"], c["end"]
        if a is None or b is None:
            c["endpoint_valid"] = False; c["connectivity"] = {"component_id": None, "start_degree": None, "end_degree": None}
            c["topology_signature"] = "missing_endpoint"
            continue
        an, bn = a["name"], b["name"]
        c["endpoint_valid"] = True
        c["connectivity"] = {"component_id": components.get(an), "start_degree": len(adj[an]), "end_degree": len(adj[bn])}
        c["topology_signature"] = f"{section['topology']['classification']}:d{len(adj[an])}-d{len(adj[bn])}:c{components.get(an)}"


def _finalize(section: dict[str, Any], tolerance: float) -> None:
    for c in section["curves"]:
        start, end = c.pop("start"), c.pop("end")
        c["start"] = {k: start[k] for k in ("id", "name", "gCoord", "sCoord")} if start else None
        c["end"] = {k: end[k] for k in ("id", "name", "gCoord", "sCoord")} if end else None
        path = [p for p in ([start["sCoord"] if start else None] + c["control_points"] + [end["sCoord"] if end else None]) if p]
        c["bbox"] = _bbox(path)
        c["bbox_method"] = "control_hull" if c["control_points"] else "endpoints"
        c["length"] = None
        c["length_method"] = None
        if start and end and start.get("sCoord") and end.get("sCoord"):
            samples = _bezier(path[0], path[1], path[2], path[-1]) if len(c["control_points"]) == 2 else [start["sCoord"], end["sCoord"]]
            c["length"] = sum(_dist(a, b) or 0 for a, b in zip(samples, samples[1:]))
            c["length_method"] = "bezier_sample_24" if len(c["control_points"]) == 2 else "endpoint_distance"
        if start and end and start.get("sCoord") and end.get("sCoord"):
            c["orientation"] = {"vector": [end["sCoord"][i] - start["sCoord"][i] for i in range(3)], "angle_deg": math.degrees(math.atan2(end["sCoord"][2] - start["sCoord"][2], end["sCoord"][1] - start["sCoord"][1]))}
        else:
            c["orientation"] = None
    _topology(section, tolerance)


def _region_candidates(section: dict[str, Any], metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    result = []
    bounds = section.get("bbox") or _bbox([p["sCoord"] for p in section["points"] if p.get("sCoord")])
    if not bounds: return result
    for region in (metadata or {}).get("regions", []) or []:
        bb = region.get("bbox", {})
        rx, ry = bb.get("x"), bb.get("y")
        rw, rh = (bb.get("depth"), bb.get("width")) if "depth" in bb and "height" not in bb else (bb.get("width"), bb.get("height"))
        if not all(isinstance(x, (int, float)) for x in (rx, ry, rw, rh)): continue
        ids = []
        for c in section["curves"]:
            cb = c.get("bbox")
            if not cb: continue
            ymin, ymax = cb["min_y"] - bounds["min_y"], cb["max_y"] - bounds["min_y"]
            zmin, zmax = cb["min_z"] - bounds["min_z"], cb["max_z"] - bounds["min_z"]
            if ymax >= rx and ymin <= rx + rw and zmax >= ry and zmin <= ry + rh: ids.append(c["id"])
        result.append({"region_id": region.get("name"), "curve_ids": ids, "method": "bbox_candidates_not_gold",
                       "coordinate_system": "section_bbox_min_as_origin"})
    return result


def extract(source: str | Path, tolerance: float = 1e-6) -> dict[str, Any]:
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive")
    source = Path(source).resolve()
    metadata: dict[str, Any] | None = None
    geometry = source
    if source.suffix.lower() in (".yaml", ".yml"):
        metadata = _load_yaml_metadata(source)
        for candidate in (source.with_suffix(".xml"), source.with_suffix(".py")):
            if candidate.exists(): geometry = candidate; break
        else: raise FileNotFoundError(f"companion XML/Python geometry not found for {source}")
    if geometry.suffix.lower() == ".xml": sections, diagnostics = _xml_records(geometry)
    elif geometry.suffix.lower() == ".py":
        points, curves = _parse_py(geometry)
        sec_name = (metadata or {}).get("id", geometry.stem)
        sections = [{"id": sec_name, "name": sec_name, "coord_sys_id": None, "points": list(points.values()), "curves": []}]
        for c in curves:
            c["start"] = points.get(c.pop("start_name")); c["end"] = points.get(c.pop("end_name")); c["section"] = sec_name; c["control_points"] = []
            sections[0]["curves"].append(c)
        diagnostics = []
    else: raise ValueError("source must be .xml, .py, .yaml or .yml")
    for sec in sections:
        _finalize(sec, tolerance)
        sec["bbox"] = _bbox([p["sCoord"] for p in sec["points"] if p.get("sCoord")])
        sec["region_candidates"] = _region_candidates(sec, metadata)
        sec["points"] = [{k: p.get(k) for k in ("id", "name", "gCoord", "sCoord")} for p in sec["points"]]
        for c in sec["curves"]:
            c.pop("section", None)
            c["scope"] = {"model": geometry.stem, "surface_groups": sec.get("surface_groups", []),
                          "section_id": sec["id"], "section": sec["name"]}
            if not c["endpoint_valid"] and geometry.suffix.lower() == ".py":
                diagnostics.append({"code": "missing_or_ambiguous_endpoint", "curve": c["name"], "section": sec["name"]})
    source_info = {"file": str(source), "sha256": _sha256(source), "geometry_file": str(geometry), "geometry_sha256": _sha256(geometry)}
    edge_map = [{"section_id": s["id"], "section": s["name"], "regions": s["region_candidates"]} for s in sections]
    return {"schema_version": "1.0", "parser_version": PARSER_VERSION, "tolerance": tolerance,
            "source": source_info, "manifest": {"source": source_info, "parser_version": PARSER_VERSION, "tolerance": tolerance,
                                                   "sections": [s["name"] for s in sections], "gold": False},
            "sections": sections, "edge_map": edge_map, "diagnostics": diagnostics}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract canonical DFC Curve/Edge records")
    p.add_argument("source", nargs="?", help="section XML, Python macro, or YAML with a companion XML/Python")
    p.add_argument("--section", dest="section", help="named alias for the source path")
    p.add_argument("-o", "--output", help="write JSON here; stdout by default (also writes .edge_map.json and .manifest.json)")
    p.add_argument("--tolerance", type=float, default=1e-6)
    args = p.parse_args(argv)
    source = args.section or args.source
    if not source:
        p.error("a source path or --section is required")
    try: result = extract(source, args.tolerance)
    except (OSError, ValueError, ET.ParseError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.write_text(text + "\n", encoding="utf-8")
        output.with_name(output.stem + ".edge_map.json").write_text(json.dumps(result["edge_map"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.with_name(output.stem + ".manifest.json").write_text(json.dumps(result["manifest"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else: print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""端到端 Mapper：Label / 工程师原话 -> 实体集合 + 置信度 + 证据 + 决策。

输出契约（对齐调研文档 §1.3）：实体集合是"可审计的定位结果"，
不是修改授权；低置信度必须走 needs_confirmation / not_found。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .config import CONF_NEEDS_CONFIRMATION, CONF_RESOLVED
from .labels import LabelProfile, LabelRegistry, Selector
from .models import ModelBank, rule_point_scores
from .pipeline import SectionBundle

SCORE_THRESHOLD = 0.5


@dataclass
class Instance:
    """一个可选实体实例（如"一条筋"、"一个腔"）。"""
    entity_type: str            # curve_group | face | point
    curves: list[str]
    faces: list[str]
    points: list[str]
    score: float
    centroid: tuple[float, float]

    def key_entities(self) -> list[str]:
        if self.entity_type == "face":
            return self.faces
        if self.entity_type == "point":
            return self.points
        return self.curves


class Mapper:
    def __init__(self, bundles: list[SectionBundle], registry: LabelRegistry,
                 bank: ModelBank):
        self.by_section = {b.record.section_id: b for b in bundles}
        self.registry = registry
        self.bank = bank

    # ------------------------------------------------------------------
    def map_query(self, section_id: str, query: str | None = None,
                  label_id: str | None = None, selector: Selector | None = None,
                  top_k: int = 10) -> dict:
        t0 = time.perf_counter()
        bundle = self.by_section.get(section_id)
        if bundle is None:
            return self._reply(t0, section_id, query, None, None, "unsupported",
                               0.0, [], [], [f"unknown_section:{section_id}"])

        # 1. 解析查询
        profile: LabelProfile | None = None
        sel = selector or Selector()
        text_score = 1.0
        evidence: list[str] = []
        if label_id is not None:
            profile = self.registry.by_id.get(label_id) \
                or self.registry.by_short.get(label_id.rsplit(".", 1)[-1])
            evidence.append("input:label_id")
        if profile is None and query:
            resolved = self.registry.resolve(query)
            if resolved is not None:
                profile = resolved.profile
                text_score = resolved.score
                if selector is None:
                    sel = resolved.selector
                evidence.append(f"text:{resolved.evidence}={resolved.matched_alias}")
        if profile is None:
            return self._reply(t0, section_id, query, None, sel, "unsupported",
                               0.0, [], [], ["unresolved_query"])

        # 2. 候选打分
        feats = bundle.features
        short = profile.short
        if profile.entity_type == "face":
            scores, scorer = self.bank.score_faces(feats)
            names = feats.face_ids
            if len(names) == 0:
                return self._reply(t0, section_id, query, profile, sel, "unsupported",
                                   0.0, [], [], ["no_closed_cells_in_section"], scorer="none")
            # 腔体候选的确定性过滤（规则候选层，见调研 §10.2）：
            # 1) 有子腔的父 cell 让位（深腰=数据集"双腔"标注策略）；
            # 2) 碎片 cell（厚筋内腔等，面积 <5% 最大 cell）不是腔体。
            parents_with_subs = {s.parent_cell for s in bundle.graph.subcells}
            max_area = max((c.area for c in bundle.graph.cells), default=1.0)
            keep = []
            for i, fid in enumerate(names):
                face = feats.face_by_id(fid)
                if fid in parents_with_subs:
                    continue
                if face is not None and face.area < 0.05 * max_area:
                    continue
                keep.append(i)
            names = [names[i] for i in keep]
            scores = scores[keep]
            if not names:
                return self._reply(t0, section_id, query, profile, sel, "not_found",
                                   0.0, [], [], evidence + ["no_face_candidates"], scorer=scorer)
        else:
            scores, scorer = self.bank.score_curves(short, feats)
            names = feats.curve_names
        evidence.append(f"scorer:{scorer}")

        ranked = sorted(zip(names, scores.tolist()), key=lambda kv: -kv[1])
        selected = [n for n, s in ranked if s >= SCORE_THRESHOLD]

        # 倒角查询兜底：无过渡段实体时回退到角点（DFC 中倒角常被简化为尖角）
        point_mode = False
        if short == "fillet" and not selected:
            pnames, pscores = rule_point_scores(feats)
            p_ranked = sorted(zip(pnames, pscores.tolist()), key=lambda kv: -kv[1])
            p_sel = [n for n, s in p_ranked if s >= 0.35]
            if p_sel:
                point_mode = True
                evidence.append("fallback:corner_points")
                ranked = p_ranked
                selected = p_sel

        if not selected:
            return self._reply(t0, section_id, query, profile, sel, "not_found",
                               float(ranked[0][1]) if ranked else 0.0, [], ranked[:top_k],
                               evidence + ["no_entity_above_threshold"], scorer=scorer)

        # 3. 组实例
        score_map = dict(ranked)
        if profile.entity_type == "face" and not point_mode:
            instances = self._face_instances(bundle, selected, score_map)
        elif point_mode:
            instances = [self._point_instance(bundle, n, score_map[n]) for n in selected]
        else:
            instances = self._curve_instances(bundle, selected, score_map)

        # 4. 序数排序（自上而下、自左向右）与 selector 过滤
        instances.sort(key=lambda i: (-i.centroid[1], i.centroid[0]))
        flags: list[str] = []
        chosen = instances
        if sel.position:
            chosen = self._filter_position(bundle, chosen, sel.position, sel.count)
            evidence.append(f"selector:position={sel.position}")
        if sel.ordinal is not None:
            if sel.ordinal <= len(chosen):
                chosen = [chosen[sel.ordinal - 1]]
                evidence.append(f"selector:ordinal={sel.ordinal}")
            else:
                return self._reply(t0, section_id, query, profile, sel, "not_found",
                                   0.0, [], ranked[:top_k],
                                   evidence + [f"ordinal_out_of_range:{sel.ordinal}>{len(chosen)}"],
                                   scorer=scorer)
        if sel.count is not None and len(chosen) != sel.count:
            if len(chosen) > sel.count:
                by_score = sorted(chosen, key=lambda i: -i.score)[: sel.count]
                chosen = [i for i in chosen if i in by_score]
                evidence.append(f"selector:count={sel.count}(截取)")
            else:
                flags.append(f"count_mismatch:expect{sel.count}_got{len(chosen)}")

        # 5. 置信度与决策
        ent_scores = [i.score for i in chosen]
        confidence = float(np.mean(ent_scores)) * text_score if ent_scores else 0.0
        if not chosen:
            decision = "not_found"
        elif confidence >= CONF_RESOLVED and not flags:
            decision = "resolved"
        elif confidence >= CONF_NEEDS_CONFIRMATION:
            decision = "needs_confirmation"
        else:
            decision = "not_found"

        # 模型证据：首个实例的特征贡献
        model = self.bank.curve_models.get(short) if profile.entity_type != "face" else self.bank.face_model
        if model is not None and chosen and not point_mode:
            first = chosen[0].key_entities()
            if first:
                try:
                    if profile.entity_type == "face":
                        idx = feats.face_ids.index(first[0])
                        evidence += [f"feat:{f}" for f in model.top_contributions(feats.face_matrix[idx])]
                    else:
                        idx = feats.curve_names.index(first[0])
                        evidence += [f"feat:{f}" for f in model.top_contributions(feats.curve_matrix[idx])]
                except ValueError:
                    pass

        return self._reply(t0, section_id, query, profile, sel, decision, confidence,
                           chosen, ranked[:top_k], evidence + flags, scorer=scorer)

    # ------------------------------------------------------------------
    def _curve_instances(self, bundle: SectionBundle, selected: list[str],
                         score_map: dict[str, float]) -> list[Instance]:
        graph = bundle.graph
        node_of: dict[str, set[str]] = {}
        for e in graph.edges:
            if e.orig_curve in graph.geo.curves:
                node_of.setdefault(e.orig_curve, set()).update((e.node_a, e.node_b))
        parent = {c: c for c in selected}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        sel_set = set(selected)
        node_index: dict[str, list[str]] = {}
        for c in selected:
            for nd in node_of.get(c, ()):  # 共享平面化节点 => 同一实例
                node_index.setdefault(nd, []).append(c)
        for group in node_index.values():
            for other in group[1:]:
                ra, rb = find(group[0]), find(other)
                if ra != rb:
                    parent[rb] = ra
        groups: dict[str, list[str]] = {}
        for c in sel_set:
            groups.setdefault(find(c), []).append(c)

        out = []
        for members in groups.values():
            pts, w_len = [], 0.0
            cx = cy = 0.0
            for c in members:
                cv = bundle.graph.geo.curves[c]
                mid = cv.polyline_local[len(cv.polyline_local) // 2]
                cx += mid[0] * cv.length
                cy += mid[1] * cv.length
                w_len += cv.length
                for p in (cv.start, cv.end):
                    if p not in pts:
                        pts.append(p)
            w_len = max(w_len, 1e-9)
            members_sorted = sorted(members, key=lambda c: bundle.graph.geo.curves[c].runtime_id)
            out.append(Instance(
                entity_type="curve_group", curves=members_sorted, faces=[], points=pts,
                score=float(np.mean([score_map[c] for c in members])),
                centroid=(cx / w_len, cy / w_len),
            ))
        return out

    def _face_instances(self, bundle: SectionBundle, selected: list[str],
                        score_map: dict[str, float]) -> list[Instance]:
        # cell 与其子腔同时被选中时，保留得分高的粒度
        by_parent: dict[str, list[str]] = {}
        cells = {c.cell_id for c in bundle.graph.cells}
        for fid in selected:
            if "#" in fid:
                by_parent.setdefault(fid.split("#")[0], []).append(fid)
        final: list[str] = []
        for fid in selected:
            if "#" in fid:
                parent = fid.split("#")[0]
                if parent in selected:
                    subs = by_parent[parent]
                    sub_mean = float(np.mean([score_map[s] for s in subs]))
                    if sub_mean >= score_map[parent]:
                        final.append(fid)
                else:
                    final.append(fid)
            else:
                subs = by_parent.get(fid, [])
                if subs:
                    sub_mean = float(np.mean([score_map[s] for s in subs]))
                    if score_map[fid] > sub_mean:
                        final.append(fid)
                else:
                    final.append(fid)
        _ = cells
        out = []
        for fid in final:
            face = bundle.features.face_by_id(fid)
            if face is None:
                continue
            out.append(Instance(
                entity_type="face", curves=list(face.curve_names), faces=[fid],
                points=list(face.point_names), score=score_map[fid], centroid=face.centroid,
            ))
        return out

    def _point_instance(self, bundle: SectionBundle, pname: str, score: float) -> Instance:
        pt = bundle.graph.geo.points[pname]
        return Instance(entity_type="point", curves=[], faces=[], points=[pname],
                        score=score, centroid=pt.uv_local)

    def _filter_position(self, bundle: SectionBundle, instances: list[Instance],
                         position: str, count: int | None) -> list[Instance]:
        """按位置词过滤实例。给定数量时取位置最优的前 count 个；
        否则取最优者及其"并列近邻"（歧义留给 needs_confirmation）。"""
        if not instances:
            return instances
        W = max(bundle.graph.geo.width, 1e-9)
        H = max(bundle.graph.geo.height, 1e-9)
        crit = {
            "center": lambda i: abs(i.centroid[1] / H - 0.5) + 0.3 * abs(i.centroid[0] / W - 0.5),
            "top": lambda i: -i.centroid[1] / H,
            "bottom": lambda i: i.centroid[1] / H,
            "left": lambda i: i.centroid[0] / W,
            "right": lambda i: -i.centroid[0] / W,
        }[position]
        ranked = sorted(instances, key=crit)
        if count is not None:
            keep = set(id(i) for i in ranked[:count])
            return [i for i in instances if id(i) in keep]
        best_val = crit(ranked[0])
        near = [i for i in ranked if crit(i) - best_val <= 0.12]
        keep = set(id(i) for i in near)
        return [i for i in instances if id(i) in keep]

    # ------------------------------------------------------------------
    def _reply(self, t0: float, section_id: str, query: str | None,
               profile: LabelProfile | None, selector: Selector | None,
               decision: str, confidence: float, chosen: list[Instance],
               ranked_topk: list, evidence: list[str], scorer: str = "none") -> dict:
        bundle = self.by_section.get(section_id)
        geo = bundle.graph.geo if bundle else None
        targets = []
        derived_points: list[str] = []
        derived_curves: list[str] = []
        for inst in chosen:
            for c in inst.curves:
                cv = geo.curves[c]
                if inst.entity_type == "face":
                    # 面实例的边界曲线是派生高亮，不是主目标
                    if c not in derived_curves:
                        derived_curves.append(c)
                    continue
                targets.append({
                    "entity_type": "curve", "name": c, "runtime_id": cv.runtime_id,
                    "stable_ref": f"{section_id}/{geo.section_name}/curve/{c}",
                })
            for f in inst.faces:
                targets.append({
                    "entity_type": "face", "name": f, "runtime_id": None,
                    "stable_ref": f"{section_id}/{geo.section_name}/derived_face/{f}",
                })
            for p in inst.points:
                if inst.entity_type == "point":
                    targets.append({
                        "entity_type": "point", "name": p,
                        "runtime_id": geo.points[p].runtime_id,
                        "stable_ref": f"{section_id}/{geo.section_name}/point/{p}",
                    })
                elif p not in derived_points:
                    derived_points.append(p)
        version = ""
        if bundle is not None:
            version = str(((bundle.record.meta.get("metadata") or {}).get("version")) or "")
        return {
            "query": query,
            "label_id": profile.label_id if profile else None,
            "entity_type": profile.entity_type if profile else None,
            "section_id": section_id,
            "model_version": version,
            "selector": {
                "ordinal": selector.ordinal if selector else None,
                "count": selector.count if selector else None,
                "position": selector.position if selector else None,
            },
            "decision": decision,
            "confidence": round(float(confidence), 4),
            "scorer": scorer,
            "targets": targets,
            "derived_points": derived_points,
            "derived_curves": derived_curves,
            "instances": [
                {
                    "rank": i + 1, "score": round(inst.score, 4),
                    "entity_type": inst.entity_type,
                    "curves": inst.curves, "faces": inst.faces, "points": inst.points,
                }
                for i, inst in enumerate(chosen)
            ],
            "candidates_topk": [
                {"name": n, "score": round(float(s), 4)} for n, s in ranked_topk
            ],
            "evidence": evidence,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
        }

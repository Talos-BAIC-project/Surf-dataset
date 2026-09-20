"""Audit published augmentation data; optionally reproduce it from pinned Git blobs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
GATES = {"cell_count", "targets_non_empty", "label_cooccurrence", "affine_agreement",
         "unique_geometry", "geometry_reasonable"}


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def _inside(root, relative):
    path = (root / relative).resolve()
    _check(path.is_relative_to(root.resolve()), f"path outside root: {relative}")
    return path


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_record(row, source_hashes):
    sid = row["source_id"]
    _check(row["shape_family"] == row["family"], f"family mismatch: {sid}")
    refs = row["source_manifest"]
    _check(bool(refs), f"missing provenance: {sid}")
    for ref in refs:
        _check(source_hashes.get(f"sections/{sid}/{ref['file']}") == ref["sha256"],
               f"source hash mismatch: {sid}/{ref['file']}")
    canonical = json.dumps(refs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _check(_sha(canonical.encode()) == row["source_sha256"], f"manifest hash mismatch: {sid}")
    report = row["validation_report"]
    _check(report["passed"] is True and not report["failures"], f"failed validation: {sid}")
    _check(set(report["gates"]) == GATES, f"missing gates: {sid}")
    _check(all(g["passed"] is True for g in report["gates"].values()), f"failed gate: {sid}")
    _check(bool(row["propagated_labels"]), f"missing labels: {sid}")
    silver = {(x["region_name"], x["label_id"], x["entity_type"]): x for x in row["silver"]}
    for label in row["propagated_labels"]:
        key = (label["region_name"], label["label_id"], label["entity_type"])
        target = silver.get(key)
        _check(target is not None, f"propagated label missing from silver: {sid}/{key}")
        _check(target["curve_names"] == label["curve_names"] and target["face_ids"] == label["face_ids"],
               f"propagated entity set differs: {sid}/{key}")
    geo = row["geometry"]
    names = {c["name"] for c in geo["curves"]}
    _check(len(names) == len(geo["curves"]), f"duplicate curve names: {sid}")
    for curve in geo["curves"]:
        _check(curve["start"] in geo["points"] and curve["end"] in geo["points"],
               f"missing curve endpoint: {sid}/{curve['name']}")
    for children in row["name_map"].values():
        _check(set(children) <= names, f"unknown split child: {sid}")


def verify_release(*, reproduce=False):
    manifest = json.loads((TOOL_ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    commit = manifest["dataset_commit"]
    _check(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "invalid dataset commit")
    source_hashes = {s["path"]: s["sha256"] for s in manifest["source_files"]}
    blobs = {}
    git_hits = 0
    workdir_hits = 0
    for path, expected in source_hashes.items():
        _inside(REPO_ROOT / "sections", path.removeprefix("sections/"))
        result = subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{commit}:{path}"],
                                capture_output=True)
        if result.returncode == 0:
            data = result.stdout
            git_hits += 1
        else:
            data = _inside(REPO_ROOT, path).read_bytes()
            workdir_hits += 1
        _check(_sha(data) == expected, f"source hash mismatch: {path}")
        blobs[path] = data
    # #region agent log
    try:
        import time
        _dbg = Path(__file__).resolve().parents[3] / "DP" / "debug-c5fe58.log"
        _dbg.parent.mkdir(parents=True, exist_ok=True)
        with _dbg.open("a", encoding="utf-8") as _fh:
            _fh.write(json.dumps({
                "sessionId": "c5fe58",
                "runId": "verify1",
                "hypothesisId": "E",
                "location": "verify_release.py:verify_release",
                "message": "source blob resolution",
                "data": {"git_hits": git_hits, "workdir_hits": workdir_hits, "commit": commit},
                "timestamp": int(time.time() * 1000),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion
    datasets = []
    for spec in manifest["datasets"]:
        data = _inside(TOOL_ROOT, spec["path"]).read_bytes()
        _check(_sha(data) == spec["sha256"], f"data hash mismatch: {spec['name']}")
        report = _inside(TOOL_ROOT, spec["report_path"]).read_bytes()
        _check(_sha(report) == spec["report_sha256"], f"report hash mismatch: {spec['name']}")
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        _check(len(rows) == spec["records"], "record count mismatch")
        _check(len({r["variant_id"] for r in rows}) == len(rows), "duplicate variant ID")
        _check(len({r["source_id"] for r in rows}) == spec["source_count"], "source count mismatch")
        _check(all(r["seed"] == spec["seed"] for r in rows), "seed mismatch")
        ops = Counter(op["kind"] for row in rows for op in row["ops"])
        _check(dict(ops) == spec["operations"], "operation counts mismatch")
        for row in rows:
            verify_record(row, source_hashes)
        datasets.append((spec, rows))
    if reproduce:
        from .label2brep.augment import generate_variants, select_pilot_bundles
        from .label2brep.pipeline import build_corpus
        # Exact historical bytes avoid OS-dependent checkout line endings.
        with tempfile.TemporaryDirectory(prefix="brep2regin-replay-") as temporary:
            root = Path(temporary)
            for path, data in blobs.items():
                target = _inside(root, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            corpus, registry = build_corpus(root / "sections")
            _check(len(corpus) == manifest["corpus_sections"], "corpus count mismatch")
            for spec, expected in datasets:
                selected = select_pilot_bundles(corpus) if spec["pilot"] else corpus
                variants, _ = generate_variants(selected, registry, seed=spec["seed"],
                                               per_section=spec["per_section"], quota=spec["quota"])
                actual = json.loads(json.dumps([v.to_record() for v in variants]))
                _check(actual == expected, f"reproduction differs: {spec['name']}")
                print(f"reproduced {spec['name']}: {len(actual)} identical records", flush=True)
    return {"source_files_verified": len(blobs), "datasets": {s["name"]: len(r) for s, r in datasets},
            "reproduced": reproduce, "label_quality": manifest["label_quality"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reproduce", action="store_true", help="regenerate both batches and compare every record")
    args = parser.parse_args()
    print(json.dumps(verify_release(reproduce=args.reproduce), indent=2))


if __name__ == "__main__":
    main()

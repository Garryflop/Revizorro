"""Measure a Revizorro report against the hand-labelled defect list and the precision labels.

Usage (from the repo root):
    uv run --project backend python eval/evaluate.py reports/report.json
    uv run --project backend python eval/evaluate.py reports/report.json --labels eval/labels.csv

Recall: share of expected defects (eval/expected_defects.yaml) matched by kept findings.
Precision: from eval/labels.csv, where a human marks each finding: в — верно, л — ложно, с — спорно.
New findings are appended to labels.csv with an empty verdict; existing verdicts are kept.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import yaml

from revizorro.tools.quotes import normalize

HERE = Path(__file__).resolve().parent
SEV_RANK = {"critical": 0, "major": 1, "minor": 2}
FIELDS = ["key", "fid", "refs", "criterion", "severity", "title", "quote", "verdict", "comment"]


def finding_key(f: dict) -> str:
    """Stable across runs: criterion + requirement refs + first quote."""
    refs = f.get("rid") or ",".join(sorted(f.get("related_rids") or []))
    quote = normalize(f["locations"][0]["quote"]) if f.get("locations") else ""
    return hashlib.sha1(f"{f['criterion']}|{refs}|{quote}".encode()).hexdigest()[:12]


def anchor_blocks(blocks: list[dict], anchors: list[str]) -> set[str]:
    found: set[str] = set()
    for a in anchors:
        a_n = normalize(a)
        found.update(b["id"] for b in blocks if a_n in normalize(b["text"]))
    return found


def matches(defect: dict, f: dict, blocks: set[str]) -> bool:
    text = " ".join([f["title"], f["problem"], f.get("suggestion", ""), f.get("impact", "")]).lower()
    keywords = defect.get("keywords") or []
    if keywords and not any(k.lower() in text for k in keywords):
        return False
    if defect.get("anchors"):
        return any(loc["block_id"] in blocks for loc in f["locations"])
    return f["criterion"] in (defect.get("criteria") or [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--expected", type=Path, default=HERE / "expected_defects.yaml")
    ap.add_argument("--labels", type=Path, default=HERE / "labels.csv")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    report = json.loads(args.report.read_text(encoding="utf-8"))
    blocks = report["document"]["blocks"]
    kept = [f for f in report["findings"] if f["status"] == "kept"]
    expected = yaml.safe_load(args.expected.read_text(encoding="utf-8"))

    # ---- recall ----
    hit: dict[str, list[str]] = {}
    matched_fids: set[str] = set()
    for d in expected:
        ab = anchor_blocks(blocks, d.get("anchors") or [])
        if d.get("anchors") and not ab:
            print(f"! {d['id']}: якорь не найден в документе: {d['anchors']}")
        fids = [f["fid"] for f in kept if matches(d, f, ab)]
        hit[d["id"]] = fids
        matched_fids.update(fids)

    found = [d for d in expected if hit[d["id"]]]
    print(
        f"\nПолнота (recall): {len(found)} из {len(expected)} эталонных дефектов = {len(found) / len(expected):.0%}"
    )
    for sev in ("critical", "major", "minor"):
        group = [d for d in expected if d["severity"] == sev]
        if group:
            n = sum(bool(hit[d["id"]]) for d in group)
            print(f"  {sev:8}: {n} из {len(group)}")
    print("\nНе найдены:")
    for d in expected:
        if not hit[d["id"]]:
            print(f"  {d['id']} [{d['severity']}] {d['title']}")

    extra = [f for f in kept if f["fid"] not in matched_fids]
    print(f"\nНаходок вне эталона: {len(extra)} из {len(kept)} (новые верные или ложные — см. разметку)")

    # ---- labels / precision ----
    existing: dict[str, dict] = {}
    if args.labels.is_file():
        with args.labels.open(encoding="utf-8-sig", newline="") as fh:
            existing = {row["key"]: row for row in csv.DictReader(fh)}

    rows = []
    for f in sorted(kept, key=lambda f: (SEV_RANK[f["severity"]], f["fid"])):
        key = finding_key(f)
        prev = existing.get(key, {})
        rows.append(
            {
                "key": key,
                "fid": f["fid"],
                "refs": f.get("rid") or ",".join(f.get("related_rids") or []),
                "criterion": f["criterion"],
                "severity": f["severity"],
                "title": f["title"],
                "quote": f["locations"][0]["quote"] if f["locations"] else "",
                "verdict": prev.get("verdict", ""),
                "comment": prev.get("comment", ""),
            }
        )
    current = {r["key"] for r in rows}
    stale = [row for key, row in existing.items() if key not in current and row.get("verdict")]
    args.labels.parent.mkdir(parents=True, exist_ok=True)
    with args.labels.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerows({k: row.get(k, "") for k in FIELDS} for row in stale)  # keep old labels

    verdicts = [r["verdict"].strip().lower() for r in rows]
    good, bad, unsure = verdicts.count("в"), verdicts.count("л"), verdicts.count("с")
    labelled = good + bad + unsure
    print(f"\nРазметка: {labelled} из {len(rows)} находок размечены ({args.labels})")
    if good + bad:
        print(
            f"Точность (precision): {good} верных из {good + bad} = {good / (good + bad):.0%}; спорных: {unsure}"
        )
    unlabelled = len(rows) - labelled
    if unlabelled:
        print(
            f"Осталось разметить: {unlabelled}. Поставьте в колонке verdict: в — верно, л — ложно, с — спорно."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

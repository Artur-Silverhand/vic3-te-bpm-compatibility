"""Read-only inventory of Clausewitz declaration overlaps; not a load simulator.

Comments and quoted strings are lexed separately. INJECT/REPLACE selectors are
kept as operations on the same entity. Results describe candidates for review,
not proven runtime conflicts. No external dependencies or source mutations.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


TOKEN = re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|[{}]|[=<>!?]+|[^\s{}=<>!?#"]+')
OPERATIONS = {"INJECT", "REPLACE", "TRY_INJECT", "TRY_REPLACE", "INJECT_OR_CREATE", "REPLACE_OR_CREATE"}
ROOTS = {
    "timeline": Path(r"D:\SteamLibrary\steamapps\workshop\content\529340\3721261891"),
    "bpm": Path(r"D:\SteamLibrary\steamapps\workshop\content\529340\2932134122"),
    "utopia": Path(r"D:\SteamLibrary\steamapps\workshop\content\529340\3535929411"),
    "game": Path(r"D:\SteamLibrary\steamapps\common\Victoria 3\game"),
}


def declarations(text: str, relative: str) -> tuple[list[dict], list[str]]:
    tokens = [(m.group(), m.start()) for m in TOKEN.finditer(text) if not m.group().startswith("#")]
    newlines = [m.start() for m in re.finditer("\n", text)]
    records, issues = [], []
    index = 0
    while index + 2 < len(tokens):
        name, offset = tokens[index]
        if tokens[index + 1][0] != "=" or tokens[index + 2][0] != "{":
            index += 1
            continue
        start = index
        depth, index = 1, index + 3
        fields = []
        while index < len(tokens) and depth:
            token, position = tokens[index]
            if depth == 1 and index + 1 < len(tokens) and tokens[index + 1][0] == "=":
                fields.append({"key": token, "line": bisect_right(newlines, position) + 1})
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
            index += 1
        if depth:
            issues.append(f"Unclosed block at {relative}:{bisect_right(newlines, offset) + 1}")
        operation = "DEFINE"
        if ":" in name and name.split(":", 1)[0] in OPERATIONS:
            operation, name = name.split(":", 1)
        parts = relative.split("/")
        category = "/".join(parts[:2])
        if parts[:2] == ["common", "technology"]:
            category = "/".join(parts[:3])
        records.append({
            "key": name,
            "operation": operation,
            "path": relative,
            "line": bisect_right(newlines, offset) + 1,
            "category": category,
            "fields": fields,
            "tokens": index - start,
            "semantic_sha256": hashlib.sha256(" ".join(t[0] for t in tokens[start:index]).encode()).hexdigest(),
        })
    return records, issues


def inventory(label: str, root: Path) -> dict:
    files, records, issues = {}, [], []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part.startswith(".") for part in path.relative_to(root).parts) and not relative.startswith(".metadata/"):
            continue
        if relative.startswith("archive/"):
            continue
        files[relative] = {"bytes": path.stat().st_size}
        if relative.startswith(("common/", "events/", "gui/", "map_data/", ".metadata/")):
            data = path.read_bytes()
            files[relative]["sha256"] = hashlib.sha256(data).hexdigest()
            if relative.startswith("common/") and path.suffix == ".txt":
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    issues.append(f"Non-UTF-8 file: {relative}")
                    continue
                found, problems = declarations(text, relative)
                records.extend(found)
                issues.extend(problems)
    categories = Counter(record["category"] for record in records)
    return {"root": str(root.resolve()), "files": files, "declarations": records,
            "category_counts": dict(sorted(categories.items())), "parse_issues": issues}


def overlap(left: dict, right: dict) -> dict:
    left_by_key, right_by_key = defaultdict(list), defaultdict(list)
    for dataset, target in ((left, left_by_key), (right, right_by_key)):
        for record in dataset["declarations"]:
            target[(record["category"], record["key"])].append(record)
    shared = []
    for category, key in sorted(left_by_key.keys() & right_by_key.keys()):
        shared.append({"category": category, "key": key,
                       "left": left_by_key[(category, key)], "right": right_by_key[(category, key)]})
    paths = sorted(left["files"].keys() & right["files"].keys())
    return {"shared_paths": paths, "shared_entities": shared,
            "shared_entity_categories": dict(sorted(Counter(item["category"] for item in shared).items()))}


def gui_symbols(root: Path) -> list[dict]:
    """Approximate named GUI type index, including the nearest types namespace."""
    found = []
    for path in sorted(root.glob("gui/**/*.gui")):
        source = path.read_text(encoding="utf-8-sig")
        namespaces = list(re.finditer(r"(?m)^[ \t]*types[ \t]+(\w+)", source))
        for match in re.finditer(r"(?m)^[ \t]*(type|template)[ \t]+([\w:]+)[ \t]*(?:=|:)", source):
            previous = [namespace for namespace in namespaces if namespace.start() < match.start()]
            found.append({"namespace": previous[-1][1] if previous else "", "key": match[2],
                          "kind": match[1], "path": path.relative_to(root).as_posix(),
                          "line": source.count("\n", 0, match.start()) + 1})
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeline-root", type=Path, default=ROOTS["timeline"])
    parser.add_argument("--bpm-root", type=Path, default=ROOTS["bpm"])
    parser.add_argument("--game-root", type=Path, default=ROOTS["game"])
    parser.add_argument("--utopia-root", type=Path, help="Optional historical comparison, outside the current target pair")
    arguments = parser.parse_args()
    roots = {"timeline": arguments.timeline_root, "bpm": arguments.bpm_root, "game": arguments.game_root}
    if arguments.utopia_root is not None:
        roots["utopia"] = arguments.utopia_root
    data = {"generated_utc": datetime.now(timezone.utc).isoformat(),
            "method": "lexical top-level common/*.txt declarations; selectors normalized; no engine simulation",
            "sources": {label: inventory(label, root) for label, root in roots.items()}}
    data["comparisons"] = {}
    pairs = [("timeline", "bpm"), ("timeline", "game"), ("bpm", "game")]
    if "utopia" in roots:
        pairs.append(("utopia", "bpm"))
    for left, right in pairs:
        data["comparisons"][f"{left}_{right}"] = overlap(data["sources"][left], data["sources"][right])
    new_lawgroups = {record["key"] for record in data["sources"]["timeline"]["declarations"]
                     if record["category"] == "common/law_groups"}
    for label in (name for name in roots if name != "game"):
        source = data["sources"][label]
        source["gui_symbols"] = gui_symbols(Path(source["root"]))
        ideologies = [record for record in source["declarations"] if record["category"] == "common/ideologies"]
        source["ideologies_with_timeline_lawgroup_fields"] = [record["key"] for record in ideologies
            if {field["key"] for field in record["fields"]} & new_lawgroups]
    data["timeline_new_lawgroups"] = sorted(new_lawgroups)
    left_gui, right_gui = defaultdict(list), defaultdict(list)
    for label, target in (("timeline", left_gui), ("bpm", right_gui)):
        for record in data["sources"][label]["gui_symbols"]:
            target[(record["namespace"], record["key"])].append(record)
    data["comparisons"]["timeline_bpm"]["shared_gui_symbols"] = [
        {"namespace": namespace, "key": key, "left": left_gui[(namespace, key)], "right": right_gui[(namespace, key)]}
        for namespace, key in sorted(left_gui.keys() & right_gui.keys())]
    summary = {label: {"files": len(source["files"]), "declarations": len(source["declarations"]),
                       "parse_issues": source["parse_issues"]}
               for label, source in data["sources"].items()}
    for pair, comparison in data["comparisons"].items():
        summary[pair] = {"shared_paths": comparison["shared_paths"] if not pair.endswith("_game") else len(comparison["shared_paths"]),
                         "shared_entities": len(comparison["shared_entities"]),
                         "categories": comparison["shared_entity_categories"]}
    # Keep complete hashes and overlap evidence, without duplicating every
    # game's unrelated declaration tree in a very large research artifact.
    for source in data["sources"].values():
        source["declaration_count"] = len(source.pop("declarations"))
        source["file_counts"] = {
            "total": len(source["files"]),
            "common_txt": sum(path.startswith("common/") and path.endswith(".txt") for path in source["files"]),
            "events_txt": sum(path.startswith("events/") and path.endswith(".txt") for path in source["files"]),
            "gui": sum(path.startswith("gui/") and path.endswith(".gui") for path in source["files"]),
        }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

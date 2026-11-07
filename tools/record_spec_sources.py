"""Record the pinned specification inputs without changing either source mod.

Run after inspect_mod_overlap.py has produced both dated research reports.
Only line endings are normalized for the GitHub/Workshop alignment; this is
not a semantic compatibility check or a deployable-package manifest.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs/research"
SCOPE = (".metadata", "common", "events", "gui")
MODS = {
    "timeline": {
        "repository": "https://github.com/jakeOmega/Vic3TimelineExtended",
        "checkout": ROOT / "sources/upstream/Vic3TimelineExtended",
        "mod_subdirectory": ".",
        "commit": "48a28e73ad06c25d4de02edead2ec976a9e8dd35",
        "workshop_id": "3721261891",
    },
    "bpm": {
        "repository": "https://github.com/Better-Politics-Mod/Better-Politics-Mod-Vic-3",
        "checkout": ROOT / "sources/upstream/Better-Politics-Mod-Vic-3",
        "mod_subdirectory": "better-politics-mod",
        "commit": "d785d399001ceaa87a1153ca7e0fb4ba512d8425",
        "workshop_id": "2932134122",
    },
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repository), *args], encoding="utf-8").strip()


def files_in_scope(root: Path) -> dict[str, Path]:
    return {path.relative_to(root).as_posix(): path for top in SCOPE
            for path in (root / top).rglob("*") if path.is_file()}


def alignment(upstream: Path, workshop: Path) -> dict:
    left, right = files_in_scope(upstream), files_in_scope(workshop)
    changed, exact, line_endings_only = [], 0, 0
    for relative in sorted(left.keys() & right.keys()):
        a, b = left[relative].read_bytes(), right[relative].read_bytes()
        if a == b:
            exact += 1
        elif a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n"):
            line_endings_only += 1
        else:
            changed.append({"path": relative, "github_sha256": sha(a), "workshop_sha256": sha(b),
                            "github_lf_sha256": sha(a.replace(b"\r\n", b"\n")),
                            "workshop_lf_sha256": sha(b.replace(b"\r\n", b"\n"))})
    return {"scope": list(SCOPE), "normalization": "CRLF to LF only; no BOM/comment/whitespace normalization",
            "github_root": str(upstream.resolve()), "workshop_root": str(workshop),
            "exact_files": exact, "line_endings_only_files": line_endings_only,
            "changed_after_normalization": changed,
            "only_github": sorted(left.keys() - right.keys()),
            "only_workshop": sorted(right.keys() - left.keys())}


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    lock = {"schema_version": 1, "specification": "SPEC-002", "specification_version": "0.2",
            "recorded_utc": now, "purpose": "pinned research inputs; not proof of runtime compatibility",
            "primary_distribution": "GitHub commits; Workshop is a separate candidate profile",
            "mods": {}, "research_reports": {}}
    align = {"recorded_utc": now, "sources": {}}
    for label, config in MODS.items():
        checkout = config["checkout"]
        commit = git(checkout, "rev-parse", "HEAD")
        if commit != config["commit"]:
            raise RuntimeError(f"{label}: checkout differs from the specification's pinned commit")
        mod_root = checkout / config["mod_subdirectory"]
        workshop = Path(r"D:\SteamLibrary\steamapps\workshop\content\529340") / config["workshop_id"]
        metadata_path = mod_root / ".metadata/metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        compare = alignment(mod_root, workshop)
        align["sources"][label] = compare
        lock["mods"][label] = {
            "repository": config["repository"], "commit": commit,
            "tree": git(checkout, "rev-parse", "HEAD^{tree}"),
            "commit_time": git(checkout, "show", "-s", "--format=%cI", "HEAD"),
            "checkout": str(checkout), "mod_subdirectory": config["mod_subdirectory"],
            "mod_root": str(mod_root.resolve()),
            "sparse_checkout": git(checkout, "config", "--get", "core.sparseCheckout") == "true",
            "metadata": metadata, "metadata_sha256": sha(metadata_path.read_bytes()),
            "workshop_id": config["workshop_id"], "workshop_root": str(workshop),
            "workshop_metadata": json.loads((workshop / ".metadata/metadata.json").read_text(encoding="utf-8-sig")),
            "workshop_changed_script_files_after_lf_normalization": len(compare["changed_after_normalization"]),
        }
    game = Path(r"D:\SteamLibrary\steamapps\common\Victoria 3")
    settings_path = game / "launcher/launcher-settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    manifest = Path(r"D:\SteamLibrary\steamapps\appmanifest_529340.acf").read_text(encoding="utf-8-sig")
    lock["game"] = {"root": str(game), "version": settings["rawVersion"],
                    "display_version": settings["version"],
                    "steam_build_id": re.search(r'"buildid"\s+"([^"]+)"', manifest)[1],
                    "launcher_settings_sha256": sha(settings_path.read_bytes())}
    te = Path(lock["mods"]["timeline"]["mod_root"])
    rules = (te / "common/game_rules/extra_game_rules.txt").read_text(encoding="utf-8-sig")
    lock["default_game_rules"] = dict(re.findall(
        r"(?m)^([A-Za-z_0-9]+)[ \t]*=[ \t]*\{\s*default[ \t]*=[ \t]*([A-Za-z_0-9]+)", rules))
    lock["validation_status"] = {
        "full_deployable_packages_prepared": (ROOT/'docs/validation/prepared-profile.json').exists(),
        "dlc_profile_verified": False, "game_runs_performed": False,
        "patch_implemented": (ROOT/'patch/.metadata/metadata.json').exists(),
        "latest_status": "STATUS.md",
    }
    lock["coverage_limitations"] = [
        "Git commits identify complete upstream trees; checkout materialization is recorded per source.",
        "Alignment covers metadata/common/events/gui, not graphics, localization or map_data.",
        "Research hashes cover metadata and selected runtime script categories; they are not full installation hashes.",
        "Lexical overlaps and author load-order models do not establish engine behavior.",
    ]
    for profile in ("github", "workshop"):
        path = RESEARCH / f"2026-11-07-{profile}-overlap.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        lock["research_reports"][profile] = {"path": str(path), "sha256": sha(path.read_bytes()),
            "generated_utc": report["generated_utc"],
            "shared_categories": report["comparisons"]["timeline_bpm"]["shared_entity_categories"],
            "timeline_additional_lawgroups": len(report["timeline_new_lawgroups"])}
    alignment_path = RESEARCH / "2026-11-07-source-alignment.json"
    alignment_path.write_text(json.dumps(align, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lock["alignment_report"] = {"path": str(alignment_path), "sha256": sha(alignment_path.read_bytes())}
    (ROOT / "sources.lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": ["sources.lock.json", str(alignment_path.relative_to(ROOT))],
                      "rules_recorded": len(lock["default_game_rules"]),
                      "changed_files": {label: len(value["changed_after_normalization"])
                                        for label, value in align["sources"].items()}}, ensure_ascii=True))


if __name__ == "__main__":
    main()

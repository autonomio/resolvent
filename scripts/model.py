"""Small, deterministic integrity layer for Autonomio Resolvent.

This module checks structure and traceability, not whether an assertion is true.
Source text is never executed; no network calls or model-provider keys are used.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

DATA_ROOTS = ("claims", "evidence", "sources", "graph", "questions", "input-artefacts", "briefs", "maintenance")
CANONICAL_ROOTS = ("claims", "evidence", "sources", "graph", "questions")
PREFIXES = {"claims": "C", "evidence": "E", "sources": "S", "graph": "R", "questions": "Q"}
MAX_FILE_BYTES = 2 * 1024 * 1024
ID = re.compile(r"^(?:C|E|S|R|Q|RUN|BR|BC|M)-[0-9a-f]{32}$")


class Invalid(ValueError):
    """A contribution or world model violates an executable rule."""


class StrictLoader(yaml.SafeLoader):
    pass


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise Invalid("Mapping keys must be strings.")
        if key in result:
            raise Invalid(f"Duplicate mapping key: {key}")
        result[key] = value
    return result


def construct_mapping(loader: StrictLoader, node: yaml.MappingNode) -> dict:
    return unique_pairs([(loader.construct_object(k), loader.construct_object(v)) for k, v in node.value])


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
# Preserve dates as text; the schemas validate explicit date/time strings.
StrictLoader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in values if tag != "tag:yaml.org,2002:timestamp"]
    for k, values in StrictLoader.yaml_implicit_resolvers.items()
}


def read_data(path: Path) -> dict:
    if path.is_symlink():
        raise Invalid(f"Symlinks are not accepted: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise Invalid(f"File exceeds the 2 MiB contribution limit: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        if path.suffix == ".json":
            value = json.loads(raw, object_pairs_hook=unique_pairs,
                               parse_constant=lambda x: (_ for _ in ()).throw(Invalid(f"Non-finite number: {x}")))
        else:
            # Reject YAML aliases/anchors to keep data finite and reviewable.
            if any(isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)) for t in yaml.scan(raw)):
                raise Invalid(f"YAML anchors and aliases are not supported: {path}")
            value = yaml.load(raw, Loader=StrictLoader)
    except (json.JSONDecodeError, yaml.YAMLError, UnicodeError) as exc:
        raise Invalid(f"Cannot parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Invalid(f"Expected an object in {path}")
    return value


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def safe_relative(path: str) -> bool:
    p = Path(path)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in path and bool(p.parts)


def load_state(root: Path) -> dict[str, dict]:
    state: dict[str, dict] = {}
    for name in DATA_ROOTS:
        folder = root / name
        if folder.is_symlink():
            raise Invalid(f"Data directories cannot be symlinks: {name}")
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise Invalid(f"Symlink in data: {path.relative_to(root)}")
            if not path.is_file() or path.name in (".gitkeep", "README.md"):
                continue
            if path.suffix not in (".yaml", ".json"):
                raise Invalid(f"Unsupported data file: {path.relative_to(root)}")
            state[path.relative_to(root).as_posix()] = read_data(path)
    return state


def family(path: str) -> str:
    if path.startswith("input-artefacts/"):
        return "submission"
    if path.startswith("briefs/closed/"):
        return "closure"
    if path.startswith("briefs/open/done/"):
        return "brief"
    if path.startswith("briefs/ready/"):
        return "result"
    first = path.split("/")[0]
    if first in CANONICAL_ROOTS or first == "maintenance":
        return first
    raise Invalid(f"Unexpected data path: {path}")


def indexes(state: dict[str, dict]) -> dict[str, dict[str, dict]]:
    result: dict[str, dict[str, dict]] = {}
    for path, record in state.items():
        kind = family(path)
        key = record.get("id", "")
        by_kind = result.setdefault(kind, {})
        if key in by_kind:
            raise Invalid(f"Duplicate {kind} ID: {key}")
        by_kind[key] = record
    return result


def fail(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def no_duplicates(values: list[Any], name: str) -> None:
    fail(len(values) == len(set(values)), f"Duplicate entries in {name}")


def acyclic(edges: list[tuple[str, str]], description: str) -> None:
    graph: dict[str, list[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    visiting: set[str] = set()
    visited: set[str] = set()
    # Iterative traversal avoids recursion depth failures in large models.
    for start in graph:
        stack = [(start, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                visiting.remove(node)
                visited.add(node)
                continue
            if node in visited:
                continue
            fail(node not in visiting, f"Circular {description} at {node}")
            visiting.add(node)
            stack.append((node, True))
            stack.extend((target, False) for target in graph.get(node, []))


def validate_submission(p: dict, existing: dict[str, dict]) -> None:
    local: dict[str, set[str]] = {}
    for group in ("sources", "evidence", "claims", "connectors", "questions"):
        ids = [x["id"] for x in p[group]]
        no_duplicates(ids, f"{p['id']}.{group}")
        local[group] = set(ids)
    sources = {s["id"]: s for s in p["sources"]}
    evidence = {e["id"]: e for e in p["evidence"]}
    known_claims = local["claims"] | set(existing)
    for e in p["evidence"]:
        fail(set(e["source_ids"]) <= local["sources"], f"{e['id']}: unresolved source")
        fail(set(e["premise_claim_ids"]) <= known_claims, f"{e['id']}: unresolved premise claim")
        if e["independent"]:
            fail(e["kind"] == "external", f"{e['id']}: only external evidence can be independent")
            for sid in e["source_ids"]:
                s = sources[sid]
                fail(s["kind"] in ("publication", "web") and s["access"] == "inspected" and bool(s["uri"]),
                     f"{e['id']}: independent evidence needs an inspected, addressable external source")
    for c in p["claims"]:
        no_duplicates(c["evidence_ids"], c["id"] + ".evidence_ids")
        fail(set(c["evidence_ids"]) <= local["evidence"], f"{c['id']}: unresolved evidence")
        if c["uncertainty"] == "low":
            fail(any(evidence[e]["independent"] for e in c["evidence_ids"]),
                 f"{c['id']}: low uncertainty requires independent inspected evidence in the contribution")
    for r in p["connectors"]:
        fail(r["from"] in known_claims and r["to"] in known_claims, f"{r['id']}: unknown connector endpoint")
        fail(r["from"] != r["to"], f"{r['id']}: self-connector")
        fail(set(r["evidence_ids"]) <= local["evidence"], f"{r['id']}: unresolved connector evidence")
    for q in p["questions"]:
        fail(set(q["claim_ids"]) <= known_claims, f"{q['id']}: unknown question claim")
    if not p["claims"]:
        fail(bool(p["handoff"]["no_claims_reason"]), "A zero-claim contribution needs an explicit reason")
    route = p["input_method"]
    meta = p["method_metadata"]
    if route == "research":
        fail(p["brief"] is not None, "Research requires a brief")
        fail(p["origin"]["mode"] == "live" and p["brief"]["created_before_research"] is True,
             "Retrospective capture uses conversation/source_material, not a fabricated prospective brief")
        expected = [x["id"] for x in p["brief"]["acceptance_criteria"]]
        actual = [x["criterion_id"] for x in p["result"]["acceptance_outcomes"]]
        no_duplicates(expected, "acceptance criteria")
        no_duplicates(actual, "acceptance outcomes")
        fail(set(expected) == set(actual), "Every acceptance criterion needs an explicit outcome")
    if route == "conversation":
        fail(p["origin"]["mode"] == "retrospective", "Conversation capture must be retrospective")
        fail(p["origin"]["coverage"] in ("complete", "partial"), "Record visible chat coverage")
        fail(meta.get("new_research_performed") is False, "Chat capture must explicitly prohibit new research")
        fail(p["brief"] is None, "Do not fabricate a pre-research brief for chat capture")
        if p["origin"]["coverage"] == "partial":
            fail(bool(p["origin"]["limitations"]), "Partial chat capture requires an explicit limitation")
    if route == "simulation":
        for key in ("spec_id", "spec_version", "run_id", "parameters"):
            fail(key in meta and meta[key] is not None, f"Simulation requires {key}")
        fail(isinstance(meta["parameters"], dict), "Simulation parameters must be an object")
    if route == "interview":
        fail(bool(meta.get("participants")) and bool(meta.get("interview_date")), "Interview needs participants and date")
    if route == "intra_model":
        fail(bool(meta.get("source_claim_ids")) and bool(meta.get("source_commit")), "Intra-model input requires source claims and commit")
        fail(set(meta["source_claim_ids"]) <= set(existing), "Intra-model source claims must already exist")
    if route == "liminal_research":
        fail(bool(meta.get("topic")) and bool(meta.get("perspective")) and bool(meta.get("stage_outputs")), "Liminal input requires topic, perspective, and stage outputs")
        fail(meta.get("external_search_performed") is False and meta.get("world_model_read_during_generation") is False,
             "Liminal generation forbids external search and world-model reads")
        fail(all(c["class"] == "assumption" and c["uncertainty"] == "high" for c in p["claims"]),
             "Liminal claims are capped at assumption/high uncertainty")


def validate_state(state: dict[str, dict], policy_root: Path, require_closure: bool = False) -> dict[str, int]:
    schemas: dict[str, Draft202012Validator] = {}
    for path, record in state.items():
        kind = family(path)
        if kind in ("brief", "result"):
            fail(set(record) == {"id", "submission_id", kind}, f"Invalid {kind} archive: {path}")
        else:
            if kind not in schemas:
                schema = read_data(policy_root / "docs/schemas" / f"{kind}.schema.json")
                Draft202012Validator.check_schema(schema)
                schemas[kind] = Draft202012Validator(schema, format_checker=FormatChecker())
            errors = sorted(schemas[kind].iter_errors(record), key=lambda e: str(list(e.path)))
            if errors:
                err = errors[0]
                raise Invalid(f"{path} {list(err.path)}: {err.message}")
        fail(record.get("id") == Path(path).stem, f"ID does not match filename: {path}")
        # Exactly one record per file, at a fixed location.
        expected = {
            "submission": f"input-artefacts/{record['id']}.json",
            "closure": f"briefs/closed/{record['id']}.yaml",
            "brief": f"briefs/open/done/{record['id']}.yaml",
            "result": f"briefs/ready/{record['id']}.yaml",
        }.get(kind, f"{kind}/{record['id']}.yaml")
        fail(path == expected, f"Unexpected record location: {path}; expected {expected}")
    idx = indexes(state)
    claims, evidence, sources, graph = [idx.get(n, {}) for n in ("claims", "evidence", "sources", "graph")]
    for p in idx.get("submission", {}).values():
        validate_submission(p, claims)
        parent = p["parent_run_id"]
        fail(parent is None or parent in idx.get("submission", {}), f"{p['id']}: unknown parent contribution")
        fail(parent != p["id"], "A contribution cannot be its own parent")
    acyclic([(p['id'], p['parent_run_id']) for p in idx.get('submission', {}).values() if p['parent_run_id']], 'contribution lineage')
    premise_edges = []
    for c in claims.values():
        fail(set(c["evidence_ids"]) <= set(evidence), f"{c['id']}: unresolved canonical evidence")
        no_duplicates(c["evidence_ids"], c["id"] + ".evidence_ids")
        for eid in c["evidence_ids"]:
            fail(c["id"] in evidence[eid]["claim_ids"], f"Missing evidence backlink {eid} -> {c['id']}")
            premise_edges.extend((c["id"], premise) for premise in evidence[eid]["premise_claim_ids"])
        if c["uncertainty"] == "low":
            fail(any(evidence[e]["independent"] for e in c["evidence_ids"]), f"{c['id']}: low uncertainty lacks independent evidence")
    for e in evidence.values():
        fail(set(e["source_ids"]) <= set(sources), f"{e['id']}: unresolved source")
        fail(set(e["premise_claim_ids"]) <= set(claims), f"{e['id']}: unresolved derivation premise")
        fail(set(e["claim_ids"]) <= set(claims), f"{e['id']}: unresolved claim backlink")
        for cid in e["claim_ids"]:
            fail(e["id"] in claims[cid]["evidence_ids"], f"Missing claim backlink {cid} -> {e['id']}")
        if e["independent"]:
            fail(e["kind"] == "external", f"{e['id']}: non-external evidence cannot be independent")
            fail(all(sources[s]["kind"] in ("publication", "web") and sources[s]["access"] == "inspected" and sources[s]["uri"] for s in e["source_ids"]), f"{e['id']}: independent evidence has an unverified source")
    acyclic(premise_edges, "evidential self-validation")
    for r in graph.values():
        fail(r["from"] in claims and r["to"] in claims, f"{r['id']}: unresolved endpoint")
        fail(r["from"] != r["to"], f"{r['id']}: self-connector")
        fail(set(r["evidence_ids"]) <= set(evidence), f"{r['id']}: unresolved evidence")
    acyclic([(r["from"], r["to"]) for r in graph.values() if r["type"] == "dependency" and r["state"] == "active"], "dependency")
    for q in idx.get("questions", {}).values():
        fail(set(q["claim_ids"]) <= set(claims), f"{q['id']}: unresolved question claim")
    submissions = idx.get("submission", {})
    closed = set()
    for c in idx.get("closure", {}).values():
        sid = c["submission_id"]
        fail(sid in submissions, f"{c['id']}: missing submission")
        p = submissions[sid]
        fail(c["id"] == sid.replace("RUN-", "BC-"), "Closure ID must match run")
        fail(c["input_method"] == p["input_method"], "Closure route differs from submission")
        fail(c["submission_sha256"] == digest(p), f"{sid}: contribution changed after admission; closure is stale")
        candidate_ids = [d["candidate_id"] for d in c["claim_dispositions"]]
        no_duplicates(candidate_ids, "closure dispositions")
        fail(set(candidate_ids) == {x["id"] for x in p["claims"]}, f"{sid}: every candidate needs a disposition")
        for d in c["claim_dispositions"]:
            admitted = d["disposition"] in ("created", "merged")
            fail((d["claim_id"] in claims) if admitted else d["claim_id"] is None, f"{sid}: invalid disposition target")
        admitted_ids = {d["candidate_id"] for d in c["claim_dispositions"] if d["claim_id"] is not None}
        reviewed_ids = [r["candidate_id"] for r in c["connection_review"]]
        no_duplicates(reviewed_ids, "connection review")
        fail(set(reviewed_ids) == admitted_ids, f"{sid}: every admitted candidate needs a bounded connection assessment")
        for assessment in c["connection_review"]:
            fail(set(assessment["considered_claim_ids"]) <= set(claims), "Connection assessment references unknown claims")
            if assessment["outcome"] == "deferred":
                fail(bool(c["follow_up_gaps"]), "Deferred connection work must be recorded for maintenance")
        expected_counts = {f"{n}_claims": sum(d["disposition"] == n for d in c["claim_dispositions"]) for n in ("created", "merged", "rejected", "deferred")}
        expected_counts["created_connectors"] = len(c["created"]["graph"])
        fail(c["counts"] == expected_counts, f"{sid}: closure counts disagree with dispositions")
        touched = []
        for mode in ("created", "updated"):
            for group, paths in c[mode].items():
                for path in paths:
                    fail(safe_relative(path) and path in state and path.startswith(group + "/"), f"{sid}: invalid {mode} path {path}")
                touched.extend(paths)
        fail(set(touched) == set(c["touched_files"]), f"{sid}: closure touched-files mismatch")
        if p["input_method"] == "research":
            bid = sid.replace("RUN-", "BR-")
            for kind, payload in (("brief", p["brief"]), ("result", p["result"])):
                archive = idx.get(kind, {}).get(bid)
                fail(archive is not None and archive["submission_id"] == sid and archive[kind] == payload,
                     f"{sid}: missing or inconsistent {kind} artifact")
        closed.add(sid)
    if require_closure:
        fail(set(submissions) <= closed, "Awaiting admission agent: contributions need a materialized closure before merge: " + ", ".join(sorted(set(submissions)-closed)))
    for m in idx.get("maintenance", {}).values():
        fail(set(m["claim_ids"]) <= set(claims), f"{m['id']}: unresolved maintenance claim")
        fail(set(m["reviewed_claim_ids"]) <= set(m["claim_ids"]), f"{m['id']}: reviewed claims outside workset")
        fail(all(safe_relative(p) and p in state and p.split('/')[0] in CANONICAL_ROOTS for p in m["touched_files"]), "Invalid maintenance touched file")
        if m["status"] == "completed":
            fail(set(m["reviewed_claim_ids"]) == set(m["claim_ids"]) or bool(m["deferred"]), "Incomplete maintenance coverage needs explicit deferrals")
            fail(bool(m["touched_files"]) or bool(m["no_change_reason"]), "No-change maintenance requires an explanation")
            fail(bool(m["findings"]) or bool(m["no_change_reason"]), "Maintenance needs findings or no-change reason")
        elif require_closure:
            raise Invalid(f"Awaiting maintenance agent: {m['id']} is pending")
    historical_coverage = set()
    for record in idx.get("closure", {}).values():
        historical_coverage.update(record["touched_files"])
    for record in idx.get("maintenance", {}).values():
        if record["status"] == "completed":
            historical_coverage.update(record["touched_files"])
    canonical_paths = {p for p in state if family(p) in (*CANONICAL_ROOTS, "brief", "result")}
    fail(canonical_paths <= historical_coverage, "Canonical records lack an admission/maintenance provenance record: " + ", ".join(sorted(canonical_paths-historical_coverage)))
    return {name: len(records) for name, records in idx.items()}


def tracked_files(root: Path) -> dict[str, bytes]:
    excluded = {".git", ".venv", "__pycache__", ".resolvent", ".pytest_cache"}
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in excluded for part in rel.parts):
            continue
        if path.is_symlink():
            raise Invalid(f"Repository symlinks are not supported: {rel}")
        if path.is_file():
            files[rel.as_posix()] = path.read_bytes()
    return files


def validate_delta(root: Path, base: Path, current: dict[str, dict]) -> None:
    old = load_state(base)
    before, after = tracked_files(base), tracked_files(root)
    changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
    data_changes = {p for p in changed if p in current or p in old}
    governance_changes = changed - data_changes
    fail(not (data_changes and governance_changes), "Separate governance/code changes from model-data PRs: " + ", ".join(sorted(governance_changes)))
    fail(not (set(old) - set(current)), "Do not delete model history; retire records instead")
    for path in old:
        if family(path) in ("submission", "closure", "brief", "result", "maintenance"):
            fail(old[path] == current.get(path), f"Merged provenance is immutable; use a new run: {path}")
    actual = {p for p in data_changes if family(p) in (*CANONICAL_ROOTS, "brief", "result")}
    covered: set[str] = set()
    for path in data_changes:
        if path not in current:
            continue
        record = current[path]
        if family(path) == "closure" or (family(path) == "maintenance" and record["status"] == "completed"):
            covered.update(record["touched_files"])
    fail(actual == covered, f"Materialized delta and integration records differ. Unrecorded: {sorted(actual-covered)}; not changed: {sorted(covered-actual)}")

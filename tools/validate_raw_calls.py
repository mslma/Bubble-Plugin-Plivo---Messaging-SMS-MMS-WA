#!/usr/bin/env python3
"""Read-only structural validator for this Bubble plugin mirror.

This repo is written by Bubble's GitHub sync, not by hand. The checks here exist
to catch two classes of problem:

  * drift introduced by a hand edit (wrong serialization, a dangling type
    reference, a colliding parameter ID), and
  * pre-existing schema defects that Bubble's editor will happily emit
    (a `number` field whose sample is a string, two calls describing the same
    Plivo object with divergent types).

Nothing here writes, network-calls, or needs credentials. Run it before and
after any change to `api/raw_calls.json`.

    python3 tools/validate_raw_calls.py            # errors fail, warnings print
    python3 tools/validate_raw_calls.py --strict   # warnings fail too

Exit code 0 = clean, 1 = failures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Every file Bubble's sync owns. Each must round-trip byte-exact (see check_serialization).
BUBBLE_OWNED = ["api/raw_calls.json", "meta_data.json", "shared_tech_params.json"]

# `auth_id` is deliberately the same parameter ID across all three calls -- it is a
# plugin-level setting, not a per-call field. Whitelisted so that any *other* cross-call
# ID reuse (which would be a genuine collision) still gets reported.
SHARED_PARAM_IDS = {"AAV"}

URL_PLACEHOLDER = re.compile(r"\[([^\]]+)\]")
RET_VALUE = re.compile(r"^api\.(?P<plugin_id>[^.]+)\.plugin_api\.(?P<call_id>.+)$")
# e.g. list.api.<plugin_id>.plugin_api.AAc.objects
TYPE_REF = re.compile(r"^(?:list\.)?api\.(?P<plugin_id>[^.]+)\.plugin_api\.(?P<type_name>.+)$")
ISO_8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T")


class Report:
    """Collects findings so one run surfaces every problem, not just the first."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def load_calls() -> dict:
    raw = (REPO / "api/raw_calls.json").read_text(encoding="utf-8")
    return json.loads(raw)


def parsed_types(call: dict) -> dict:
    """`types` is a JSON document stored as an escaped string inside the JSON. Yes, really."""
    return json.loads(call["types"]) if "types" in call else {}


# --------------------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------------------

def check_serialization(report: Report) -> None:
    """Bubble emits json.dumps(obj, sort_keys=True, indent=4, ensure_ascii=False), no trailing newline.

    This is the canary. A hand edit that does not reproduce it byte-for-byte turns the
    next Bubble->GitHub push into a whole-file diff, which is exactly the "both sides
    modified" state where Bubble's copy wins and your change is lost.
    """
    for rel in BUBBLE_OWNED:
        path = REPO / rel
        if not path.exists():
            report.error(f"{rel}: missing")
            continue
        raw = path.read_text(encoding="utf-8")
        expected = json.dumps(json.loads(raw), sort_keys=True, indent=4, ensure_ascii=False)
        if raw != expected:
            detail = "trailing newline" if raw.rstrip("\n") == expected else "key order / indentation"
            report.error(f"{rel}: not in Bubble's canonical serialization ({detail})")


def check_types_parse(spec: dict, report: Report) -> None:
    for call_id, call in spec["calls"].items():
        if "types" not in call:
            continue
        try:
            json.loads(call["types"])
        except json.JSONDecodeError as exc:
            report.error(f"{call_id}: `types` is not valid JSON ({exc})")


def check_ret_values(spec: dict, report: Report) -> None:
    """Every call's ret_value must be api.<plugin_id>.plugin_api.<its own id>, one plugin ID throughout."""
    plugin_ids = set()
    for call_id, call in spec["calls"].items():
        ret = call.get("ret_value")
        if ret is None:
            report.warn(f"{call_id}: no `ret_value`")
            continue
        match = RET_VALUE.match(ret)
        if not match:
            report.error(f"{call_id}: malformed `ret_value` {ret!r}")
            continue
        plugin_ids.add(match["plugin_id"])
        if match["call_id"] != call_id:
            report.error(
                f"{call_id}: `ret_value` points at call {match['call_id']!r}, not itself"
            )
    if len(plugin_ids) > 1:
        report.error(f"calls disagree on the plugin ID: {sorted(plugin_ids)}")


def check_type_references(spec: dict, report: Report) -> None:
    """A field whose ret_btype names another type must resolve within the same call's `types`."""
    for call_id, call in spec["calls"].items():
        types = parsed_types(call)
        for type_name, type_def in types.items():
            for field_name, field in type_def.get("fields", {}).items():
                bt = field.get("ret_btype", "")
                if "plugin_api." not in bt:
                    continue
                match = TYPE_REF.match(bt)
                if not match:
                    report.error(f"{call_id} {type_name}.{field_name}: unparseable ret_btype {bt!r}")
                    continue
                # Nested types are referenced as `...plugin_api.AAc.objects` but keyed
                # in `types` as `plugin_api.AAc.objects` -- re-add the prefix to look up.
                target = f"plugin_api.{match['type_name']}"
                if target not in types:
                    report.error(
                        f"{call_id} {type_name}.{field_name}: ret_btype references "
                        f"{target!r}, which is not defined in this call's `types`"
                    )


def check_url_placeholders(spec: dict, report: Report) -> None:
    """`[foo]` in the URL and url_params[*].key must be a bijection, or requests hit a malformed path."""
    for call_id, call in spec["calls"].items():
        in_url = set(URL_PLACEHOLDER.findall(call.get("url", "")))
        declared = {p["key"] for p in call.get("url_params", {}).values() if "key" in p}
        for missing in sorted(in_url - declared):
            report.error(f"{call_id}: URL uses [{missing}] but no url_param declares it")
        for unused in sorted(declared - in_url):
            report.error(f"{call_id}: url_param {unused!r} never appears in the URL")


def check_param_ids(spec: dict, report: Report) -> None:
    """IDs must be unique within a call, and (outside the whitelist) across calls."""
    seen: dict[str, list[str]] = {}
    for call_id, call in spec["calls"].items():
        within: dict[str, list[str]] = {}
        for bucket in ("params", "url_params"):
            for pid, param in call.get(bucket, {}).items():
                within.setdefault(pid, []).append(f"{bucket}.{param.get('key', '?')}")
                seen.setdefault(pid, []).append(call_id)
        for pid, uses in within.items():
            if len(uses) > 1:
                report.error(f"{call_id}: parameter ID {pid!r} used twice ({', '.join(uses)})")
    for pid, calls in seen.items():
        if len(calls) > 1 and pid not in SHARED_PARAM_IDS:
            report.warn(f"parameter ID {pid!r} is reused across calls {calls} (collision?)")


def check_sample_types(spec: dict, report: Report) -> None:
    """A ret_btype that disagrees with its own sample_value is a coercion bug waiting to happen.

    `number` with a string sample is only a real problem for identifiers (mcc/mnc), where
    coercion strips leading zeros -- mnc "01" becomes 1. For decimal money fields it is
    harmless and desirable. See docs/KNOWN-ISSUES.md.
    """
    for call_id, call in spec["calls"].items():
        for type_name, type_def in parsed_types(call).items():
            for field_name, field in type_def.get("fields", {}).items():
                bt, sample = field.get("ret_btype"), field.get("sample_value")
                if sample is None:
                    continue
                if bt == "number" and isinstance(sample, str):
                    report.warn(f"{call_id} {type_name}.{field_name}: `number` with string sample {sample!r}")
                elif bt == "boolean" and isinstance(sample, str):
                    report.warn(f"{call_id} {type_name}.{field_name}: `boolean` with string sample {sample!r}")
                elif bt == "date" and isinstance(sample, str) and not ISO_8601.match(sample):
                    report.warn(f"{call_id} {type_name}.{field_name}: `date` with non-ISO-8601 sample {sample!r}")


def check_schema_parity(spec: dict, report: Report) -> None:
    """`List all messages`.objects and `Retrieve a Message` describe the same Plivo Message object.

    They currently agree on every shared field's type. This check exists so that a type fix
    applied to only one of them gets caught.
    """
    pairs = [("AAc", "plugin_api.AAc.objects", "AAe", "plugin_api.AAe")]
    for a_call, a_type, b_call, b_type in pairs:
        if a_call not in spec["calls"] or b_call not in spec["calls"]:
            continue
        a = parsed_types(spec["calls"][a_call]).get(a_type, {}).get("fields", {})
        b = parsed_types(spec["calls"][b_call]).get(b_type, {}).get("fields", {})
        if not a or not b:
            continue
        for field in sorted(set(a) & set(b)):
            if a[field]["ret_btype"] != b[field]["ret_btype"]:
                report.error(
                    f"schema drift on {field}: {a_type} says {a[field]['ret_btype']!r}, "
                    f"{b_type} says {b[field]['ret_btype']!r}"
                )


def check_sanity(spec: dict, report: Report) -> None:
    for call_id, call in spec["calls"].items():
        if call.get("publish_as") not in ("action", "data"):
            report.error(f"{call_id}: unexpected publish_as {call.get('publish_as')!r}")
        method = call.get("method", "")
        if method != method.lower():
            report.error(f"{call_id}: method {method!r} should be lowercase")
        url = call.get("url", "")
        if not url.startswith("https://"):
            report.error(f"{call_id}: URL is not https ({url!r})")
        # Plivo's REST API is Tastypie-style and canonically uses trailing slashes on
        # resource URIs; without one it 301-redirects, costing a round-trip.
        if not url.endswith("/"):
            report.warn(f"{call_id}: URL has no trailing slash ({url!r}) -- Plivo will 301-redirect")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    report = Report()
    check_serialization(report)

    spec = load_calls()
    for check in (
        check_types_parse,
        check_ret_values,
        check_type_references,
        check_url_placeholders,
        check_param_ids,
        check_sample_types,
        check_schema_parity,
        check_sanity,
    ):
        check(spec, report)

    for msg in report.errors:
        print(f"ERROR   {msg}")
    for msg in report.warnings:
        print(f"warning {msg}")

    failed = bool(report.errors) or (args.strict and bool(report.warnings))
    print(
        f"\n{len(spec['calls'])} calls checked -- "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

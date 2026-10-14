"""Corrections for known errors in the upstream Talos config JSON schema.

Each fix only applies while the upstream schema still has the error, so it becomes a
no-op once Talos corrects it.
"""

from __future__ import annotations

import copy

# Keys describing a property rather than its value type; they stay on the property.
_ANNOTATIONS = ("title", "description", "markdownDescription", "x-intellij-html-description")

# (definition, property): reason. The Go fields are slices of PEM certificates, but the
# schema generator emits a single object.
OBJECT_SHOULD_BE_LIST = {
    ("v1alpha1.MachineConfig", "acceptedCAs"): "MachineAcceptedCAs is []*x509.PEMEncodedCertificate",
    ("v1alpha1.ClusterConfig", "acceptedCAs"): "ClusterAcceptedCAs is []*x509.PEMEncodedCertificate",
}


def apply_fixes(schema: dict) -> tuple[dict, list[str]]:
    """Return a corrected copy of the schema and a description of each applied fix."""
    schema = copy.deepcopy(schema)
    defs = schema.get("$defs") or schema.get("definitions") or {}
    applied: list[str] = []
    for (def_name, prop), reason in OBJECT_SHOULD_BE_LIST.items():
        node = (defs.get(def_name) or {}).get("properties", {}).get(prop)
        if not node or node.get("type") != "object":
            continue
        item = {k: v for k, v in node.items() if k not in _ANNOTATIONS}
        defs[def_name]["properties"][prop] = {
            **{k: v for k, v in node.items() if k in _ANNOTATIONS},
            "type": "array",
            "items": item,
        }
        applied.append(f"{def_name}.{prop}: object -> list ({reason})")
    return schema, applied

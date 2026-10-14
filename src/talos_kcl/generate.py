"""Convert the Talos machine configuration JSON schema into a KCL package.

Layout of the generated package (``talos`` by default)::

    kcl.mod
    README.md
    talos.k                 # TALOS_VERSION + `Document` type alias of every document kind
    patch/patch.k           # `Delete` schema and the `DELETE` marker ({"$patch": "delete"})
    <group>/<schema>.k      # one KCL schema per JSON schema definition, grouped by Go package

Every attribute is optional and accepts `patch.Delete`, because Talos honours
`$patch: delete` on any mapping value of a strategic merge patch.  Object schemas
also carry an optional `"$patch"` attribute so list items and whole documents can be
deleted (``{interface = "eth0", "$patch" = "delete"}``).

Known errors in the upstream schema are corrected first (see `fixes.py`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .fixes import apply_fixes

KCL_KEYWORDS = frozenset(
    {
        "True", "False", "None", "Undefined", "import", "as", "rule", "schema", "mixin",
        "protocol", "check", "for", "assert", "if", "elif", "else", "or", "and", "not",
        "in", "is", "lambda", "all", "any", "filter", "map", "type",
    }
)  # fmt: skip
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
# KCL system modules. A relative import (`import .runtime`) of a package with one of these
# names resolves to the builtin module, so the generated code always imports absolutely
# (`import talos.runtime`), and binds such packages under an alias to avoid shadowing.
KCL_SYSTEM_MODULES = frozenset(
    {
        "base64", "collection", "crypto", "datetime", "file", "json", "manifests", "math",
        "net", "os", "regex", "runtime", "template", "units", "yaml",
    }
)  # fmt: skip

PATCH_KEY = "$patch"
PATCH_PKG = "patch"
DELETE_TYPE = f"{PATCH_PKG}.Delete"
ROOT_FILE = "talos.k"


class SchemaError(Exception):
    """Raised when the JSON schema uses a construct the generator cannot represent."""


@dataclass
class Attr:
    key: str  # JSON property name, as emitted in YAML
    type: str  # KCL type annotation
    description: str
    required_upstream: bool
    default: str | None = None  # KCL literal; attributes with a default are non-optional


@dataclass
class Schema:
    group: str
    name: str
    description: str
    is_document: bool = False
    deletable: bool = True
    attrs: list[Attr] = field(default_factory=list)
    checks: list[tuple[str, str]] = field(default_factory=list)  # (expression, message)
    imports: set[str] = field(default_factory=set)
    uses_regex: bool = False

    @property
    def filename(self) -> str:
        return f"{self.group}/{snake_case(self.name)}.k"


def snake_case(name: str) -> str:
    # Split "BGPImport" into "BGP_Import", but keep versioned acronyms ("DHCPv4", "IPv6") whole.
    s = re.sub(r"([A-Z]+)([A-Z][a-z]+(?![0-9]))", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def attr_name(key: str) -> str:
    """KCL attribute name for a JSON property (keywords are `$`-escaped, odd names quoted)."""
    if IDENT.match(key):
        return f"${key}" if key in KCL_KEYWORDS else key
    return json.dumps(key, ensure_ascii=False)


def expr_name(key: str) -> str | None:
    """Name usable to reference the attribute inside a check expression, if any."""
    return attr_name(key) if IDENT.match(key) else None


def literal(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # KCL interpolates "${...}" in string literals.
        return json.dumps(value, ensure_ascii=False).replace("${", "\\${")
    raise SchemaError(f"unsupported literal {value!r}")


def union(types: list[str]) -> str:
    out: list[str] = []
    for t in types:
        if t not in out:
            out.append(t)
    if "any" in out:
        return "any"
    return " | ".join(out)


def split_def(def_name: str) -> tuple[str, str]:
    group, _, name = def_name.rpartition(".")
    group = group.replace(".", "_") or "common"
    if not IDENT.match(group) or group in KCL_KEYWORDS or group == PATCH_PKG:
        raise SchemaError(f"definition group {group!r} is not a usable KCL package name")
    if not IDENT.match(name) or name in KCL_KEYWORDS:
        raise SchemaError(f"definition name {name!r} is not a usable KCL schema name")
    return group, name


def module_alias(group: str) -> str:
    """Name a generated package is bound to when imported from inside the package."""
    return f"{group}_" if group in KCL_SYSTEM_MODULES else group


def import_stmt(package: str, group: str) -> str:
    alias = module_alias(group)
    return f"import {package}.{group}" + (f" as {alias}" if alias != group else "")


def ref_def(ref: str) -> str:
    for prefix in ("#/$defs/", "#/definitions/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    raise SchemaError(f"unsupported $ref {ref!r}")


def clean_text(text: str) -> str:
    text = (text or "").strip().replace("\r\n", "\n")
    # The docstring is a raw triple-quoted string: it cannot contain a triple quote.
    return text.replace('"""', "'''")


class Generator:
    def __init__(self, schema: dict, talos_version: str, package_name: str = "talos", package_version: str | None = None):
        schema, self.fixes = apply_fixes(schema)
        self.defs: dict[str, dict] = schema.get("$defs") or schema.get("definitions") or {}
        if not self.defs:
            raise SchemaError("schema has no $defs")
        if not IDENT.match(package_name) or package_name in KCL_KEYWORDS | KCL_SYSTEM_MODULES:
            raise SchemaError(f"package name {package_name!r} is not a usable KCL package name")
        self.talos_version = talos_version
        self.package_name = package_name
        self.package_version = package_version or talos_version.removeprefix("v")
        self.document_defs = [ref_def(d["$ref"]) for d in schema.get("oneOf", []) if "$ref" in d]
        self.schemas: dict[tuple[str, str], Schema] = {}

    # ------------------------------------------------------------------ conversion

    def convert(self) -> None:
        for def_name, node in self.defs.items():
            group, name = split_def(def_name)
            self.convert_object(group, name, node, is_document=def_name in self.document_defs)

    def convert_object(self, group: str, name: str, node: dict, is_document: bool = False) -> Schema:
        key = (group, name)
        if key in self.schemas:
            raise SchemaError(f"duplicate schema {group}.{name}")
        props: dict[str, dict] = node.get("properties") or {}
        schema = Schema(group, name, clean_text(node.get("description", "")), is_document=is_document)
        self.schemas[key] = schema
        if is_document:
            # The legacy v1alpha1 document has no apiVersion/kind; Talos refuses to delete its root.
            schema.deletable = "kind" in props
        required = set(node.get("required") or [])

        for prop, pnode in props.items():
            if prop == PATCH_KEY:
                raise SchemaError(f"{group}.{name} already defines {PATCH_KEY}")
            default = None
            if is_document and prop in ("apiVersion", "kind") and len(pnode.get("enum") or []) == 1:
                # Fixed document identity: emit it automatically.
                kcl_type = default = literal(pnode["enum"][0])
            else:
                base = self.kcl_type(pnode, schema, prop)
                kcl_type = base if base == "any" else union([base, DELETE_TYPE])
            schema.attrs.append(
                Attr(prop, kcl_type, clean_text(pnode.get("description", "")), prop in required, default)
            )
            self.add_checks(schema, prop, pnode)
        return schema

    def kcl_type(self, node: dict, ctx: Schema, hint: str) -> str:
        """KCL type for a JSON schema node, without the `patch.Delete` alternative."""
        if "$ref" in node:
            group, name = split_def(ref_def(node["$ref"]))
            if group == ctx.group:
                return name
            ctx.imports.add(group)
            return f"{module_alias(group)}.{name}"
        if "enum" in node:
            return union([literal(v) for v in node["enum"]])
        for kw in ("oneOf", "anyOf"):
            if kw in node:
                return union([self.kcl_type(sub, ctx, hint) for sub in node[kw]])
        if "allOf" in node:
            raise SchemaError(f"allOf is not supported ({ctx.group}.{ctx.name}.{hint})")
        if "const" in node:
            return literal(node["const"])

        types = node.get("type")
        if isinstance(types, list):
            return union([self.kcl_type({**node, "type": t}, ctx, hint) for t in types if t != "null"])
        if types is None and any(k in node for k in ("properties", "patternProperties", "additionalProperties")):
            types = "object"
        match types:
            case "string":
                return "str"
            case "integer":
                return "int"
            case "number":
                return "float"
            case "boolean":
                return "bool"
            case "array":
                items = node.get("items")
                return f"[{self.kcl_type(items, ctx, hint + 'Item')}]" if items else "[any]"
            case "object":
                return self.object_type(node, ctx, hint)
            case None:
                return "any"
        raise SchemaError(f"unsupported type {types!r} ({ctx.group}.{ctx.name}.{hint})")

    def object_type(self, node: dict, ctx: Schema, hint: str) -> str:
        if node.get("properties"):
            # Inline object: hoist it into its own schema next to the parent.
            name = ctx.name + hint[:1].upper() + re.sub(r"[^A-Za-z0-9_]", "_", hint[1:])
            self.convert_object(ctx.group, name, node)
            return name
        values = [self.kcl_type(v, ctx, hint + "Value") for v in (node.get("patternProperties") or {}).values()]
        extra = node.get("additionalProperties")
        if isinstance(extra, dict):
            values.append(self.kcl_type(extra, ctx, hint + "Value"))
        elif extra is True or not values:
            values.append("any")
        value_type = union(values)
        # Map entries can be removed individually with `$patch: delete`.
        return f"{{str:{value_type if value_type == 'any' else union([value_type, DELETE_TYPE])}}}"

    # ------------------------------------------------------------------ checks

    # Attributes are unions with `patch.Delete`, so every check is guarded by a `typeof` test
    # and narrows the value for the type checker: `str(x)`, `float(x)`, or `[*x]` for lists.

    def add_checks(self, schema: Schema, prop: str, node: dict) -> None:
        ref = expr_name(prop)
        if ref is None:
            return
        if "$ref" in node:
            return
        self._value_checks(schema, ref, prop, node)
        items = node.get("items")
        if isinstance(items, dict) and "$ref" not in items:
            item_checks = self._scalar_conditions(schema, "_item", items)
            if item_checks:
                cond = all_of(item_checks)
                schema.checks.append(
                    (
                        f'all _item in [*{ref}] {{{cond}}} if typeof({ref}) == "list"',
                        f"every item of {prop} must satisfy: {self._describe(items)}",
                    )
                )

    def _value_checks(self, schema: Schema, ref: str, prop: str, node: dict) -> None:
        conds = self._scalar_conditions(schema, ref, node)
        if conds:
            schema.checks.append((all_of(conds), f"{prop} must satisfy: {self._describe(node)}"))
        if "minItems" in node:
            schema.checks.append(
                (f'len([*{ref}]) >= {node["minItems"]} if typeof({ref}) == "list"', f"{prop} must have at least {node['minItems']} item(s)")
            )
        if "maxItems" in node:
            schema.checks.append(
                (f'len([*{ref}]) <= {node["maxItems"]} if typeof({ref}) == "list"', f"{prop} must have at most {node['maxItems']} item(s)")
            )

    def _scalar_conditions(self, schema: Schema, ref: str, node: dict) -> list[str]:
        """Conditions that hold for `ref` (vacuously true when it is not of the constrained type)."""
        conds: list[str] = []
        if "pattern" in node:
            schema.uses_regex = True
            conds.append(f'typeof({ref}) != "str" or regex.match(str({ref}), {literal(node["pattern"])})')
        if "minLength" in node:
            conds.append(f'typeof({ref}) != "str" or len(str({ref})) >= {node["minLength"]}')
        if "maxLength" in node:
            conds.append(f'typeof({ref}) != "str" or len(str({ref})) <= {node["maxLength"]}')
        for kw, op in (("minimum", ">="), ("maximum", "<="), ("exclusiveMinimum", ">"), ("exclusiveMaximum", "<")):
            if isinstance(node.get(kw), (int, float)) and not isinstance(node.get(kw), bool):
                conds.append(f'typeof({ref}) not in ["int", "float"] or float({ref}) {op} {node[kw]!r}')
        return conds

    @staticmethod
    def _describe(node: dict) -> str:
        parts = []
        if "pattern" in node:
            parts.append(f"pattern {node['pattern']}")
        for kw in ("minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            if kw in node:
                parts.append(f"{kw} {node[kw]}")
        return ", ".join(parts)

    # ------------------------------------------------------------------ rendering

    # Rendered files are already in `kcl fmt` canonical form (checked by the test suite).

    def header(self) -> str:
        return (
            f"# Generated by talos-kcl from the Talos Linux {self.talos_version} configuration schema.\n"
            "# DO NOT EDIT: changes will be overwritten on the next generation."
        )

    def render_schema(self, s: Schema) -> str:
        lines = [self.header()]
        lines += [import_stmt(self.package_name, g) for g in sorted(s.imports | {PATCH_PKG})]
        if s.uses_regex:
            lines.append("import regex")
        lines.append("")
        lines.append(f"schema {s.name}:")
        lines.append(indent(self.render_docstring(s), 4))
        for a in s.attrs:
            if a.default is not None:
                lines.append(f"    {attr_name(a.key)}: {a.type} = {a.default}")
            else:
                lines.append(f"    {attr_name(a.key)}?: {a.type}")
        if s.deletable:
            lines.append(f'    "{PATCH_KEY}"?: "delete"')
        if s.checks:
            lines.append("")
            lines.append("    check:")
            for expr, msg in s.checks:
                lines.append(f"        {expr}, {literal(msg)}")
        return "\n".join(lines) + "\n"

    def render_docstring(self, s: Schema) -> str:
        out = ['r"""']
        out.append(s.description or f"{s.name} schema.")
        if s.attrs or s.deletable:
            out += ["", "Attributes", "----------"]
        for a in s.attrs:
            flags = ["required" if a.default is not None else "optional"]
            if a.default is not None:
                flags.insert(0, f"default is {a.default}")
            out.append(f"{attr_name(a.key)} : {a.type}, {', '.join(flags)}")
            desc = a.description or a.key
            if a.required_upstream and a.default is None:
                desc += "\n\nRequired by Talos in the final machine configuration."
            out.append(indent(desc, 4))
        if s.deletable:
            out.append(f'"{PATCH_KEY}" : "delete", optional')
            out.append(
                indent(
                    "Strategic merge patch directive. Set to \"delete\" to remove this object: a whole\n"
                    "document (selected by apiVersion, kind and name), a list item (selected by its first\n"
                    "other key) or the field holding it.",
                    4,
                )
            )
        out.append('"""')
        return "\n".join(out)

    def render_patch(self) -> str:
        return (
            self.header()
            + '''
schema Delete:
    r"""
    Talos strategic merge patch delete directive (`$patch: delete`).

    Assign `DELETE` (or `Delete {}`) to any attribute or map entry of a Talos schema to
    remove it from the machine configuration when the patch is applied.

    Attributes
    ----------
    "$patch" : "delete", default is "delete", required
        The patch directive.
    """
    "$patch": "delete" = "delete"

DELETE: Delete = Delete {}
'''
        )

    def render_root(self) -> str:
        groups = sorted({s.group for s in self.schemas.values()})
        lines = [self.header()]
        lines += [import_stmt(self.package_name, g) for g in groups]
        lines.append("")
        lines.append(f"TALOS_VERSION = {literal(self.talos_version)}")
        docs = []
        for d in self.document_defs:
            group, name = split_def(d)
            docs.append(f"{module_alias(group)}.{name}")
        lines.append("# Any Talos machine configuration document.")
        lines.append("type Document = " + (" | ".join(docs) or "any"))
        return "\n".join(lines) + "\n"

    def render_kcl_mod(self) -> str:
        return (
            "[package]\n"
            f"name = {literal(self.package_name)}\n"
            'edition = "v0.11.0"\n'
            f"version = {literal(self.package_version)}\n"
            f"description = {literal(f'KCL schemas for the Talos Linux {self.talos_version} machine configuration, with $patch: delete support')}\n"
        )

    def render_readme(self) -> str:
        docs = sorted(f"{s.group}.{s.name}" for s in self.schemas.values() if s.is_document)
        kinds = "\n".join(f"- `{d}`" for d in docs)
        fixes = ""
        if self.fixes:
            fixes = "\n## Corrections to the upstream schema\n\n" + "\n".join(f"- {f}" for f in self.fixes) + "\n"
        return f"""# {self.package_name}

KCL schemas for the [Talos Linux](https://www.talos.dev) **{self.talos_version}** machine configuration,
generated from the upstream `config.schema.json`.

All attributes are optional so the schemas can describe partial documents (machine config patches).
Every attribute also accepts `patch.DELETE`, which renders as `$patch: delete`.

```python
import manifests
import {self.package_name}.patch
import {self.package_name}.v1alpha1

manifests.yaml_stream([
    v1alpha1.Config {{
        machine = {{certSANs = ["k8s.example.com"], features = patch.DELETE}}
    }}
])
```

## Document kinds

{kinds}
{fixes}"""

    def files(self) -> dict[str, str]:
        if not self.schemas:
            self.convert()
        out = {
            "kcl.mod": self.render_kcl_mod(),
            "README.md": self.render_readme(),
            ROOT_FILE: self.render_root(),
            f"{PATCH_PKG}/patch.k": self.render_patch(),
        }
        for s in self.schemas.values():
            if s.filename in out:
                raise SchemaError(f"file name clash: {s.filename}")
            out[s.filename] = self.render_schema(s)
        return out


def all_of(conds: list[str]) -> str:
    return conds[0] if len(conds) == 1 else " and ".join(f"({c})" for c in conds)


def indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else "" for line in text.split("\n"))


def generate(schema: dict, talos_version: str, package_name: str = "talos", package_version: str | None = None) -> dict[str, str]:
    """Return the generated package as a mapping of relative path to file content."""
    return Generator(schema, talos_version, package_name, package_version).files()

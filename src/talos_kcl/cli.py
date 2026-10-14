"""Command line entry point: `talos-kcl generate` and `talos-kcl plan`."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

from . import MIN_TALOS_VERSION, SCHEMA_URL
from .generate import generate
from .releases import env_token, package_version, parse_version, plan, registry_tags, talos_releases


def load_schema(talos_version: str, schema: str | None) -> dict:
    if schema and not schema.startswith(("http://", "https://")):
        return json.loads(Path(schema).read_text(encoding="utf-8"))
    url = schema or SCHEMA_URL.format(tag=talos_version)
    req = urllib.request.Request(url, headers={"User-Agent": "talos-kcl"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def cmd_generate(args: argparse.Namespace) -> int:
    if parse_version(args.talos_version) < parse_version(MIN_TALOS_VERSION):
        print(
            f"warning: Talos {args.talos_version} predates {MIN_TALOS_VERSION} and rejects `$patch: delete`",
            file=sys.stderr,
        )
    files = generate(
        load_schema(args.talos_version, args.schema),
        args.talos_version,
        package_name=args.package_name,
        package_version=args.package_version or package_version(args.talos_version),
    )
    out = Path(args.out)
    if out.exists():
        if not (out / "kcl.mod").exists() and any(out.iterdir()):
            print(f"refusing to overwrite non-package directory {out}", file=sys.stderr)
            return 1
        shutil.rmtree(out)
    for rel, content in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"generated {len(files)} files for Talos {args.talos_version} in {out}", file=sys.stderr)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    token = env_token()
    published = set() if args.force else registry_tags(args.registry, args.repository, args.registry_username, token)
    only = [v.strip() for v in args.versions.split(",") if v.strip()] if args.versions else None
    entries = plan(
        talos_releases(token=token),
        published,
        min_version=args.min_version,
        include_prereleases=args.include_prereleases,
        only=only,
        force=args.force,
    )
    if args.limit and len(entries) > args.limit:
        print(f"limiting {len(entries)} pending releases to the oldest {args.limit}", file=sys.stderr)
        entries = entries[: args.limit]
    print(json.dumps(entries))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="talos-kcl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate the KCL package for a Talos release")
    g.add_argument("--talos-version", required=True, help="Talos release tag, e.g. v1.14.2")
    g.add_argument("--schema", help="path or URL of config.schema.json (default: fetched from GitHub for the tag)")
    g.add_argument("--out", default="build/talos", help="output directory (replaced if it holds a KCL package)")
    g.add_argument("--package-name", default="talos")
    g.add_argument("--package-version", help="KCL package version (default: the Talos version without 'v')")
    g.set_defaults(func=cmd_generate)

    p = sub.add_parser("plan", help="print the Talos releases that still need publishing, as JSON")
    p.add_argument("--registry", default="ghcr.io")
    p.add_argument("--repository", required=True, help="OCI repository of the package, e.g. owner/talos")
    p.add_argument("--registry-username", help="username for registry auth (token taken from GITHUB_TOKEN)")
    p.add_argument("--min-version", default=MIN_TALOS_VERSION, help="oldest Talos release to consider")
    p.add_argument("--include-prereleases", action="store_true")
    p.add_argument("--versions", help="comma separated releases to build regardless of what is published")
    p.add_argument("--force", action="store_true", help="rebuild releases that are already published")
    p.add_argument("--limit", type=int, default=200, help="max entries (GitHub matrix limit is 256)")
    p.set_defaults(func=cmd_plan)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

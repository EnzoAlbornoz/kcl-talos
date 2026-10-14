"""Work out which Talos releases still need a KCL package published."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\Z")


def parse_version(tag: str) -> tuple:
    """Sort key for a semver tag; pre-releases sort before the release."""
    m = VERSION_RE.match(tag)
    if not m:
        raise ValueError(f"not a semantic version: {tag!r}")
    major, minor, patch, pre = m.groups()
    pre_key: tuple = (1,) if pre is None else (0, *((0, int(p)) if p.isdigit() else (1, p) for p in pre.split(".")))
    return (int(major), int(minor), int(patch), pre_key)


def package_version(tag: str) -> str:
    """KCL package version for a Talos tag (`v1.14.2` -> `1.14.2`)."""
    return tag.removeprefix("v")


def _request(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "talos-kcl", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read(), dict(resp.headers)


def _next_link(headers: dict[str, str]) -> str | None:
    for part in headers.get("Link", headers.get("link", "")).split(","):
        m = re.match(r'\s*<([^>]+)>\s*;\s*rel="next"', part)
        if m:
            return m.group(1)
    return None


def talos_releases(repo: str = "siderolabs/talos", token: str | None = None) -> list[dict]:
    """All published (non-draft) GitHub releases of Talos."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url: str | None = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    releases: list[dict] = []
    while url:
        body, resp_headers = _request(url, headers)
        releases += [r for r in json.loads(body) if not r.get("draft")]
        url = _next_link(resp_headers)
    return releases


def _registry_token(challenge: str, username: str | None, password: str | None) -> str:
    params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
    realm = params.pop("realm")
    headers = {}
    if username and password:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    body, _ = _request(f"{realm}?{urllib.parse.urlencode(params)}", headers)
    data = json.loads(body)
    return data.get("token") or data["access_token"]


def registry_tags(registry: str, repository: str, username: str | None = None, password: str | None = None) -> set[str]:
    """Tags of an OCI repository (empty if the repository does not exist yet)."""
    url: str | None = f"https://{registry}/v2/{repository}/tags/list?n=1000"
    headers: dict[str, str] = {}
    tags: set[str] = set()
    while url:
        try:
            body, resp_headers = _request(url, headers)
        except urllib.error.HTTPError as err:
            if err.code == 401 and "Authorization" not in headers:
                challenge = err.headers.get("WWW-Authenticate", "")
                try:
                    headers["Authorization"] = "Bearer " + _registry_token(challenge, username, password)
                except urllib.error.HTTPError as token_err:
                    # Anonymous pulls of a repository that does not exist yet are denied.
                    if token_err.code in (401, 403) and not (username and password):
                        return tags
                    raise
                continue
            if err.code in (403, 404):  # repository not created yet (or not visible yet)
                return tags
            raise
        tags.update(json.loads(body).get("tags") or [])
        link = _next_link(resp_headers)
        url = urllib.parse.urljoin(f"https://{registry}", link) if link else None
    return tags


def plan(
    releases: list[dict],
    published: set[str],
    min_version: str,
    include_prereleases: bool = False,
    only: list[str] | None = None,
    force: bool = False,
) -> list[dict[str, str]]:
    """Releases to (re)build, oldest first, as `{"talos": tag, "version": package_version}` entries."""
    floor = parse_version(min_version)
    wanted: list[str] = []
    for r in releases:
        tag = r["tag_name"]
        try:
            key = parse_version(tag)
        except ValueError:
            continue
        if only is not None:
            if tag in only or package_version(tag) in only:
                wanted.append(tag)
            continue
        if key < floor or (r.get("prerelease") and not include_prereleases):
            continue
        if force or package_version(tag) not in published:
            wanted.append(tag)
    wanted.sort(key=parse_version)
    return [{"talos": t, "version": package_version(t)} for t in wanted]


def env_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

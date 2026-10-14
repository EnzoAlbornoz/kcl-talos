# kcl-talos

Typed [KCL](https://www.kcl-lang.io) schemas for [Talos Linux](https://www.talos.dev) machine configuration,
generated from Talos's own `config.schema.json`, so you can write machine config patches in KCL,
including `$patch: delete`.

A scheduled GitHub Actions workflow watches Talos releases. For every release from **v1.8.0** on
(the first one whose config loader accepts `$patch: delete`), it generates, tests, and publishes
a KCL package version matching the Talos version:

```
oci://ghcr.io/<owner>/talos:1.14.2   <- Talos v1.14.2
```

## Using the package

```bash
kcl mod add oci://ghcr.io/<owner>/talos --tag 1.14.2
```

```python
import manifests
import talos
import talos.cluster
import talos.k8s
import talos.network
import talos.patch
import talos.v1alpha1

manifests.yaml_stream([
    v1alpha1.Config {machine.certSANs = ["k8s.example.com"]}
    network.HostnameConfigV1Alpha1 {hostname = "cp-1", auto = patch.DELETE}
    network.LinkConfigV1Alpha1 {
        name = "eth0"
        addresses = [{address = "10.0.0.11/24"}]
    }
    # Delete a whole document.
    cluster.DiscoveryServiceConfigV1Alpha1 {name = "default", "$patch" = "delete"}
    # Delete a single map entry.
    k8s.KubeNodeConfigV1Alpha1 {taints = {"node-role.kubernetes.io/control-plane" = patch.DELETE}}
])
```

```bash
kcl run main.k > patch.yaml
talosctl machineconfig patch controlplane.yaml --patch @patch.yaml -o cp-1.yaml
```

[examples/main.k](examples/main.k) shows a complete per-node setup.

### Package layout

| Import                     | Contents                                                                  |
| -------------------------- | ------------------------------------------------------------------------- |
| `talos`                    | `TALOS_VERSION`, and `Document`: a type that matches any document kind    |
| `talos.patch`              | `Delete` schema and the `DELETE` marker (`{"$patch": "delete"}`)          |
| `talos.<group>`            | one schema per Talos config type, grouped like the Go packages: `v1alpha1`, `network`, `block`, `k8s`, `runtime`, ... |

Schema names follow the Talos Go types (`network.LinkConfigV1Alpha1` is `kind: LinkConfig`).
Documents fill in `apiVersion` and `kind` on their own. Attributes that are KCL keywords are
`$`-escaped (`$type`), and names that are not identifiers are quoted (`"tcp-data-split"`).

`runtime` is also the name of a KCL system module, so import the Talos group under an alias:
`import talos.runtime as talos_runtime`.

### Deleting with `$patch`

Talos applies `$patch: delete` in three places, and the schemas allow all three:

| What to delete                       | KCL                                                                         | Renders as                              |
| ------------------------------------ | --------------------------------------------------------------------------- | --------------------------------------- |
| any field: object, list, scalar, map entry | `features = patch.DELETE`                                             | `features: {$patch: delete}`            |
| a list item                          | `addresses = [{address = "10.0.0.3/24", "$patch" = "delete"}]`              | the item, with `$patch: delete`         |
| a whole document                     | `network.LinkConfigV1Alpha1 {name = "eth0", "$patch" = "delete"}`           | apiVersion, kind, name + `$patch`       |

Every attribute's type is `T | patch.Delete`, and every object schema has an optional
`"$patch": "delete"` attribute. For object fields, `{"$patch" = "delete"}` and `patch.DELETE`
are interchangeable.

Talos rules to keep in mind (KCL can't enforce them):

- A list item is matched on its **first key other than `$patch`**, so set only the key you match on.
- `$patch` inside a map nested in a list item is rejected (`cannot delete an inner key`).
- The root of the legacy `v1alpha1` document can't be deleted, so `v1alpha1.Config` has no `$patch` attribute.

### What is validated

- Unknown attributes, wrong types, and invalid enum values fail at compile time.
- Schema `pattern`, `minimum`/`maximum` and `minItems` constraints are KCL `check`s.
- Every attribute is optional, because a patch is a partial document. Fields Talos requires are
  marked "Required by Talos in the final machine configuration" in the docstrings. Talos checks
  them when you apply the patch.
- Values are unions with `patch.Delete`. To compare one you read back, convert it first:
  `str(cfg.machine.type) == "worker"`.

## How it works

```
Talos release ──► config.schema.json ──► talos-kcl generate ──► build/talos ──► tests ──► kcl mod push
```

- [src/talos_kcl/generate.py](src/talos_kcl/generate.py) converts the JSON schema (`$defs`, refs,
  enums, `oneOf`, string maps, patterns, ...) into one KCL file per schema and adds the
  `$patch` unions. The output is already `kcl fmt` canonical.
- [src/talos_kcl/fixes.py](src/talos_kcl/fixes.py) corrects known errors in the upstream schema.
  For example, `acceptedCAs` is declared as an object but is a list in Talos. Each fix stops
  applying once Talos fixes its schema.
- [src/talos_kcl/releases.py](src/talos_kcl/releases.py) compares Talos GitHub releases with the
  tags already in the registry, to decide what to publish.

### Workflows

- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs on every push and PR:
  generator unit tests, then the package checks for the oldest supported, an older, and the
  current Talos release.
- **Release** ([.github/workflows/release.yml](.github/workflows/release.yml)) runs daily and on
  demand. It plans which Talos releases are unpublished, then generates, validates, and pushes
  each one to `ghcr.io/<owner>/talos`. Manual runs accept:
  - `versions`: build only specific releases
  - `force`: re-publish existing versions, e.g. after a generator fix
  - `include-prereleases`: also publish alpha and beta releases

  The first run backfills every release since v1.8.0. GHCR creates new packages as private.
  To let others pull, make the `talos` package public once, under the package settings on GitHub.

Each package version must pass these checks before it's pushed:

1. `scripts/test-package.sh`
   - the generated code is `kcl fmt` clean
   - every module compiles
   - the KCL unit tests in [tests/kcl](tests/kcl) pass
   - each snippet in [tests/kcl/invalid](tests/kcl/invalid) fails with its expected error
2. `scripts/e2e.sh`: renders patches with the package, applies them with the matching
   `talosctl machineconfig patch`, and checks the result.
   - [tests/e2e/generic](tests/e2e/generic) runs for every version.
   - [tests/e2e/multidoc](tests/e2e/multidoc) (Talos ≥ 1.14) covers every `$patch: delete` form:
     named and unnamed documents, list items, map entries, and scalar and object fields.

## Development

Requires [uv](https://docs.astral.sh/uv/), the [KCL CLI](https://www.kcl-lang.io/docs/user_docs/getting-started/install)
and `talosctl`.

```bash
uv run python -m unittest discover -s tests              # generator unit tests
uv run talos-kcl generate --talos-version v1.14.2        # -> build/talos (add --schema FILE to work offline)
scripts/test-package.sh                                  # validate build/talos
scripts/e2e.sh                                           # apply rendered patches with talosctl
uv run talos-kcl plan --repository <owner>/talos         # what the release workflow would publish
```

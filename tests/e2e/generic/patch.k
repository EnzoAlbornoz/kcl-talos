# Version independent patch: only uses v1alpha1 fields present in every supported Talos release.
import manifests
import talos.patch
import talos.v1alpha1

manifests.yaml_stream([
    v1alpha1.Config {
        machine = {
            certSANs = ["kcl.example.com"]
            # A list in Talos, although the upstream JSON schema says object (see fixes.py).
            acceptedCAs = [{crt = "a2NsLXRhbG9zLWUyZQ=="}]
            # Present in every generated config; removed with `$patch: delete`.
            features = patch.DELETE
        }
    }
])

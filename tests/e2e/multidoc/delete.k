# Stage 2: exercise every `$patch: delete` form Talos supports.
import manifests
import talos.block
import talos.cluster
import talos.k8s
import talos.network
import talos.patch
import talos.v1alpha1

manifests.yaml_stream([
    # Field of the legacy v1alpha1 document.
    v1alpha1.Config {machine.features = patch.DELETE}
    # Whole named document.
    cluster.DiscoveryServiceConfigV1Alpha1 {name = "default", "$patch" = "delete"}
    # Whole unnamed document.
    network.ResolverConfigV1Alpha1 {"$patch" = "delete"}
    # List item, selected by its first key; scalar field deleted alongside an update.
    network.LinkConfigV1Alpha1 {
        name = "eth0"
        mtu = 9000
        addresses = [{address = "10.0.0.3/24", "$patch" = "delete"}]
        routes = patch.DELETE
    }
    # Map entry and a whole map.
    k8s.KubeNodeConfigV1Alpha1 {
        labels = {"node.kubernetes.io/exclude-from-external-load-balancers" = patch.DELETE}
        taints = patch.DELETE
    }
    # Object field, via the schema's own "$patch" attribute.
    block.VolumeConfigV1Alpha1 {name = "EPHEMERAL", mount = {"$patch" = "delete"}}
    # Enum field deleted, sibling set.
    network.HostnameConfigV1Alpha1 {auto = patch.DELETE, hostname = "cp-1"}
])

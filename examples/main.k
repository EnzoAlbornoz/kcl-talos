# Per-node machine config patches for Talos 1.14, rendered as a multi-document YAML stream:
#
#   kcl run -q main.k -D node=cp-1 > cp-1.patch.yaml
#   talosctl machineconfig patch controlplane.yaml --patch @cp-1.patch.yaml -o cp-1.yaml
import manifests
import talos
import talos.cluster
import talos.k8s
import talos.network
import talos.patch
import talos.runtime as talos_runtime
import talos.v1alpha1

schema Node:
    name: str
    address: str
    vip?: str

nodes: {str:Node} = {
    "cp-1" = {name = "cp-1", address = "10.0.0.11/24", vip = "10.0.0.10"}
    "cp-2" = {name = "cp-2", address = "10.0.0.12/24", vip = "10.0.0.10"}
    "worker-1" = {name = "worker-1", address = "10.0.0.21/24"}
}

_node = nodes[option("node") or "cp-1"]

# Patches shared by every node.
_common: [talos.Document] = [
    v1alpha1.Config {machine.certSANs = ["k8s.example.com"]}
    talos_runtime.SysctlConfigV1Alpha1 {params = {"vm.nr_hugepages" = "1024"}}
    network.TimeSyncConfigV1Alpha1 {ntp.servers = ["time.cloudflare.com"]}
    # We run our own discovery: drop the default document entirely.
    cluster.DiscoveryServiceConfigV1Alpha1 {name = "default", "$patch" = "delete"}
]

_networking: [talos.Document] = [
    network.HostnameConfigV1Alpha1 {hostname = _node.name, auto = patch.DELETE}
    network.LinkConfigV1Alpha1 {
        name = "eth0"
        addresses = [{address = _node.address}]
        routes = [{gateway = "10.0.0.1"}]
    }
] + ([network.Layer2VIPConfigV1Alpha1 {name = _node.vip, link = "eth0"}] if _node.vip else [])

# Let workloads run on the control plane: delete the default taint (a map entry).
_scheduling: [talos.Document] = [
    k8s.KubeNodeConfigV1Alpha1 {taints = {"node-role.kubernetes.io/control-plane" = patch.DELETE}}
] if _node.vip else []

manifests.yaml_stream(_common + _networking + _scheduling)

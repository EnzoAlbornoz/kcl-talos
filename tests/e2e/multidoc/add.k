# Stage 1: add content that stage 2 partially deletes (Talos >= 1.14).
import manifests
import talos.network
import talos.v1alpha1

manifests.yaml_stream([
    v1alpha1.Config {machine.certSANs = ["kcl.example.com"]}
    network.LinkConfigV1Alpha1 {
        name = "eth0"
        addresses = [{address = "10.0.0.2/24"}, {address = "10.0.0.3/24"}]
        routes = [{gateway = "10.0.0.1"}]
    }
])

import file
import yaml

_docs = [d for d in yaml.decode_all(file.read(option("patched"))) if d]
_kind = lambda kind: str, name: str -> [any] {
    [d for d in _docs if d?.kind == kind and (not name or d?.name == name)]
}

_config = [d for d in _docs if "kind" not in d][0]
assert "kcl.example.com" in _config.machine.certSANs, "certSANs were not merged"
assert "features" not in _config.machine, "machine.features was not deleted"

assert not _kind("DiscoveryServiceConfig", ""), "named document was not deleted"
assert not _kind("ResolverConfig", ""), "unnamed document was not deleted"

_link = _kind("LinkConfig", "eth0")[0]
assert [a.address for a in _link.addresses] == ["10.0.0.2/24"], "list item was not deleted: ${_link.addresses}"
assert _link.mtu == 9000, "link mtu was not merged"
assert not _link?.routes, "routes were not deleted"

_node = _kind("KubeNodeConfig", "")[0]
assert "node.kubernetes.io/exclude-from-external-load-balancers" not in _node.labels, "map entry was not deleted"
assert "node-role.kubernetes.io/control-plane" in _node.labels, "unrelated map entry was deleted"
assert not _node?.taints, "taints were not deleted"

assert "mount" not in _kind("VolumeConfig", "EPHEMERAL")[0], "object field was not deleted"

_hostname = _kind("HostnameConfig", "")[0]
assert "auto" not in _hostname and _hostname.hostname == "cp-1", "hostname config not patched: ${_hostname}"

result = "ok"

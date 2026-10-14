# Behaviour of the generated package. Only uses schemas that exist, unchanged, in every
# Talos release from v1.8.0 on, so the release pipeline can run it for each version.
# Invalid values that KCL rejects at compile time are covered by invalid/*.k instead.
import runtime
import yaml
import talos
import talos.extensions
import talos.network
import talos.patch
import talos.runtime as talos_runtime
import talos.siderolink
import talos.v1alpha1

_fails = lambda f: () -> any {
    # runtime.catch returns the error message, or Undefined on success.
    bool(runtime.catch(f))
}

test_delete_marker = lambda {
    assert yaml.encode(patch.DELETE) == "$patch: delete\n"
    assert yaml.encode(patch.Delete {}) == "$patch: delete\n"
}

test_document_identity_defaults = lambda {
    doc = talos_runtime.KmsgLogV1Alpha1 {name = "remote", url = "tcp://192.168.0.1:5555"}
    assert doc.apiVersion == "v1alpha1"
    assert doc.kind == "KmsgLogConfig"
}

test_any_field_accepts_delete = lambda {
    cfg = v1alpha1.Config {
        debug = patch.DELETE
        machine = {type = patch.DELETE, certSANs = patch.DELETE, features = patch.DELETE}
        cluster = patch.DELETE
    }
    assert yaml.encode(cfg) == """\
debug:
  $patch: delete
machine:
  type:
    $patch: delete
  certSANs:
    $patch: delete
  features:
    $patch: delete
cluster:
  $patch: delete
"""
}

test_object_field_deleted_with_dict = lambda {
    cfg = v1alpha1.Config {machine.features = {"$patch" = "delete"}}
    assert yaml.encode(cfg) == "machine:\n  features:\n    $patch: delete\n"
}

test_document_deletion = lambda {
    named = extensions.ServiceConfigV1Alpha1 {name = "nut-client", "$patch" = "delete"}
    assert yaml.encode(named) == "apiVersion: v1alpha1\nkind: ExtensionServiceConfig\nname: nut-client\n$patch: delete\n"
    unnamed = siderolink.ConfigV1Alpha1 {"$patch" = "delete"}
    assert yaml.encode(unnamed) == "apiVersion: v1alpha1\nkind: SideroLinkConfig\n$patch: delete\n"
}

test_list_item_deletion = lambda {
    svc = extensions.ServiceConfigV1Alpha1 {
        name = "nut-client"
        configFiles = [{mountPath = "/usr/local/etc/nut/upsmon.conf", "$patch" = "delete"}]
    }
    assert yaml.encode(svc.configFiles) == "- mountPath: /usr/local/etc/nut/upsmon.conf\n  $patch: delete\n"
}

test_patterns_are_checked = lambda {
    assert not _fails(lambda { talos_runtime.KmsgLogV1Alpha1 {url = "udp://10.0.0.1:514"} })
    assert _fails(lambda { talos_runtime.KmsgLogV1Alpha1 {url = "http://10.0.0.1:514"} })
    assert not _fails(lambda { talos_runtime.KmsgLogV1Alpha1 {url = patch.DELETE} })
    assert not _fails(lambda { talos_runtime.WatchdogTimerV1Alpha1 {timeout = "2m30s"} })
    assert not _fails(lambda { talos_runtime.WatchdogTimerV1Alpha1 {timeout = "500µs"} })
    assert _fails(lambda { talos_runtime.WatchdogTimerV1Alpha1 {timeout = "soon"} })
    assert not _fails(lambda { siderolink.ConfigV1Alpha1 {apiUrl = "grpc://omni.example.com"} })
    assert _fails(lambda { siderolink.ConfigV1Alpha1 {apiUrl = "omni.example.com"} })
}

test_list_item_patterns_are_checked = lambda {
    ok = network.RuleConfigV1Alpha1 {
        name = "ssh"
        portSelector = {ports = [22, "8000-9000"], protocol = "tcp"}
        ingress = [{subnet = "10.0.0.0/8", except = "10.1.0.0/16"}]
    }
    assert ok.portSelector.ports == [22, "8000-9000"]
    assert _fails(lambda { network.IngressRule {subnet = "10.0.0.0"} })
}

test_document_union = lambda {
    docs: [talos.Document] = [
        v1alpha1.Config {machine.certSANs = ["a"]}
        talos_runtime.KmsgLogV1Alpha1 {name = "x"}
    ]
    assert len(docs) == 2
    assert talos.TALOS_VERSION.startswith("v1.")
}

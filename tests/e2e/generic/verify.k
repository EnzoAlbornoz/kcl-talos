import file
import yaml

_docs = yaml.decode_all(file.read(option("patched")))
_config = [d for d in _docs if d and "kind" not in d][0]

assert "kcl.example.com" in _config.machine.certSANs, "certSANs were not merged"
assert _config.machine.acceptedCAs == [{crt = "a2NsLXRhbG9zLWUyZQ=="}], "acceptedCAs were not merged"
assert "features" not in _config.machine, "machine.features was not deleted"

result = "ok"

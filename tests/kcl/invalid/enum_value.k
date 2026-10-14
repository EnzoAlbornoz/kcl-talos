# Enum values are checked at compile time.
# expect: got str(sctp)
import talos.network

r = network.RulePortSelector {protocol = "sctp"}

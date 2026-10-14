# The document identity is fixed.
# expect: got str(Other)
import talos.runtime as talos_runtime

d = talos_runtime.KmsgLogV1Alpha1 {kind = "Other"}

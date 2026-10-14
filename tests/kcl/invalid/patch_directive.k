# Only "delete" is a valid patch directive.
# expect: got str(replace)
import talos.siderolink

c = siderolink.ConfigV1Alpha1 {"$patch" = "replace"}

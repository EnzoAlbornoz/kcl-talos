# Schemas are closed: unknown attributes are rejected.
# expect: Cannot add member 'notAField'
import talos.v1alpha1

m = v1alpha1.MachineConfig {notAField = True}

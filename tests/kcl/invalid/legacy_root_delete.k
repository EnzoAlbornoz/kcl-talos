# Talos refuses to delete the root of the legacy v1alpha1 document.
# expect: Cannot add member '$patch' to schema 'Config'
import talos.v1alpha1

c = v1alpha1.Config {"$patch" = "delete"}

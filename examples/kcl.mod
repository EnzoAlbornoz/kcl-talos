[package]
name = "examples"
edition = "v0.11.0"
version = "0.0.0"

[dependencies]
# In your own module use the published package instead:
#   kcl mod add oci://ghcr.io/<owner>/talos --tag 1.14.2
talos = { path = "../build/talos" }

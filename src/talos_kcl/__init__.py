"""Generate a KCL package from the Talos Linux machine configuration JSON schema."""

SCHEMA_URL = "https://raw.githubusercontent.com/siderolabs/talos/{tag}/pkg/machinery/config/schemas/config.schema.json"

# First Talos release whose config loader understands `$patch: delete` (siderolabs/talos@899f1b9).
MIN_TALOS_VERSION = "v1.8.0"

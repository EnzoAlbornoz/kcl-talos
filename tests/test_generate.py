import unittest

from talos_kcl.generate import SchemaError, attr_name, generate, literal, snake_case


def prop(**kw):
    return {"description": "desc", **kw}


SCHEMA = {
    "$defs": {
        "network.LinkConfigV1Alpha1": {
            "type": "object",
            "description": "LinkConfig doc.",
            "required": ["name"],
            "properties": {
                "apiVersion": prop(enum=["v1alpha1"]),
                "kind": prop(enum=["LinkConfig"]),
                "name": prop(type="string"),
                "mtu": prop(type="integer", minimum=68, maximum=65535),
                "addresses": prop(type="array", items={"$ref": "#/$defs/network.AddressConfig"}),
                "type": prop(enum=["a", "b"]),
                "tcp-data-split": prop(type="boolean"),
                "labels": prop(type="object", patternProperties={".*": {"type": "string"}}),
                "extraArgs": prop(
                    type="object",
                    additionalProperties={"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                ),
                "raw": prop(type="object"),
                "ports": prop(type="array", items={"oneOf": [{"type": "integer"}, {"type": "string"}]}),
                "prefixes": prop(type="array", minItems=1, items={"type": "string", "pattern": "^[0-9.]+/\\d+$"}),
                "env": prop(type="object", properties={"key": prop(type="string")}),
                "timeout": prop(type="string", pattern="^[0-9]+(µs|s)$"),
                "selector": prop(**{"$ref": "#/$defs/runtime.Selector"}),
            },
        },
        "network.AddressConfig": {
            "type": "object",
            "properties": {"address": prop(type="string")},
        },
        "runtime.Selector": {"type": "object", "properties": {"match": prop(type="string")}},
        "v1alpha1.Config": {
            "type": "object",
            "properties": {"version": prop(enum=["v1alpha1"]), "debug": prop(type="boolean")},
        },
    },
    "oneOf": [
        {"$ref": "#/$defs/network.LinkConfigV1Alpha1"},
        {"$ref": "#/$defs/v1alpha1.Config"},
    ],
}


class NamingTest(unittest.TestCase):
    def test_snake_case(self):
        self.assertEqual(snake_case("LinkConfigV1Alpha1"), "link_config_v1_alpha1")
        self.assertEqual(snake_case("BGPImportRoute"), "bgp_import_route")
        self.assertEqual(snake_case("DHCPv4ConfigV1Alpha1"), "dhcpv4_config_v1_alpha1")
        self.assertEqual(snake_case("HCloudVIPConfigV1Alpha1"), "h_cloud_vip_config_v1_alpha1")

    def test_literal_escapes_interpolation(self):
        self.assertEqual(literal("a${b}"), '"a\\${b}"')
        self.assertEqual(literal("µs"), '"µs"')

    def test_attr_name(self):
        self.assertEqual(attr_name("name"), "name")
        self.assertEqual(attr_name("type"), "$type")
        self.assertEqual(attr_name("tcp-data-split"), '"tcp-data-split"')


class GenerateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = generate(SCHEMA, "v1.14.2")
        cls.link = cls.files["network/link_config_v1_alpha1.k"]

    def test_layout(self):
        self.assertEqual(
            sorted(self.files),
            [
                "README.md",
                "kcl.mod",
                "network/address_config.k",
                "network/link_config_v1_alpha1.k",
                "network/link_config_v1_alpha1_env.k",
                "patch/patch.k",
                "runtime/selector.k",
                "talos.k",
                "v1alpha1/config.k",
            ],
        )

    def test_kcl_mod(self):
        mod = self.files["kcl.mod"]
        self.assertIn('name = "talos"', mod)
        self.assertIn('version = "1.14.2"', mod)

    def test_document_identity_has_defaults(self):
        self.assertIn('    apiVersion: "v1alpha1" = "v1alpha1"\n', self.link)
        self.assertIn('    kind: "LinkConfig" = "LinkConfig"\n', self.link)

    def test_every_attribute_is_optional_and_deletable(self):
        self.assertIn("    name?: str | patch.Delete\n", self.link)
        self.assertIn("    mtu?: int | patch.Delete\n", self.link)
        self.assertIn("    selector?: runtime_.Selector | patch.Delete\n", self.link)

    def test_list_items_are_not_unioned_with_delete(self):
        # Items are deleted through their own "$patch" attribute, scalars cannot be.
        self.assertIn("    addresses?: [AddressConfig] | patch.Delete\n", self.link)
        self.assertIn("    ports?: [int | str] | patch.Delete\n", self.link)

    def test_maps_allow_deleting_entries(self):
        self.assertIn("    labels?: {str:str | patch.Delete} | patch.Delete\n", self.link)
        self.assertIn("    extraArgs?: {str:str | [str] | patch.Delete} | patch.Delete\n", self.link)
        self.assertIn("    raw?: {str:any} | patch.Delete\n", self.link)

    def test_names(self):
        self.assertIn('    $type?: "a" | "b" | patch.Delete\n', self.link)
        self.assertIn('    "tcp-data-split"?: bool | patch.Delete\n', self.link)

    def test_objects_carry_patch_directive_last(self):
        self.assertIn('    selector?: runtime_.Selector | patch.Delete\n    "$patch"?: "delete"\n\n    check:', self.link)
        self.assertTrue(self.files["network/address_config.k"].endswith('    "$patch"?: "delete"\n'))

    def test_legacy_document_root_is_not_deletable(self):
        self.assertNotIn('"$patch"?:', self.files["v1alpha1/config.k"])

    def test_inline_objects_are_hoisted(self):
        self.assertIn("    env?: LinkConfigV1Alpha1Env | patch.Delete\n", self.link)
        self.assertIn("schema LinkConfigV1Alpha1Env:", self.files["network/link_config_v1_alpha1_env.k"])

    def test_imports_are_absolute_and_avoid_system_modules(self):
        self.assertIn("import talos.patch\n", self.link)
        self.assertIn("import talos.runtime as runtime_\n", self.link)
        self.assertIn("import regex\n", self.link)
        self.assertNotIn("import talos.network", self.link)

    def test_checks(self):
        self.assertIn(
            '(typeof(mtu) not in ["int", "float"] or float(mtu) >= 68) and '
            '(typeof(mtu) not in ["int", "float"] or float(mtu) <= 65535)',
            self.link,
        )
        self.assertIn('len([*prefixes]) >= 1 if typeof(prefixes) == "list"', self.link)
        self.assertIn(
            'all _item in [*prefixes] {typeof(_item) != "str" or regex.match(str(_item), "^[0-9.]+/\\\\d+$")}',
            self.link,
        )
        self.assertIn('regex.match(str(timeout), "^[0-9]+(µs|s)$")', self.link)
        self.assertNotIn("tcp-data-split) ", self.link)

    def test_docstring_marks_upstream_required(self):
        self.assertIn("Required by Talos in the final machine configuration.", self.link)

    def test_root_module(self):
        root = self.files["talos.k"]
        self.assertIn('TALOS_VERSION = "v1.14.2"', root)
        self.assertIn("type Document = network.LinkConfigV1Alpha1 | v1alpha1.Config\n", root)
        self.assertIn("import talos.runtime as runtime_\n", root)

    def test_package_name(self):
        files = generate(SCHEMA, "v1.14.2", package_name="talos114", package_version="1.14.2-1")
        self.assertIn("import talos114.patch\n", files["network/link_config_v1_alpha1.k"])
        self.assertIn('version = "1.14.2-1"', files["kcl.mod"])
        with self.assertRaises(SchemaError):
            generate(SCHEMA, "v1.14.2", package_name="runtime")


class FixesTest(unittest.TestCase):
    def test_accepted_cas_become_lists(self):
        schema = {
            "$defs": {
                "v1alpha1.MachineConfig": {
                    "type": "object",
                    "properties": {
                        "acceptedCAs": prop(type="object", properties={"crt": prop(type="string")}),
                    },
                },
            }
        }
        files = generate(schema, "v1.10.0")
        self.assertIn(
            "    acceptedCAs?: [MachineConfigAcceptedCAsItem] | patch.Delete\n", files["v1alpha1/machine_config.k"]
        )
        self.assertIn("v1alpha1.MachineConfig.acceptedCAs: object -> list", files["README.md"])
        # The caller's schema is left untouched.
        self.assertEqual(schema["$defs"]["v1alpha1.MachineConfig"]["properties"]["acceptedCAs"]["type"], "object")

    def test_fixes_are_noops_once_upstream_is_correct(self):
        schema = {
            "$defs": {
                "v1alpha1.MachineConfig": {
                    "type": "object",
                    "properties": {"acceptedCAs": prop(type="array", items={"$ref": "#/$defs/x509.PEM"})},
                },
                "x509.PEM": {"type": "object", "properties": {"crt": prop(type="string")}},
            }
        }
        files = generate(schema, "v1.20.0")
        self.assertIn("    acceptedCAs?: [x509.PEM] | patch.Delete\n", files["v1alpha1/machine_config.k"])
        self.assertNotIn("Corrections", files["README.md"])


class UnsupportedTest(unittest.TestCase):
    def test_existing_patch_property(self):
        schema = {"$defs": {"a.B": {"type": "object", "properties": {"$patch": {"type": "string"}}}}}
        with self.assertRaises(SchemaError):
            generate(schema, "v1.0.0")

    def test_all_of(self):
        schema = {"$defs": {"a.B": {"type": "object", "properties": {"x": {"allOf": []}}}}}
        with self.assertRaises(SchemaError):
            generate(schema, "v1.0.0")


if __name__ == "__main__":
    unittest.main()

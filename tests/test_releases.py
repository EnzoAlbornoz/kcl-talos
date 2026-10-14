import unittest

from talos_kcl.releases import package_version, parse_version, plan


def rel(tag, prerelease=False):
    return {"tag_name": tag, "prerelease": prerelease}


RELEASES = [
    rel("v1.15.0-alpha.1", prerelease=True),
    rel("v1.14.2"),
    rel("v1.13.11"),
    rel("v1.14.0"),
    rel("v1.7.6"),
    rel("v1.8.0"),
    rel("not-a-version"),
]


class VersionTest(unittest.TestCase):
    def test_ordering(self):
        tags = ["v1.10.0", "v1.9.1", "v1.10.0-beta.0", "v1.10.0-alpha.2", "v1.10.0-alpha.10"]
        self.assertEqual(
            sorted(tags, key=parse_version),
            ["v1.9.1", "v1.10.0-alpha.2", "v1.10.0-alpha.10", "v1.10.0-beta.0", "v1.10.0"],
        )

    def test_package_version(self):
        self.assertEqual(package_version("v1.14.2"), "1.14.2")
        self.assertEqual(package_version("v1.15.0-alpha.1"), "1.15.0-alpha.1")


class PlanTest(unittest.TestCase):
    def tags(self, entries):
        return [e["talos"] for e in entries]

    def test_skips_published_old_and_prereleases(self):
        entries = plan(RELEASES, published={"1.14.0"}, min_version="v1.8.0")
        self.assertEqual(self.tags(entries), ["v1.8.0", "v1.13.11", "v1.14.2"])
        self.assertEqual(entries[-1], {"talos": "v1.14.2", "version": "1.14.2"})

    def test_prereleases(self):
        entries = plan(RELEASES, published=set(), min_version="v1.14.0", include_prereleases=True)
        self.assertEqual(self.tags(entries), ["v1.14.0", "v1.14.2", "v1.15.0-alpha.1"])

    def test_force_rebuilds_published(self):
        entries = plan(RELEASES, published={"1.14.0", "1.14.2"}, min_version="v1.14.0", force=True)
        self.assertEqual(self.tags(entries), ["v1.14.0", "v1.14.2"])

    def test_explicit_versions_ignore_filters(self):
        entries = plan(RELEASES, published={"1.14.2"}, min_version="v1.14.0", only=["1.14.2", "v1.7.6"])
        self.assertEqual(self.tags(entries), ["v1.7.6", "v1.14.2"])


if __name__ == "__main__":
    unittest.main()

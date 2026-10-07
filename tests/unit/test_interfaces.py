"""tests/unit/test_interfaces.py — Verify abstract interface contracts."""

import unittest

from core.interfaces import (
    BaseActionVerifier,
    BaseBrowserBackend,
    BaseElementResolver,
    BaseSelectorCache,
    BaseTaskEngine,
)


class TestCoreInterfaces(unittest.TestCase):
    def test_cannot_instantiate_abstract_backend(self):
        with self.assertRaises(TypeError):
            BaseBrowserBackend()

    def test_cannot_instantiate_abstract_resolver(self):
        with self.assertRaises(TypeError):
            BaseElementResolver()

    def test_cannot_instantiate_abstract_verifier(self):
        with self.assertRaises(TypeError):
            BaseActionVerifier()

    def test_cannot_instantiate_abstract_cache(self):
        with self.assertRaises(TypeError):
            BaseSelectorCache()

    def test_cannot_instantiate_abstract_task_engine(self):
        with self.assertRaises(TypeError):
            BaseTaskEngine()


if __name__ == "__main__":
    unittest.main()

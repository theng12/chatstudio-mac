import unittest

from backend import catalog


class CatalogTruthTests(unittest.TestCase):
    def test_repositories_and_sizes_are_unique_and_verified(self):
        repos = [m.repo for m in catalog.CATALOG]
        self.assertEqual(len(repos), len(set(repos)))
        self.assertTrue(all(m.size_gb > 0 for m in catalog.CATALOG))
        self.assertTrue(all(not catalog.serialize_model(m)["size_gb_approximate"] for m in catalog.CATALOG))

    def test_known_multimodal_entries_are_marked_for_vlm(self):
        multimodal = {
            "mlx-community/Llama-4-Scout-17B-16E-Instruct-4bit",
            "mlx-community/Mistral-Small-3.1-24B-Instruct-2503-4bit",
            "mlx-community/gemma-4-E2B-it-qat-4bit",
            "mlx-community/gemma-3-4b-it-qat-4bit",
            "mlx-community/Qwen3.5-4B-MLX-4bit",
        }
        marked = {m.repo for m in catalog.CATALOG if m.is_vision}
        self.assertTrue(multimodal <= marked)
        self.assertNotIn("mlx-community/gemma-3-1b-it-qat-4bit", marked)


if __name__ == "__main__":
    unittest.main()

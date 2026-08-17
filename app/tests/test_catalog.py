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

    def test_every_entry_belongs_to_a_declared_family(self):
        for m in catalog.CATALOG:
            self.assertIn(m.family, catalog.FAMILIES, f"{m.repo} has no family")
        used = {m.family for m in catalog.CATALOG}
        self.assertEqual(set(catalog.FAMILIES) - used, set(), "family with no variants")

    def test_memory_floor_covers_weights_within_the_gpu_budget(self):
        """macOS gives Metal ~66.67% of unified memory by default, so a model
        whose weights alone overrun that share of its declared floor cannot
        load on the machine the catalog is sending the user to."""
        for m in catalog.CATALOG:
            budget = m.min_unified_memory_gb * 1.073741824 * (2 / 3)
            self.assertLess(
                m.size_gb, budget,
                f"{m.repo}: {m.size_gb} GB of weights exceeds the "
                f"{budget:.1f} GB GPU budget of a {m.min_unified_memory_gb} GB Mac",
            )

    def test_larger_sibling_never_claims_a_lower_floor(self):
        by_family: dict[str, list[catalog.ModelEntry]] = {}
        for m in catalog.CATALOG:
            by_family.setdefault(m.family, []).append(m)
        for family, entries in by_family.items():
            for big in entries:
                for small in entries:
                    if big.size_gb > small.size_gb:
                        self.assertGreaterEqual(
                            big.min_unified_memory_gb, small.min_unified_memory_gb,
                            f"{family}: {big.repo} ({big.size_gb} GB) claims a lower "
                            f"floor than the smaller {small.repo} ({small.size_gb} GB)",
                        )

    def test_non_commercial_licence_is_flagged_where_the_user_chooses(self):
        """Qwen2.5 3B is the one catalogued model under a non-commercial
        licence. Shipping it unlabelled to someone selling a product is the
        hazard; the warning must survive future copy edits."""
        entry = catalog.get_model("mlx-community/Qwen2.5-3B-Instruct-4bit")
        self.assertIsNotNone(entry)
        self.assertIn("non-commercial", entry.best_for.lower())

    def test_gemma4_offers_both_quantization_builds_per_size(self):
        gemma4 = {m.repo for m in catalog.CATALOG if m.family == "gemma4"}
        for size in ("E2B", "E4B", "12B"):
            plain = f"mlx-community/gemma-4-{size}-it-4bit"
            qat = f"mlx-community/gemma-4-{size}-it-qat-4bit"
            self.assertIn(plain, gemma4)
            self.assertIn(qat, gemma4)
            self.assertLess(
                catalog.get_model(plain).size_gb, catalog.get_model(qat).size_gb,
                f"the plain 4-bit {size} build should be smaller than its QAT build",
            )


if __name__ == "__main__":
    unittest.main()

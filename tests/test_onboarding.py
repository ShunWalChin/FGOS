from __future__ import annotations

from unittest import TestCase

from core_engine.slug import DEFAULT_BRANDING, merge_branding, slugify


class SlugifyTest(TestCase):
    def test_basic(self) -> None:
        self.assertEqual(slugify("Minha Agência"), "minha-agencia")

    def test_strips_accents_and_symbols(self) -> None:
        self.assertEqual(slugify("FAT Tech & Cia!!"), "fat-tech-cia")

    def test_collapses_and_trims(self) -> None:
        self.assertEqual(slugify("  --Hello   World--  "), "hello-world")

    def test_empty_falls_back(self) -> None:
        self.assertEqual(slugify(""), "agencia")
        self.assertEqual(slugify("@#$%"), "agencia")

    def test_is_lowercase_ascii(self) -> None:
        s = slugify("Çãóü Studio 2026")
        self.assertEqual(s, s.lower())
        self.assertTrue(s.isascii())


class MergeBrandingTest(TestCase):
    def test_defaults_when_empty(self) -> None:
        self.assertEqual(merge_branding(None), DEFAULT_BRANDING)
        self.assertEqual(merge_branding({}), DEFAULT_BRANDING)

    def test_override_known_keys(self) -> None:
        out = merge_branding({"primary_color": "#123456", "display_name": "Acme"})
        self.assertEqual(out["primary_color"], "#123456")
        self.assertEqual(out["display_name"], "Acme")
        self.assertEqual(out["accent_color"], DEFAULT_BRANDING["accent_color"])

    def test_ignores_unknown_and_empty(self) -> None:
        out = merge_branding({"unknown": "x", "primary_color": ""})
        self.assertNotIn("unknown", out)
        self.assertEqual(out["primary_color"], DEFAULT_BRANDING["primary_color"])

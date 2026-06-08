from __future__ import annotations

import time
from unittest import TestCase

from core_engine.auth import (
    create_token,
    hash_password,
    verify_password,
    verify_token,
)

SECRET = "test-secret"


class PasswordTest(TestCase):
    def test_hash_then_verify_roundtrip(self) -> None:
        encoded = hash_password("s3nh@forte")
        self.assertTrue(encoded.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("s3nh@forte", encoded))

    def test_wrong_password_fails(self) -> None:
        encoded = hash_password("correta")
        self.assertFalse(verify_password("errada", encoded))

    def test_salt_makes_hashes_unique(self) -> None:
        self.assertNotEqual(hash_password("x"), hash_password("x"))

    def test_malformed_hash_is_rejected(self) -> None:
        self.assertFalse(verify_password("x", "not-a-valid-hash"))


class TokenTest(TestCase):
    def test_token_roundtrip_carries_claims(self) -> None:
        token = create_token({"sub": "u1", "agency_id": "a1", "role": "owner"}, SECRET, ttl_seconds=60)
        payload = verify_token(token, SECRET)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["sub"], "u1")
        self.assertEqual(payload["agency_id"], "a1")
        self.assertIn("exp", payload)

    def test_wrong_secret_is_rejected(self) -> None:
        token = create_token({"sub": "u1"}, SECRET, ttl_seconds=60)
        self.assertIsNone(verify_token(token, "other-secret"))

    def test_tampered_token_is_rejected(self) -> None:
        token = create_token({"sub": "u1"}, SECRET, ttl_seconds=60)
        head, payload, sig = token.split(".")
        tampered = f"{head}.{payload}x.{sig}"
        self.assertIsNone(verify_token(tampered, SECRET))

    def test_expired_token_is_rejected(self) -> None:
        token = create_token({"sub": "u1"}, SECRET, ttl_seconds=-1)
        time.sleep(0.01)
        self.assertIsNone(verify_token(token, SECRET))

    def test_garbage_is_rejected(self) -> None:
        self.assertIsNone(verify_token("not.a.jwt.at.all", SECRET))
        self.assertIsNone(verify_token("", SECRET))

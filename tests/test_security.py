from __future__ import annotations

import hmac
from hashlib import sha256
from unittest import TestCase

from core_engine.security import valid_meta_signature


class MetaSignatureTest(TestCase):
    def test_valid_meta_signature_accepts_hmac_sha256(self) -> None:
        body = b'{"hello":"world"}'
        secret = "super-secret"
        signature = "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()

        self.assertTrue(valid_meta_signature(body, signature, secret))

    def test_valid_meta_signature_rejects_wrong_signature(self) -> None:
        self.assertFalse(valid_meta_signature(b"{}", "sha256=bad", "super-secret"))

from __future__ import annotations

import asyncio
from unittest import TestCase

from core_engine.providers.registry import SUPPORTED_PLATFORMS, get_provider, oauth_authorize_url
from core_engine.providers.social_base import (
    DryRunProvider,
    ErrorKind,
    PublishResult,
    classify_status,
    plan_post_action,
)
from core_engine.settings import Settings


def _settings(**over) -> Settings:
    base = dict(meta_app_secret="x", meta_verify_token="y")
    base.update(over)
    return Settings(**base)


class ClassifyStatusTest(TestCase):
    def test_status_to_error_kind(self) -> None:
        self.assertEqual(classify_status(429), ErrorKind.RATE_LIMITED)
        self.assertEqual(classify_status(401), ErrorKind.AUTH)
        self.assertEqual(classify_status(403), ErrorKind.AUTH)
        self.assertEqual(classify_status(400), ErrorKind.INVALID)
        self.assertEqual(classify_status(422), ErrorKind.INVALID)
        self.assertEqual(classify_status(500), ErrorKind.NETWORK)
        self.assertEqual(classify_status(503), ErrorKind.NETWORK)
        self.assertEqual(classify_status(None), ErrorKind.NETWORK)
        self.assertEqual(classify_status(200), ErrorKind.NONE)


class PlanPostActionTest(TestCase):
    def test_success_publishes_and_reactivates_account(self) -> None:
        action = plan_post_action(PublishResult.success("p_1"))
        self.assertEqual(action.outcome, "published")
        self.assertEqual(action.account_status, "active")
        self.assertEqual(action.post_disposition, "published")
        self.assertEqual(action.event, "social.post.published")

    def test_rate_limit_pauses_account_and_backs_off(self) -> None:
        action = plan_post_action(PublishResult.failure(ErrorKind.RATE_LIMITED, "429"))
        self.assertEqual(action.account_status, "rate_limited")
        self.assertEqual(action.post_disposition, "backoff")
        self.assertEqual(action.event, "social.account.rate_limited")

    def test_auth_disconnects_account(self) -> None:
        action = plan_post_action(PublishResult.failure(ErrorKind.AUTH, "401"))
        self.assertEqual(action.account_status, "disconnected")
        self.assertEqual(action.event, "social.account.disconnected")

    def test_invalid_is_dead_lettered(self) -> None:
        action = plan_post_action(PublishResult.failure(ErrorKind.INVALID, "bad payload"))
        self.assertEqual(action.post_disposition, "dead_letter")
        self.assertEqual(action.account_status, "unchanged")
        self.assertEqual(action.event, "social.post.failed")

    def test_network_retries_without_touching_account(self) -> None:
        action = plan_post_action(PublishResult.failure(ErrorKind.NETWORK, "timeout"))
        self.assertEqual(action.post_disposition, "backoff")
        self.assertEqual(action.account_status, "unchanged")


class DryRunProviderTest(TestCase):
    def test_dry_run_returns_deterministic_synthetic_id(self) -> None:
        provider = DryRunProvider("meta")
        payload = {"caption": "olá", "scheduled_at": "2026-06-08T12:00:00Z"}
        r1 = asyncio.run(provider.publish(token="t", payload=payload))
        r2 = asyncio.run(provider.publish(token="t", payload=payload))
        self.assertTrue(r1.ok)
        self.assertTrue(r1.platform_post_id.startswith("dry_"))
        self.assertEqual(r1.platform_post_id, r2.platform_post_id)


class RegistryTest(TestCase):
    def test_dev_mode_returns_dry_run_for_every_platform(self) -> None:
        settings = _settings(social_live=False)
        for platform in SUPPORTED_PLATFORMS:
            self.assertIsInstance(get_provider(platform, settings), DryRunProvider)

    def test_unsupported_platform_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_provider("myspace", _settings())

    def test_authorize_url_carries_redirect_and_state(self) -> None:
        settings = _settings(oauth_redirect_base="https://app.fgos.dev", meta_client_id="cid")
        url = oauth_authorize_url("meta", "agency:nonce", settings)
        self.assertIn("client_id=cid", url)
        self.assertIn("state=agency%3Anonce", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fapp.fgos.dev%2Fapi%2Foauth%2Fmeta%2Fcallback", url)

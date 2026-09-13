import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils import auth


def session(user_id="user-a", email="a@example.com"):
    return SimpleNamespace(user=SimpleNamespace(id=user_id, email=email),
                           access_token="private-access", refresh_token="private-refresh")


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.session = session()
        response = SimpleNamespace(session=self.session)
        self.client.auth.sign_in_with_password.return_value = response
        self.client.auth.sign_up.return_value = response
        self.client.auth.get_session.return_value = self.session
        self.factory = patch("utils.auth.create_auth_client", return_value=self.client).start()
        self.profile = patch("utils.auth.ensure_profile").start()
        self.addCleanup(patch.stopall)
        self.state = {"query": "2 choices", "page": 1, "categories": ["choice"]}

    def test_guest_does_not_create_client_or_contact_backend(self):
        self.assertIsNone(auth.current_account(self.state))
        self.factory.assert_not_called()
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)

    def test_login_uses_provider_identity_and_keeps_search(self):
        auth.authenticate(self.state, " a@example.com ", "password")
        account = auth.current_account(self.state)
        self.assertEqual(account.user_id, "user-a")
        self.assertEqual(account.email, "a@example.com")
        self.assertIs(account.session, self.session)
        self.client.auth.sign_in_with_password.assert_called_once_with(
            {"email": "a@example.com", "password": "password"})
        self.assertEqual(self.state["query"], "2 choices")
        self.assertEqual(self.state["page"], 1)
        self.assertEqual(self.state["categories"], ["choice"])
        self.assertNotIn("private-access", repr(account))
        self.assertNotIn("private-refresh", repr(account))

    def test_invalid_credentials_are_sanitized(self):
        error = RuntimeError("private-password private-access")
        error.code = "invalid_credentials"
        self.client.auth.sign_in_with_password.side_effect = error
        auth.authenticate(self.state, "a@example.com", "private-password")
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)
        self.assertEqual(self.state[auth.NOTICE_KEY],
                         ("error", "Email or password is incorrect."))

    def test_backend_failure_does_not_leak_details(self):
        self.client.auth.sign_in_with_password.side_effect = TimeoutError("private-access")
        auth.authenticate(self.state, "a@example.com", "password")
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)
        self.assertIn("unavailable", self.state[auth.NOTICE_KEY][1])
        self.assertNotIn("private-access", repr(self.state))

    def test_configuration_failure_keeps_guest_state(self):
        self.factory.side_effect = KeyError("SUPABASE_PUBLISHABLE_KEY")
        auth.authenticate(self.state, "a@example.com", "password")
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)
        self.assertEqual(self.state["query"], "2 choices")

    def test_blank_credentials_make_no_request(self):
        for email, password in [("", "password"), ("a@example.com", "")]:
            auth.authenticate(self.state, email, password)
        self.factory.assert_not_called()

    def test_signup_with_session_signs_in(self):
        auth.authenticate(self.state, "a@example.com", "password", signup=True)
        self.assertEqual(self.state[auth.ACCOUNT_KEY].user_id, "user-a")
        self.client.auth.sign_up.assert_called_once_with(
            {"email": "a@example.com", "password": "password"})
        self.client.auth.sign_in_with_password.assert_not_called()

    def test_signup_without_session_does_not_claim_login_or_write_profile(self):
        self.client.auth.sign_up.return_value = SimpleNamespace(session=None)
        auth.authenticate(self.state, "a@example.com", "password", signup=True)
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)
        self.client.table.assert_not_called()
        self.assertIn("No signed-in session", self.state[auth.NOTICE_KEY][1])

    def test_signup_failure(self):
        self.client.auth.sign_up.side_effect = RuntimeError("private-password")
        auth.authenticate(self.state, "a@example.com", "password", signup=True)
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)
        self.assertNotIn("private-password", repr(self.state))

    def test_logout_clears_only_private_state(self):
        auth.authenticate(self.state, "a@example.com", "password")
        self.state.update(auth_email="a@example.com", auth_password="password", auth_mode="Log in")
        auth.logout(self.state)
        self.client.auth.sign_out.assert_called_once_with({"scope": "local"})
        self.assertEqual(self.state, {"query": "2 choices", "page": 1, "categories": ["choice"],
                                    auth.NOTICE_KEY: ("success", "You are signed out.")})

    def test_logout_backend_failure_still_clears_private_state(self):
        auth.authenticate(self.state, "a@example.com", "password")
        self.client.auth.sign_out.side_effect = TimeoutError("private-refresh")
        auth.logout(self.state)
        self.assertNotIn(auth.ACCOUNT_KEY, self.state)
        self.assertEqual(self.state["query"], "2 choices")
        self.assertIn("could not be confirmed", self.state[auth.NOTICE_KEY][1])
        self.assertNotIn("private-refresh", repr(self.state))

    def test_rotated_session_is_retained(self):
        auth.authenticate(self.state, "a@example.com", "password")
        rotated = session()
        rotated.refresh_token = "rotated-refresh"
        self.client.auth.get_session.return_value = rotated
        self.assertIs(auth.current_account(self.state).session, rotated)

    def test_expired_or_failed_session_returns_to_guest(self):
        for failure in [None, TimeoutError("private-refresh")]:
            with self.subTest(failure=type(failure).__name__):
                auth.authenticate(self.state, "a@example.com", "password")
                self.client.auth.get_session.side_effect = failure
                self.client.auth.get_session.return_value = None
                self.assertIsNone(auth.current_account(self.state))
                self.assertNotIn(auth.ACCOUNT_KEY, self.state)
                self.assertEqual(self.state["query"], "2 choices")

    def test_separate_sessions_get_separate_clients(self):
        other = Mock()
        other.auth.sign_in_with_password.return_value = SimpleNamespace(session=session("user-b"))
        self.factory.side_effect = [self.client, other]
        second_state = {}
        auth.authenticate(self.state, "a@example.com", "password")
        auth.authenticate(second_state, "b@example.com", "password")
        auth.logout(self.state)
        self.assertEqual(second_state[auth.ACCOUNT_KEY].user_id, "user-b")
        other.auth.sign_out.assert_not_called()

    def test_profile_failure_keeps_login_and_can_retry(self):
        self.profile.side_effect = RuntimeError("private-access")
        auth.authenticate(self.state, "a@example.com", "password")
        self.assertFalse(self.state[auth.ACCOUNT_KEY].profile_ready)
        self.assertIn("profile", self.state[auth.NOTICE_KEY][1])
        self.assertNotIn("private-access", self.state[auth.NOTICE_KEY][1])
        self.profile.side_effect = None
        auth.sync_profile(self.state)
        self.assertTrue(self.state[auth.ACCOUNT_KEY].profile_ready)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.user_id = "a3a97e5b-7ae0-4db5-8302-c2a8618698ca"
        self.session = session(self.user_id)
        response = SimpleNamespace(session=self.session)
        self.client.auth.sign_in_with_password.return_value = response
        self.client.auth.sign_up.return_value = response
        patch("utils.auth.create_auth_client", return_value=self.client).start()
        self.addCleanup(patch.stopall)

    def test_login_and_signup_upsert_authenticated_uuid(self):
        for signup in [False, True]:
            with self.subTest(signup=signup):
                self.client.reset_mock()
                state = {}
                before = datetime.now(timezone.utc)
                auth.authenticate(state, "a@example.com", "password", signup=signup)
                self.assertTrue(state[auth.ACCOUNT_KEY].profile_ready)
                self.client.table.assert_called_once_with("profiles")
                upsert = self.client.table.return_value.upsert
                payload = upsert.call_args.args[0]
                self.assertEqual(payload["user_id"], self.user_id)
                self.assertEqual(upsert.call_args.kwargs, {"on_conflict": "user_id"})
                # Sending only these columns preserves created_at and existing names.
                self.assertEqual(set(payload), {"user_id", "updated_at"})
                updated = datetime.fromisoformat(payload["updated_at"])
                self.assertEqual(updated.tzinfo, timezone.utc)
                self.assertLessEqual(before, updated)
                self.assertLessEqual(updated, datetime.now(timezone.utc))
                upsert.return_value.execute.assert_called_once_with()

    def test_repeat_login_uses_same_conflict_key_and_fresh_timestamp(self):
        times = [datetime(2026, 9, 13, 10, tzinfo=timezone.utc),
                 datetime(2026, 9, 13, 11, tzinfo=timezone.utc)]
        with patch("utils.auth.datetime") as clock:
            clock.now.side_effect = times
            for _ in times:
                auth.authenticate({}, "a@example.com", "password")
        calls = self.client.table.return_value.upsert.call_args_list
        self.assertEqual(len(calls), 2)
        for call, timestamp in zip(calls, times):
            self.assertEqual(call.args[0], {"user_id": self.user_id,
                                           "updated_at": timestamp.isoformat()})
            self.assertEqual(call.kwargs, {"on_conflict": "user_id"})

    def test_database_failure_preserves_login_and_search_then_retry_succeeds(self):
        execute = self.client.table.return_value.upsert.return_value.execute
        for signup in [False, True]:
            with self.subTest(signup=signup):
                execute.side_effect = RuntimeError("private-access database details")
                state = {"query": "2 choices", "page": 1}
                auth.authenticate(state, "a@example.com", "password", signup=signup)
                account = state[auth.ACCOUNT_KEY]
                self.assertEqual(account.user_id, self.user_id)
                self.assertFalse(account.profile_ready)
                self.assertEqual(state["query"], "2 choices")
                self.assertEqual(state["page"], 1)
                self.assertNotIn("private-access", state[auth.NOTICE_KEY][1])
                execute.side_effect = None
                auth.sync_profile(state)
                self.assertIs(state[auth.ACCOUNT_KEY], account)
                self.assertTrue(account.profile_ready)
                self.assertNotIn(auth.NOTICE_KEY, state)

    def test_guest_profile_sync_does_not_write(self):
        auth.sync_profile({})
        self.client.table.assert_not_called()


class ConfigurationTests(unittest.TestCase):
    @patch("supabase.create_client")
    def test_publishable_config_and_no_background_or_persistent_session(self, create):
        with patch("streamlit.secrets", {"SUPABASE_URL": "https://example.supabase.co",
                                         "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test"}):
            auth.create_auth_client()
        options = create.call_args.kwargs["options"]
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)

    @patch("supabase.create_client")
    def test_privileged_keys_are_rejected(self, create):
        for key in ["sb_secret_private", "eyJ.legacy-service-role.token"]:
            with patch("streamlit.secrets", {"SUPABASE_URL": "https://example.supabase.co",
                                             "SUPABASE_PUBLISHABLE_KEY": key}):
                with self.assertRaises(ValueError):
                    auth.create_auth_client()
        create.assert_not_called()

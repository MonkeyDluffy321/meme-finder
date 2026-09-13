from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from utils.auth import ACCOUNT_KEY


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class AuthAppTests(unittest.TestCase):
    def setUp(self):
        patch("utils.images.load_preview", return_value=None).start()
        self.client = Mock()
        session = SimpleNamespace(user=SimpleNamespace(id="user-a", email="a@example.com"))
        self.client.auth.sign_in_with_password.return_value = SimpleNamespace(session=session)
        self.client.auth.sign_up.return_value = SimpleNamespace(session=session)
        self.client.auth.get_session.return_value = session
        self.factory = patch("utils.auth.create_auth_client", return_value=self.client).start()
        patch("utils.auth.ensure_profile").start()
        self.addCleanup(patch.stopall)
        self.app = AppTest.from_file(str(APP_PATH)).run()

    def submit(self, label="Log in"):
        self.app.text_input(key="auth_email").set_value("a@example.com")
        self.app.text_input(key="auth_password").set_value("private-password")
        next(b for b in self.app.button if b.label == label).click().run()
        self.assertFalse(self.app.exception)

    def test_guest_preserves_search_widget_position_and_navigation(self):
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.text_input[0].key, "query")
        self.factory.assert_not_called()
        for label in ["Explore", "Categories", "Saved", "Recently Viewed"]:
            self.assertTrue(next(b for b in self.app.button if b.label == label).disabled)

    def test_login_logout_preserve_query_filters_and_results(self):
        self.app.text_input(key="query").set_value("2 choices").run()
        self.app.multiselect(key="categories").set_value(["choice"]).run()
        before = [h.value for h in self.app.subheader]
        self.submit()
        self.assertEqual(self.app.session_state[ACCOUNT_KEY].user_id, "user-a")
        self.assertIn("a@example.com", [t.value for t in self.app.text])
        self.assertEqual([h.value for h in self.app.subheader], before)
        self.app.button(key="auth_logout").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.text_input(key="query").value, "2 choices")
        self.assertEqual(self.app.multiselect(key="categories").value, ["choice"])
        self.assertEqual([h.value for h in self.app.subheader], before)
        self.assertEqual(self.app.text_input(key="auth_password").value, "")

    def test_failed_login_clears_password_and_keeps_pagination(self):
        self.app.button(key="next").click().run()
        before = [h.value for h in self.app.subheader]
        self.client.auth.sign_in_with_password.side_effect = TimeoutError("private-password")
        self.submit()
        self.assertEqual(self.app.session_state["page"], 1)
        self.assertEqual([h.value for h in self.app.subheader], before)
        self.assertEqual(self.app.text_input(key="auth_password").value, "")
        self.assertTrue(self.app.error)
        self.assertNotIn("private-password", self.app.error[0].value)

    def test_signup_panel(self):
        self.app.radio(key="auth_mode").set_value("Sign up").run()
        self.submit("Sign up")
        self.client.auth.sign_up.assert_called_once()
        self.assertEqual(self.app.session_state[ACCOUNT_KEY].user_id, "user-a")

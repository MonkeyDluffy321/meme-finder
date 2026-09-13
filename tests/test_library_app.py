from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from test_library import make_state
from utils.auth import ACCOUNT_KEY

APP = Path(__file__).resolve().parents[1] / 'app.py'


class LibraryAppTests(unittest.TestCase):
    def setUp(self):
        patch('utils.images.load_preview', return_value=None).start()
        self.addCleanup(patch.stopall)
        self.state, self.client, self.query = make_state()
        self.app = AppTest.from_file(str(APP)).run()

    def login(self):
        self.app.session_state[ACCOUNT_KEY] = self.state[ACCOUNT_KEY]
        self.app.run()
        self.assertFalse(self.app.exception)

    def test_guest_navigation_save_and_details(self):
        self.app.button(key='save-distracted-boyfriend').click().run()
        self.assertTrue(any('sign in' in i.value for i in self.app.info))
        self.app.button(key='details-distracted-boyfriend').click().run()
        for key in ['saved', 'recent']:
            self.app.button(key=key).click().run()
            self.assertFalse(self.app.exception)
            self.assertTrue(any('sign in' in i.value for i in self.app.info))
        self.client.table.assert_not_called()

    def test_only_explicit_details_writes_history_and_reopening_updates(self):
        self.login()
        self.query.upsert.assert_not_called()
        for count, opened in [(1, True), (1, False), (2, True)]:
            self.app.button(key='details-distracted-boyfriend').click().run()
            self.assertFalse(self.app.exception)
            self.assertEqual(self.query.upsert.call_count, count)
            self.assertEqual('distracted-boyfriend' in self.app.session_state['library_open_details'], opened)
            self.assertEqual(any(c.value.startswith('Keywords:') for c in self.app.caption), opened)
        self.app.run()
        self.assertEqual(self.query.upsert.call_count, 2)

    def test_details_cards_toggle_independently(self):
        self.login()
        first, second = 'distracted-boyfriend', 'two-buttons'
        for meme_id, expected, writes in [
            (first, {first}, 1), (second, {first, second}, 2),
            (first, {second}, 2), (first, {first, second}, 3),
            (second, {first}, 3),
        ]:
            self.app.button(key='details-' + meme_id).click().run()
            self.assertFalse(self.app.exception)
            self.assertEqual(self.app.session_state['library_open_details'], expected)
            self.assertEqual(sum(c.value.startswith('Keywords:') for c in self.app.caption), len(expected))
            self.assertEqual(self.query.upsert.call_count, writes)

    def test_details_persist_and_recent_reads_same_user_rows(self):
        rows = {}
        writes = []
        client = self.client

        class Query:
            def __init__(self, table):
                self.table = table
                self.payload = None
                self.filters = {}
                self.ordering = []
                self.count = None

            def upsert(query, payload, *, on_conflict):
                self.assertEqual(query.table, 'recently_viewed')
                self.assertEqual(on_conflict, 'user_id,meme_id')
                query.payload = payload.copy()
                return query

            def select(query, columns):
                return query

            def eq(query, column, value):
                query.filters[column] = value
                return query

            def order(query, column, desc=False):
                query.ordering.append((column, desc))
                return query

            def range(query, first, last):
                return query

            def limit(query, count):
                query.count = count
                return query

            def execute(query):
                if query.payload is not None:
                    payload = query.payload
                    self.assertEqual(payload['user_id'], client.auth.get_session().user.id)
                    rows[(payload['user_id'], payload['meme_id'])] = payload
                    writes.append(payload)
                    return SimpleNamespace(data=[payload])
                if query.table != 'recently_viewed':
                    return SimpleNamespace(data=[])
                self.assertEqual(query.filters, {'user_id': 'user-a'})
                self.assertEqual(query.count, 50)
                result = [row for row in rows.values()
                          if all(row[k] == v for k, v in query.filters.items())]
                for column, desc in reversed(query.ordering):
                    result.sort(key=lambda row: row[column], reverse=desc)
                return SimpleNamespace(data=result[:query.count])

        self.client.table.side_effect = Query
        self.login()
        self.assertFalse(rows)
        times = [datetime(2026, 9, 13, tzinfo=timezone.utc) + timedelta(seconds=i)
                 for i in range(3)]
        with patch('utils.library.datetime') as clock:
            clock.now.side_effect = times
            for meme_id in ['distracted-boyfriend', 'two-buttons',
                            'distracted-boyfriend', 'distracted-boyfriend']:
                self.app.button(key='details-' + meme_id).click().run()
                self.assertFalse(self.app.exception)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[('user-a', 'distracted-boyfriend')]['last_viewed_at'],
                         times[-1].isoformat())
        self.app.button(key='recent').click().run()
        headings = [h.value for h in self.app.subheader]
        self.assertLess(headings.index('Distracted Boyfriend'), headings.index('Two Buttons'))
        self.app.run()
        self.assertEqual(len(writes), 3)
        self.assertFalse(self.app.exception)

    def test_recent_write_failure_keeps_details_visible(self):
        self.login()
        self.query.upsert.side_effect = RuntimeError('private database details')
        self.app.button(key='details-distracted-boyfriend').click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any(c.value.startswith('Keywords:') for c in self.app.caption))
        self.assertTrue(any('Could not update recently viewed' in i.value for i in self.app.info))
        self.assertFalse(any('private database details' in i.value for i in self.app.info))

    def test_saved_cards_order_unsave_and_recent_navigation(self):
        self.query.execute.return_value.data = [
            {'user_id': 'user-a', 'meme_id': x} for x in ['two-buttons', 'distracted-boyfriend']]
        self.login()
        self.app.button(key='saved').click().run()
        headings = [h.value for h in self.app.subheader]
        self.assertLess(headings.index('Two Buttons'), headings.index('Distracted Boyfriend'))
        self.app.button(key='save-two-buttons').click().run()
        self.query.delete.assert_called_once()
        self.app.button(key='recent').click().run()
        self.assertFalse(self.app.exception)
        self.query.limit.assert_called_with(50)

    def test_save_failure_does_not_break_search(self):
        self.login()
        self.query.execute.side_effect = RuntimeError('secret')
        self.app.button(key='save-distracted-boyfriend').click().run()
        self.app.text_input(key='query').set_value('2 choices').run()
        self.assertFalse(self.app.exception)
        headings = [h.value for h in self.app.subheader]
        self.assertLess(headings.index('Two Buttons'), headings.index('Drake Hotline Bling'))
        self.assertTrue(self.app.warning)

    def test_logout_removes_private_cards(self):
        self.query.execute.return_value.data = [{'user_id': 'user-a', 'meme_id': 'two-buttons'}]
        self.login()
        self.app.button(key='saved').click().run()
        self.app.button(key='auth_logout').click().run()
        self.app.button(key='saved').click().run()
        self.assertNotIn('Two Buttons', [h.value for h in self.app.subheader])
        self.assertFalse(self.app.exception)

    def test_library_navigation_preserves_search_and_search_returns_to_browse(self):
        self.app.text_input(key='query').set_value('2 choices').run()
        self.app.multiselect(key='categories').set_value(['choice']).run()
        self.app.button(key='saved').click().run()
        self.assertEqual(self.app.text_input(key='query').value, '2 choices')
        self.assertEqual(self.app.multiselect(key='categories').value, ['choice'])
        next(b for b in self.app.button if b.label == 'Search').click().run()
        self.assertEqual(self.app.session_state['library_view'], 'home')
        self.assertIn('Two Buttons', [h.value for h in self.app.subheader])
        self.assertFalse(self.app.exception)

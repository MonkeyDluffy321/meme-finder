import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils.auth import Account, ACCOUNT_KEY, logout
from utils.library import LibraryError, fetch_library, record_view, resolve_memes, save_meme, unsave_meme


def make_state(uid='user-a'):
    client = Mock()
    session = SimpleNamespace(user=SimpleNamespace(id=uid, email=uid+'@example.com'))
    client.auth.get_session.return_value = session
    query = Mock()
    for method in ['select', 'eq', 'order', 'limit', 'range', 'upsert', 'delete']:
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    client.table.return_value = query
    return {ACCOUNT_KEY: Account(client, session, uid, session.user.email, True)}, client, query


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.state, self.client, self.query = make_state()

    def test_save_success_and_duplicate_preserves_original_date(self):
        rows = {}
        def upsert(payload, **options):
            key = (payload['user_id'], payload['meme_id'])
            if options.get('ignore_duplicates'):
                rows.setdefault(key, payload)
            else:
                rows[key] = payload
            return self.query
        self.query.upsert.side_effect = upsert
        save_meme(self.state, 'meme')
        original = rows[('user-a', 'meme')].copy()
        save_meme(self.state, 'meme')
        self.assertEqual(list(rows.values()), [original])
        self.assertEqual(self.query.upsert.call_args.kwargs,
                         {'on_conflict': 'user_id,meme_id', 'ignore_duplicates': True})
        self.client.table.assert_called_with('saved_memes')
        self.assertEqual(self.query.execute.call_count, 2)

    def test_unsave_scopes_both_keys(self):
        unsave_meme(self.state, 'meme')
        self.query.delete.assert_called_once_with()
        self.assertEqual([c.args for c in self.query.eq.call_args_list],
                         [('user_id', 'user-a'), ('meme_id', 'meme')])
        self.query.execute.assert_called_once()

    def test_saved_fetch_order_and_resolution(self):
        self.query.execute.return_value.data = [
            {'user_id': 'user-a', 'meme_id': x} for x in ['new', 'missing', 'old']]
        ids = fetch_library(self.state)
        self.assertEqual(ids, ['new', 'missing', 'old'])
        self.query.order.assert_any_call('created_at', desc=True)
        self.query.eq.assert_called_with('user_id', 'user-a')
        self.assertEqual(resolve_memes([{'id': 'old'}, {'id': 'new'}], ids),
                         [{'id': 'new'}, {'id': 'old'}])

    def test_saved_fetch_pages_beyond_server_cap(self):
        self.query.execute.side_effect = [SimpleNamespace(data=[
            {'user_id': 'user-a', 'meme_id': str(i)} for i in range(500)]),
            SimpleNamespace(data=[{'user_id': 'user-a', 'meme_id': 'last'}])]
        self.assertEqual(len(fetch_library(self.state)), 501)
        self.query.range.assert_any_call(0, 499)
        self.query.range.assert_any_call(500, 999)

    def test_recent_upsert_refreshes_timestamp(self):
        record_view(self.state, 'meme')
        record_view(self.state, 'meme')
        calls = self.query.upsert.call_args_list
        for call in calls:
            self.assertEqual(call.kwargs, {'on_conflict': 'user_id,meme_id'})
            self.assertEqual(call.args[0]['user_id'], 'user-a')
            self.assertEqual(call.args[0]['meme_id'], 'meme')
        self.assertLessEqual(datetime.fromisoformat(calls[0].args[0]['last_viewed_at']),
                             datetime.fromisoformat(calls[1].args[0]['last_viewed_at']))
        self.client.table.assert_called_with('recently_viewed')

    def test_recent_order_limit_and_defensive_isolation(self):
        self.query.execute.return_value.data = [
            {'user_id': 'user-b', 'meme_id': 'private'}] + [
            {'user_id': 'user-a', 'meme_id': str(i)} for i in range(60)]
        self.assertEqual(fetch_library(self.state, recent=True), [str(i) for i in range(50)])
        self.query.order.assert_any_call('last_viewed_at', desc=True)
        self.query.limit.assert_called_once_with(50)
        self.query.eq.assert_called_with('user_id', 'user-a')

    def test_guests_never_contact_database(self):
        record_view({}, 'meme')
        for operation, args in [(save_meme, ('meme',)), (unsave_meme, ('meme',)),
                                (fetch_library, ())]:
            with self.assertRaisesRegex(LibraryError, 'sign in'):
                operation({}, *args)
        self.client.table.assert_not_called()

    def test_failures_are_safe_and_preserve_search(self):
        self.state.update(query='2 choices', page=2)
        self.query.execute.side_effect = RuntimeError('secret-token')
        for operation, args in [(save_meme, ('meme',)), (unsave_meme, ('meme',)),
                                (record_view, ('meme',)), (fetch_library, ())]:
            with self.assertRaises(LibraryError) as error:
                operation(self.state, *args)
            self.assertNotIn('secret-token', str(error.exception))
        self.assertEqual(self.state['query'], '2 choices')
        self.assertEqual(self.state['page'], 2)

    def test_separate_clients_and_session_identity_validation(self):
        other, client_b, query_b = make_state('user-b')
        save_meme(self.state, 'same')
        save_meme(other, 'same')
        self.assertEqual(self.query.upsert.call_args.args[0]['user_id'], 'user-a')
        self.assertEqual(query_b.upsert.call_args.args[0]['user_id'], 'user-b')
        self.client.auth.get_session.return_value = other[ACCOUNT_KEY].session
        self.client.table.reset_mock()
        with self.assertRaises(LibraryError):
            unsave_meme(self.state, 'same')
        self.client.table.assert_not_called()
        self.assertIn(ACCOUNT_KEY, other)

    def test_logout_clears_library_state(self):
        self.state.update(library_open_details={'meme'}, library_view='saved', library_notice='saved')
        logout(self.state)
        self.assertFalse(any(k.startswith('library_') for k in self.state))

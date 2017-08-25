import asyncio
import unittest
import unittest.mock

import aioxmpp.im.p2p
import aioxmpp.im.service

import mlxc.instrumentable_list

import mlxc.conversation as conversation

from aioxmpp.testutils import (
    CoroutineMock,
    run_coroutine,
    make_listener,
    make_connected_client,
)

from mlxc.testutils import (
    MLXCTestCase
)


PEER_JID = aioxmpp.JID.fromstr("romeo@montague.lit")
MUC_JID = aioxmpp.JID.fromstr("coven@chat.shakespeare.lit")


class TestConversationNode(MLXCTestCase):
    class FakeConversationNode(conversation.ConversationNode):
        def __init__(self, node, account, mock, *, conversation=None):
            super().__init__(node, account, conversation=conversation)
            self.__mock = mock

        @asyncio.coroutine
        def _start_conversation(self, *args, **kwargs):
            return self.__mock._start_conversation(*args, **kwargs)

        @property
        def label(self):
            return self.__mock.label

        @property
        def key(self):
            return self.__mock.key

    def setUp(self):
        super().setUp()
        self.tree = mlxc.instrumentable_list.ModelTree()
        self.account = unittest.mock.Mock([])
        self.cn_mock = unittest.mock.Mock()
        self.cn = self.FakeConversationNode(
            self.tree.root,
            self.account,
            self.cn_mock,
        )
        self.listener = make_listener(self.cn)

    def test_require_conversation_uses__start_conversation(self):
        conv = run_coroutine(self.cn.require_conversation())
        self.app.client.client_by_account.assert_called_once_with(
            self.account,
        )
        self.cn_mock._start_conversation.assert_called_once_with(
            self.app.client.client_by_account()
        )
        self.assertEqual(
            conv,
            self.cn_mock._start_conversation.return_value,
        )

    def test_require_conversation_emits_on_ready(self):
        run_coroutine(self.cn.require_conversation())
        self.listener.on_ready.assert_called_once_with()

    def test_require_conversation_is_idempotent(self):
        conv1 = run_coroutine(self.cn.require_conversation())
        self.app.client.client_by_account.assert_called_once_with(
            self.account,
        )

        conv2 = run_coroutine(self.cn.require_conversation())
        self.listener.on_ready.assert_called_once_with()
        self.cn_mock._start_conversation.assert_called_once_with(
            self.app.client.client_by_account()
        )
        self.assertEqual(
            conv1,
            self.cn_mock._start_conversation.return_value,
        )
        self.assertEqual(
            conv1,
            conv2,
        )

    def test_require_conversation_raises_ConnectionError_if_no_client(self):
        self.app.client.client_by_account.side_effect = KeyError()
        with self.assertRaisesRegexp(ConnectionError, "not connected"):
            run_coroutine(self.cn.require_conversation())

        self.listener.on_stale.assert_not_called()

    def test_require_conversation_raises_ConnectionError_if_no_client_even_if_conversation(self):  # NOQA
        run_coroutine(self.cn.require_conversation())
        self.app.client.client_by_account.side_effect = KeyError()
        with self.assertRaisesRegexp(ConnectionError, "not connected"):
            run_coroutine(self.cn.require_conversation())
        self.listener.on_stale.assert_called_once_with()

    def test_require_conversation_ConnectionError_clears_existing(self):
        self.cn_mock._start_conversation.return_value = \
            unittest.mock.sentinel.first
        run_coroutine(self.cn.require_conversation())

        self.cn_mock._start_conversation.reset_mock()
        self.cn_mock._start_conversation.return_value = \
            unittest.mock.sentinel.second

        self.app.client.client_by_account.side_effect = KeyError()
        with self.assertRaisesRegexp(ConnectionError, "not connected"):
            run_coroutine(self.cn.require_conversation())
        self.app.client.client_by_account.side_effect = None

        conv2 = run_coroutine(self.cn.require_conversation())
        self.assertEqual(conv2, unittest.mock.sentinel.second)

        self.cn_mock._start_conversation.assert_called_once_with(
            self.app.client.client_by_account()
        )


class TestP2PConversationNode(MLXCTestCase):
    def setUp(self):
        super().setUp()
        self.p2p_service = unittest.mock.Mock()
        self.aioxmpp_client.mock_services[
            aioxmpp.im.p2p.Service
        ] = self.p2p_service
        self.p2p_service.get_conversation = CoroutineMock()

        self.tree = mlxc.instrumentable_list.ModelTree()
        self.account = unittest.mock.Mock([])
        self.cn = conversation.P2PConversationNode(
            self.tree.root,
            self.account,
            PEER_JID,
        )

    def test_label(self):
        self.assertEqual(
            self.cn.label,
            str(PEER_JID)
        )

    def test__start_conversation_uses_p2p_provider(self):
        conv = run_coroutine(
            self.cn._start_conversation(self.aioxmpp_client)
        )

        self.p2p_service.get_conversation.assert_called_once_with(
            PEER_JID
        )

        self.assertEqual(
            conv,
            self.p2p_service.get_conversation.return_value
        )

    def test__start_conversation_keeps_no_state(self):
        self.p2p_service.get_conversation.return_value = \
            unittest.mock.sentinel.first
        conv1 = run_coroutine(
            self.cn._start_conversation(self.aioxmpp_client)
        )

        self.p2p_service.get_conversation.assert_called_once_with(
            PEER_JID
        )
        self.p2p_service.get_conversation.reset_mock()
        self.p2p_service.get_conversation.return_value = \
            unittest.mock.sentinel.second

        conv2 = run_coroutine(
            self.cn._start_conversation(self.aioxmpp_client)
        )

        self.p2p_service.get_conversation.assert_called_once_with(
            PEER_JID
        )

        self.assertEqual(conv1, unittest.mock.sentinel.first)
        self.assertEqual(conv2, unittest.mock.sentinel.second)


class TestMUCConversationNode(MLXCTestCase):
    def setUp(self):
        super().setUp()
        self.muc_service = unittest.mock.Mock()
        self.aioxmpp_client.mock_services[
            aioxmpp.MUCClient
        ] = self.muc_service

        self.tree = mlxc.instrumentable_list.ModelTree()
        self.account = unittest.mock.Mock([])
        self.cn = conversation.MUCConversationNode(
            self.tree.root,
            self.account,
            MUC_JID,
            "firstwitch",
        )

    def test_label(self):
        self.assertEqual(
            self.cn.label,
            str(MUC_JID)
        )

    def test__start_conversation_joins(self):
        self.muc_service.join.return_value = \
            unittest.mock.sentinel.room, \
            unittest.mock.sentinel.fut,

        conv = run_coroutine(
            self.cn._start_conversation(self.aioxmpp_client)
        )

        self.muc_service.join.assert_called_once_with(
            MUC_JID,
            "firstwitch",
        )

        self.assertEqual(
            conv,
            unittest.mock.sentinel.room,
        )


class TestConversationManager(MLXCTestCase):
    def setUp(self):
        super().setUp()
        self.p2p_svc = unittest.mock.Mock(["on_spontaneous_conversation"])
        self.bookmark_svc = unittest.mock.Mock([
            "on_bookmark_added",
            "on_bookmark_changed",
            "on_bookmark_removed",
        ])
        self.aioxmpp_client.mock_services[aioxmpp.im.p2p.Service] = \
            self.p2p_svc
        self.aioxmpp_client.mock_services[aioxmpp.BookmarkClient] = \
            self.bookmark_svc

        self.cm = conversation.ConversationManager()
        self.listener = make_listener(self.cm)

    def tearDown(self):
        del self.cm

    def test_tree(self):
        self.assertIsInstance(
            self.cm.tree,
            mlxc.instrumentable_list.ModelTree,
        )
        self.assertEqual(len(self.cm.tree.root), 0)

    def test_add_identity_node(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity
        )
        self.assertEqual(
            len(self.cm.tree.root),
            1
        )
        node = self.cm.tree.root[0]
        self.assertIsInstance(
            node,
            conversation.ConversationIdentity,
        )
        self.assertEqual(
            node.identity,
            unittest.mock.sentinel.identity,
        )

    def test_remove_identity_node(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity1
        )
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity2
        )
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity3
        )

        self.cm.handle_identity_removed(
            unittest.mock.sentinel.identity2
        )

        self.assertEqual(
            len(self.cm.tree.root),
            2
        )
        self.assertSequenceEqual(
            [
                node.identity
                for node in self.cm.tree.root
            ],
            [
                unittest.mock.sentinel.identity1,
                unittest.mock.sentinel.identity3,
            ]
        )

    def test_prepare_client_allows_to_add_spontaneous_p2p_conversation(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity,
        )

        account = unittest.mock.Mock()
        account.parent.object_ = unittest.mock.sentinel.identity
        account.identity = unittest.mock.sentinel.identity
        conv = unittest.mock.Mock(
            spec=aioxmpp.im.p2p.Conversation
        )

        self.cm.handle_client_prepare(account, self.aioxmpp_client)

        self.p2p_svc.on_spontaneous_conversation.connect\
            .assert_called_once_with(
                unittest.mock.ANY,
            )

        (_, (cb, ), _), = \
            self.p2p_svc.on_spontaneous_conversation.connect.mock_calls

        cb(conv)

        self.assertEqual(
            len(self.cm.tree.root[0].conversations),
            1
        )
        node = self.cm.tree.root[0].conversations[0]
        self.assertIsInstance(
            node,
            conversation.ConversationNode,
        )
        self.assertEqual(
            node.conversation,
            conv,
        )

        self.listener.on_conversation_added.assert_called_once_with(
            node
        )

    def test_client_stopped_removes_p2p_callbacks(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity,
        )

        account = unittest.mock.Mock()
        account.parent.object_ = unittest.mock.sentinel.identity

        self.cm.handle_client_prepare(account, self.aioxmpp_client)

        self.p2p_svc.on_spontaneous_conversation.connect\
            .assert_called_once_with(
                unittest.mock.ANY,
            )

        self.cm.handle_client_stopped(account, self.aioxmpp_client)

        self.p2p_svc.on_spontaneous_conversation.disconnect.assert_called_once_with(  # NOQA
            self.p2p_svc.on_spontaneous_conversation.connect()
        )

    def test_client_stopped_removes_bookmark_callbacks(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity,
        )

        account = unittest.mock.Mock()
        account.parent.object_ = unittest.mock.sentinel.identity

        self.cm.handle_client_prepare(account, self.aioxmpp_client)

        self.bookmark_svc.on_bookmark_added.connect.assert_called_once_with(
            unittest.mock.ANY,
        )

        self.bookmark_svc.on_bookmark_changed.connect.assert_called_once_with(
            unittest.mock.ANY,
        )

        self.bookmark_svc.on_bookmark_removed.connect.assert_called_once_with(
            unittest.mock.ANY,
        )

        self.cm.handle_client_stopped(account, self.aioxmpp_client)

        self.bookmark_svc.on_bookmark_added.disconnect.assert_called_once_with(
            self.bookmark_svc.on_bookmark_added.connect()
        )

        self.bookmark_svc.on_bookmark_changed.disconnect.assert_called_once_with(  # NOQA
            self.bookmark_svc.on_bookmark_changed.connect()
        )

        self.bookmark_svc.on_bookmark_removed.disconnect.assert_called_once_with(  # NOQA
            self.bookmark_svc.on_bookmark_removed.connect()
        )

import unittest
import unittest.mock

import aioxmpp.im.service

import mlxc.instrumentable_list

import mlxc.conversation as conversation


class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.cm = conversation.ConversationManager()
        self.listener = unittest.mock.Mock()
        for ev in ["on_conversation_added"]:
            cb = getattr(self.listener, ev)
            cb.return_value = None
            getattr(self.cm, ev).connect(cb)

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

    def test_prepare_client_allows_to_add_conversations(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity,
        )

        client = unittest.mock.Mock()
        account = unittest.mock.Mock()
        account.parent.object_ = unittest.mock.sentinel.identity

        self.cm.handle_client_prepare(account, client)

        client.summon.assert_called_once_with(
            aioxmpp.im.service.ConversationService
        )
        client.summon().on_conversation_added.connect.assert_called_once_with(
            unittest.mock.ANY,
        )

        (_, (cb, ), _), = \
            client.summon().on_conversation_added.connect.mock_calls

        cb(unittest.mock.sentinel.conversation)

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
            unittest.mock.sentinel.conversation,
        )

        self.listener.on_conversation_added.assert_called_once_with(
            node
        )

    def test_client_stopped_removes_callbacks(self):
        self.cm.handle_identity_added(
            unittest.mock.sentinel.identity,
        )

        client = unittest.mock.Mock()
        account = unittest.mock.Mock()
        account.parent.object_ = unittest.mock.sentinel.identity

        self.cm.handle_client_prepare(account, client)

        client.summon.assert_called_once_with(
            aioxmpp.im.service.ConversationService
        )
        client.summon().on_conversation_added.connect.assert_called_once_with(
            unittest.mock.ANY,
        )

        self.cm.handle_client_stopped(account, client)
        client.summon().on_conversation_added.disconnect.assert_called_once_with(  # NOQA
            client.summon().on_conversation_added.connect()
        )

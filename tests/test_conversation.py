import asyncio
import contextlib
import itertools
import unittest
import unittest.mock

import aioxmpp.im.p2p

import jclib.archive
import jclib.client
import jclib.identity

import jclib.conversation as conversation

from aioxmpp.testutils import (
    CoroutineMock,
    run_coroutine,
    make_listener,
    make_connected_client,
)


TEST_JID1 = aioxmpp.JID.fromstr("juliet@capulet.lit")


class TestConversationNode(unittest.TestCase):
    def test_for_conversation_p2p(self):
        conv = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        with contextlib.ExitStack() as stack:
            P2PConversationNode = stack.enter_context(unittest.mock.patch(
                "jclib.conversation.P2PConversationNode"
            ))

            result = conversation.ConversationNode.for_conversation(
                unittest.mock.sentinel.account,
                conv,
            )

        P2PConversationNode.assert_called_once_with(
            unittest.mock.sentinel.account,
            conv.jid,
            conversation=conv,
        )

        self.assertEqual(result, P2PConversationNode())

    def test_for_conversation_muc(self):
        conv = unittest.mock.Mock(spec=aioxmpp.muc.Room)
        with contextlib.ExitStack() as stack:
            MUCConversationNode = stack.enter_context(unittest.mock.patch(
                "jclib.conversation.MUCConversationNode"
            ))

            result = conversation.ConversationNode.for_conversation(
                unittest.mock.sentinel.account,
                conv,
            )

        MUCConversationNode.assert_called_once_with(
            unittest.mock.sentinel.account,
            conv.jid,
            None,
            conversation=conv,
        )

        self.assertEqual(result, MUCConversationNode())

    def test_for_conversation_raises_for_unknown_types(self):
        with self.assertRaisesRegex(
                TypeError,
                "unknown conversation class"):
            conversation.ConversationNode.for_conversation(
                unittest.mock.sentinel.account,
                object()
            )


class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.accounts = unittest.mock.Mock(spec=jclib.identity.Accounts)
        self.client = unittest.mock.Mock(spec=jclib.client.Client)
        self.messages = unittest.mock.Mock(spec=jclib.archive.MessageManager)
        self.task_manager_patch = unittest.mock.patch(
            "jclib.tasks.manager",
            spec=jclib.tasks.TaskManager,
        )
        self.task_manager = self.task_manager_patch.start()
        self.cm = conversation.ConversationManager(
            self.accounts,
            self.client,
            self.messages,
        )
        self.listener = make_listener(self.cm)

    def tearDown(self):
        self.task_manager_patch.stop()

    def test_adopt_conversation_creates_and_appends_conversation_node(self):
        self.assertEqual(len(self.cm), 0)

        conv = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        conv.jid = TEST_JID1

        with contextlib.ExitStack() as stack:
            for_conversation = stack.enter_context(
                unittest.mock.patch.object(conversation.ConversationNode,
                                           "for_conversation")
            )

            result = self.cm.adopt_conversation(unittest.mock.sentinel.account,
                                                conv)

        for_conversation.assert_called_once_with(
            unittest.mock.sentinel.account,
            conv,
        )

        self.assertEqual(len(self.cm), 1)

        self.assertEqual(self.cm[0], for_conversation())

        self.assertEqual(result, for_conversation())

    def test_adopt_conversation_emits_event(self):
        conv = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        conv.jid = TEST_JID1

        with contextlib.ExitStack() as stack:
            for_conversation = stack.enter_context(
                unittest.mock.patch.object(conversation.ConversationNode,
                                           "for_conversation")
            )

            result = self.cm.adopt_conversation(unittest.mock.sentinel.account,
                                                conv)

        self.listener.on_conversation_added.assert_called_once_with(
            result,
        )

    def test_adopt_conversation_starts_task_for_join(self):
        conv = unittest.mock.Mock(spec=aioxmpp.muc.Room)
        conv.jid = TEST_JID1

        with contextlib.ExitStack() as stack:
            for_conversation = stack.enter_context(
                unittest.mock.patch.object(conversation.ConversationNode,
                                           "for_conversation")
            )

            _join_conversation = stack.enter_context(
                unittest.mock.patch.object(self.cm, "_join_conversation")
            )

            first_signal = stack.enter_context(
                unittest.mock.patch("aioxmpp.callbacks.first_signal")
            )

            self.cm.adopt_conversation(unittest.mock.sentinel.account, conv)

        first_signal.assert_called_once_with(
            conv.on_enter,
            conv.on_failure,
        )

        _join_conversation.assert_called_once_with(
            for_conversation(),
            first_signal(),
        )

        self.task_manager.start.assert_called_once_with(
            _join_conversation()
        )

    def test_adopt_conversation_deduplicates_conversations_by_jid(self):
        conv1 = unittest.mock.Mock(spec=aioxmpp.muc.Room)
        conv1.jid = TEST_JID1

        conv2 = unittest.mock.Mock(spec=aioxmpp.muc.Room)
        conv2.jid = TEST_JID1

        with contextlib.ExitStack() as stack:
            for_conversation = stack.enter_context(
                unittest.mock.patch.object(conversation.ConversationNode,
                                           "for_conversation")
            )

            result1 = self.cm.adopt_conversation(
                unittest.mock.sentinel.account,
                conv1,
            )

            result2 = self.cm.adopt_conversation(
                unittest.mock.sentinel.account,
                conv2,
            )

        for_conversation.assert_called_once_with(
            unittest.mock.sentinel.account,
            conv1,
        )

        self.assertEqual(len(self.cm), 1)
        self.assertEqual(self.cm[0], for_conversation())
        self.assertEqual(result1, result2)

        self.task_manager.start.assert_called_once_with(unittest.mock.ANY)

    def test_adopt_conversation_deduplicates_conversations_by_jid_per_account(
            self):
        base = unittest.mock.Mock()

        def generate_results():
            for i in itertools.count():
                m = unittest.mock.Mock(
                    spec=conversation.ConversationNode,
                )
                setattr(base, "conv{}".format(i), m)
                yield m

        conv1 = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        conv1.jid = TEST_JID1

        conv2 = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        conv2.jid = TEST_JID1

        with contextlib.ExitStack() as stack:
            for_conversation = stack.enter_context(
                unittest.mock.patch.object(conversation.ConversationNode,
                                           "for_conversation")
            )
            for_conversation.side_effect = generate_results()

            result1 = self.cm.adopt_conversation(
                unittest.mock.sentinel.account1,
                conv1,
            )

            for_conversation.assert_called_once_with(
                unittest.mock.sentinel.account1,
                conv1,
            )
            for_conversation.reset_mock()

            result2 = self.cm.adopt_conversation(
                unittest.mock.sentinel.account2,
                conv2,
            )

            for_conversation.assert_called_once_with(
                unittest.mock.sentinel.account2,
                conv2,
            )

        self.assertEqual(len(self.cm), 2)
        self.assertEqual(self.cm[0], base.conv0)
        self.assertEqual(self.cm[1], base.conv1)
        self.assertNotEqual(result1, result2)

    def test__join_conversation(self):
        node = unittest.mock.Mock()
        fut = asyncio.Future()

        task = asyncio.ensure_future(self.cm._join_conversation(node, fut))
        run_coroutine(asyncio.sleep(0))

        self.task_manager.update_text.assert_called_once_with(
            "Starting {}".format(node.label)
        )

        self.assertFalse(task.done())

        fut.set_result(True)

        run_coroutine(task)

    def test_open_muc_conversation_adopts_new_muc(self):
        account = unittest.mock.Mock(["jid"])
        muc_client = unittest.mock.Mock(spec=aioxmpp.MUCClient)
        client = make_connected_client()
        client.mock_services[aioxmpp.MUCClient] = muc_client
        muc_client.join.return_value = (
            unittest.mock.sentinel.room,
            unittest.mock.sentinel.fut,
        )
        self.client.client_by_account.return_value = client

        with contextlib.ExitStack() as stack:
            adopt_conversation = stack.enter_context(
                unittest.mock.patch.object(self.cm, "adopt_conversation")
            )

            result = self.cm.open_muc_conversation(
                account,
                unittest.mock.sentinel.address,
                unittest.mock.sentinel.nick,
                unittest.mock.sentinel.password,
            )

        muc_client.join.assert_called_once_with(
            unittest.mock.sentinel.address,
            unittest.mock.sentinel.nick,
            password=unittest.mock.sentinel.password,
        )

        adopt_conversation.assert_called_once_with(
            account,
            unittest.mock.sentinel.room,
        )

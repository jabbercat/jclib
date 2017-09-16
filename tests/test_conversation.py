import contextlib
import itertools
import unittest
import unittest.mock

import aioxmpp.im.p2p

import jclib.client
import jclib.identity

import jclib.conversation as conversation

from aioxmpp.testutils import (
    CoroutineMock,
    run_coroutine,
    make_listener,
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
        self.task_manager_patch = unittest.mock.patch(
            "jclib.tasks.manager",
            spec=jclib.tasks.TaskManager,
        )
        self.task_manager = self.task_manager_patch.start()
        self.cm = conversation.ConversationManager(
            self.accounts,
            self.client,
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
        conv = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        conv.jid = TEST_JID1

        with contextlib.ExitStack() as stack:
            for_conversation = stack.enter_context(
                unittest.mock.patch.object(conversation.ConversationNode,
                                           "for_conversation")
            )

            _join_conversation = stack.enter_context(
                unittest.mock.patch.object(self.cm, "_join_conversation")
            )

            self.cm.adopt_conversation(unittest.mock.sentinel.account, conv)

        _join_conversation.assert_called_once_with(
            conv,
        )

        self.task_manager.start.assert_called_once_with(
            _join_conversation()
        )

    def test_adopt_conversation_deduplicates_conversations_by_jid(self):
        conv1 = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
        conv1.jid = TEST_JID1

        conv2 = unittest.mock.Mock(spec=aioxmpp.im.p2p.Conversation)
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
        conv = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            first_signal = stack.enter_context(unittest.mock.patch(
                "aioxmpp.callbacks.first_signal",
                new=CoroutineMock(),
            ))
            first_signal.return_value = None

            run_coroutine(self.cm._join_conversation(conv))

        self.task_manager.update_text.assert_called_once_with(
            "Starting {}".format(conv.label)
        )

        first_signal.assert_called_once_with(
            conv.on_enter,
            conv.on_failure,
        )

import unittest

import jclib.cache as cache

from aioxmpp.testutils import (
    run_coroutine,
)


class TestInMemoryCache(unittest.TestCase):
    def setUp(self):
        self.c = cache.InMemoryCache()

    def tearDown(self):
        del self.c

    def test_default_maxsize(self):
        self.assertEqual(
            self.c.maxsize,
            1,
        )

    def test_store_and_retrieve(self):
        key = object()
        value = object()
        run_coroutine(self.c.store(key, value))

        result = run_coroutine(self.c.fetch(key))
        self.assertEqual(result, value)

    def test_raise_KeyError_for_unknown_key(self):
        key = object()

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(key))

        value = object()
        run_coroutine(self.c.store(key, value))

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(object()))

    def test_store_multiple(self):
        size = 3
        self.c.maxsize = size
        keys = [object() for i in range(size)]
        values = [object() for i in range(size)]

        for k, v in zip(keys, values):
            run_coroutine(self.c.store(k, v))
            self.assertEqual(
                run_coroutine(self.c.fetch(k)),
                v,
            )

        for k, v in zip(keys, values):
            self.assertEqual(
                run_coroutine(self.c.fetch(k)),
                v,
            )

    def test_maxsize_can_be_written(self):
        self.c.maxsize = 4
        self.assertEqual(self.c.maxsize, 4)

    def test_maxsize_rejects_non_positive_integers(self):
        with self.assertRaisesRegex(ValueError, "must be positive"):
            self.c.maxsize = 0

        with self.assertRaisesRegex(ValueError, "must be positive"):
            self.c.maxsize = -1

    def test_maxsize_accepts_None(self):
        self.c.maxsize = None
        self.assertIsNone(self.c.maxsize)

    def test_fetch_does_not_create_ghost_keys(self):
        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(object()))
        run_coroutine(self.c.store(object(), object()))

        # "ghost key": if one part of the data structure (the "last used") is
        # updated before the check for existance of the key is made
        # in this case, the second store would raise because there is a key
        # in the "last used" data structure which isn’t in the main data
        # structure
        run_coroutine(self.c.store(object(), object()))

    def test_lru_purge_when_decreasing_maxsize(self):
        size = 4
        self.c.maxsize = size
        keys = [object() for i in range(size)]
        values = [object() for i in range(size)]

        for k, v in zip(keys, values):
            run_coroutine(self.c.store(k, v))
            self.assertEqual(
                run_coroutine(self.c.fetch(k)),
                v,
            )

        # keys have now been fetached in insertion order
        # reducing maxsize by one should remove first key, but not the others

        self.c.maxsize = size-1

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(keys[0]))

        # we now fetch the second key, so that the third is purged instead of
        # the second when we reduce maxsize again

        run_coroutine(self.c.fetch(keys[1]))

        self.c.maxsize = size-2

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(keys[2]))

        self.assertEqual(
            run_coroutine(self.c.fetch(keys[1])),
            values[1]
        )

        # reducing the size to 1 should leave only the third key

        self.c.maxsize = 1

        self.assertEqual(
            run_coroutine(self.c.fetch(keys[1])),
            values[1]
        )

        for i in [0, 2, 3]:
            with self.assertRaises(KeyError):
                run_coroutine(self.c.fetch(keys[i]))

    def test_lru_purge_when_storing(self):
        size = 4
        self.c.maxsize = size
        keys = [object() for i in range(size+2)]
        values = [object() for i in range(size+2)]

        for k, v in zip(keys[:size], values[:size]):
            run_coroutine(self.c.store(k, v))
            self.assertEqual(
                run_coroutine(self.c.fetch(k)),
                v,
            )

        # keys have now been fetached in insertion order
        # reducing maxsize by one should remove first key, but not the others

        run_coroutine(self.c.store(keys[size], values[size]))

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(keys[0]))

        # we now fetch the second key, so that the third is purged instead of
        # the second when we reduce maxsize again

        run_coroutine(self.c.fetch(keys[2]))

        run_coroutine(self.c.store(keys[size+1], values[size+1]))

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(keys[1]))

        self.assertEqual(
            run_coroutine(self.c.fetch(keys[2])),
            values[2]
        )

        for i in [0, 1]:
            with self.assertRaises(KeyError, msg=i):
                run_coroutine(self.c.fetch(keys[i]))

        for i in [2, 3, 4, 5]:
            self.assertEqual(
                run_coroutine(self.c.fetch(keys[i])),
                values[i],
            )

    def test_expire_removes_from_cache(self):
        key = object()
        value = object()
        run_coroutine(self.c.store(key, value))

        self.c.expire(key)

        with self.assertRaises(KeyError):
            run_coroutine(self.c.fetch(key))

        run_coroutine(self.c.store(object(), value))
        run_coroutine(self.c.store(object(), value))

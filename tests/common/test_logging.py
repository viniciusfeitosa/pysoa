from __future__ import (
    absolute_import,
    unicode_literals,
)

from logging import (
    Formatter,
    LogRecord,
    WARNING,
)
import logging.handlers
import socket
import threading
import unittest

import six

from pysoa.common.logging import (
    PySOALogContextFilter,
    RecursivelyCensoredDictWrapper,
    SyslogHandler,
)
from pysoa.test.compatibility import mock


class TestPySOALogContextFilter(unittest.TestCase):
    def tearDown(self):
        # Make sure that if anything goes wrong with these tests, that it doesn't affect any other tests
        PySOALogContextFilter.clear_logging_request_context()
        PySOALogContextFilter.clear_logging_request_context()
        PySOALogContextFilter.clear_logging_request_context()
        PySOALogContextFilter.clear_logging_request_context()
        PySOALogContextFilter.clear_logging_request_context()
        PySOALogContextFilter.clear_logging_request_context()
        PySOALogContextFilter.clear_logging_request_context()

    def test_threading(self):
        thread_data = {}

        def fn(*_, **__):
            thread_data['first_get'] = PySOALogContextFilter.get_logging_request_context()

            PySOALogContextFilter.set_logging_request_context(foo='bar', **{'baz': 'qux'})

            thread_data['second_get'] = PySOALogContextFilter.get_logging_request_context()

            if thread_data.get('do_clear'):
                PySOALogContextFilter.clear_logging_request_context()

            thread_data['third_get'] = PySOALogContextFilter.get_logging_request_context()

        self.assertIsNone(PySOALogContextFilter.get_logging_request_context())

        PySOALogContextFilter.set_logging_request_context(request_id=1234, **{'correlation_id': 'abc'})

        self.assertEqual(
            {'request_id': 1234, 'correlation_id': 'abc'},
            PySOALogContextFilter.get_logging_request_context()
        )

        thread = threading.Thread(target=fn)
        thread.start()
        thread.join()

        self.assertEqual(
            {'request_id': 1234, 'correlation_id': 'abc'},
            PySOALogContextFilter.get_logging_request_context()
        )

        self.assertIsNone(thread_data['first_get'])
        self.assertEqual({'foo': 'bar', 'baz': 'qux'}, thread_data['second_get'])
        self.assertEqual({'foo': 'bar', 'baz': 'qux'}, thread_data['third_get'])

        thread_data['do_clear'] = True

        thread = threading.Thread(target=fn)
        thread.start()
        thread.join()

        self.assertEqual(
            {'request_id': 1234, 'correlation_id': 'abc'},
            PySOALogContextFilter.get_logging_request_context()
        )

        self.assertIsNone(thread_data['first_get'])
        self.assertEqual({'foo': 'bar', 'baz': 'qux'}, thread_data['second_get'])
        self.assertIsNone(thread_data['third_get'])

    def test_filter(self):
        record = mock.MagicMock()

        log_filter = PySOALogContextFilter()

        self.assertTrue(log_filter.filter(record))
        self.assertEqual('--', record.correlation_id)
        self.assertEqual('--', record.request_id)
        self.assertEqual('unknown', record.service_name)

        PySOALogContextFilter.set_service_name('foo_qux')
        PySOALogContextFilter.set_logging_request_context(filter='mine', **{'logger': 'yours'})
        self.assertEqual({'filter': 'mine', 'logger': 'yours'}, PySOALogContextFilter.get_logging_request_context())

        record.reset_mock()

        self.assertTrue(log_filter.filter(record))
        self.assertEqual('--', record.correlation_id)
        self.assertEqual('--', record.request_id)
        self.assertEqual('foo_qux', record.service_name)

        PySOALogContextFilter.set_logging_request_context(request_id=4321, **{'correlation_id': 'abc1234'})
        self.assertEqual(
            {'request_id': 4321, 'correlation_id': 'abc1234'},
            PySOALogContextFilter.get_logging_request_context()
        )

        record.reset_mock()

        self.assertTrue(log_filter.filter(record))
        self.assertEqual('abc1234', record.correlation_id)
        self.assertEqual(4321, record.request_id)
        self.assertEqual('foo_qux', record.service_name)

        PySOALogContextFilter.clear_logging_request_context()
        self.assertEqual({'filter': 'mine', 'logger': 'yours'}, PySOALogContextFilter.get_logging_request_context())

        record.reset_mock()

        self.assertTrue(log_filter.filter(record))
        self.assertEqual('--', record.correlation_id)
        self.assertEqual('--', record.request_id)
        self.assertEqual('foo_qux', record.service_name)

        PySOALogContextFilter.clear_logging_request_context()
        self.assertIsNone(PySOALogContextFilter.get_logging_request_context())

        record.reset_mock()

        self.assertTrue(log_filter.filter(record))
        self.assertEqual('--', record.correlation_id)
        self.assertEqual('--', record.request_id)
        self.assertEqual('foo_qux', record.service_name)


class TestRecursivelyCensoredDictWrapper(unittest.TestCase):
    def test_non_dict(self):
        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            RecursivelyCensoredDictWrapper(['this', 'is', 'a', 'list'])

    def test_simple_dict(self):
        original = {
            'hello': 'world',
            'password': 'censor!',
            'credit_card': '1234567890123456',
            'passphrase': True,
            'cvv': 938,
        }

        wrapped = RecursivelyCensoredDictWrapper(original)

        expected = {
            'hello': 'world',
            'password': '**********',
            'credit_card': '**********',
            'passphrase': True,
            'cvv': '**********',
        }

        self.assertEqual(expected, eval(repr(wrapped)))
        self.assertEqual(repr(wrapped), str(wrapped))
        if six.PY2:
            self.assertEqual(six.text_type(repr(wrapped)), six.text_type(wrapped))
        else:
            self.assertEqual(six.binary_type(repr(wrapped), 'utf-8'), six.binary_type(wrapped))

        # Make sure the original dict wasn't modified
        self.assertEqual(
            {
                'hello': 'world',
                'password': 'censor!',
                'credit_card': '1234567890123456',
                'passphrase': True,
                'cvv': 938,
            },
            original,
        )

    def test_complex_dict(self):
        original = {
            'a_list': [
                'a',
                True,
                109.8277,
                {'username': 'nick', 'passphrase': 'this should be censored'},
                {'username': 'allison', 'passphrase': ''},
            ],
            'a_set': {
                'b',
                False,
                18273,
            },
            'a_tuple': (
                'c',
                True,
                42,
                {'cc_number': '9876543210987654', 'cvv': '987', 'expiration': '12-20', 'pin': '4096'},
            ),
            'passwords': ['Make It Censored', None, '', 'Hello, World!'],
            'credit_card_numbers': ('1234', '5678', '9012'),
            'cvv2': {'a', None, '', 'b'},
            'pin': frozenset({'c', 'd', ''}),
            'foo': 'bar',
            'passphrases': {
                'not_sensitive': 'not censored',
                'bankAccount': 'this should also be censored',
            }
        }

        wrapped = RecursivelyCensoredDictWrapper(original)

        expected = {
            'a_list': [
                'a',
                True,
                109.8277,
                {'username': 'nick', 'passphrase': '**********'},
                {'username': 'allison', 'passphrase': ''},
            ],
            'a_set': {
                'b',
                False,
                18273,
            },
            'a_tuple': (
                'c',
                True,
                42,
                {'cc_number': '**********', 'cvv': '**********', 'expiration': '12-20', 'pin': '**********'},
            ),
            'passwords': ['**********', None, '', '**********'],
            'credit_card_numbers': ('**********', '**********', '**********'),
            'cvv2': {'**********', None, '', '**********'},
            'pin': frozenset({'**********', '**********', ''}),
            'foo': 'bar',
            'passphrases': {
                'not_sensitive': 'not censored',
                'bankAccount': '**********',
            }
        }

        self.assertEqual(expected, eval(repr(wrapped)))
        self.assertEqual(repr(wrapped), str(wrapped))
        if six.PY2:
            self.assertEqual(six.text_type(repr(wrapped)), six.text_type(wrapped))
        else:
            self.assertEqual(six.binary_type(repr(wrapped), 'utf-8'), six.binary_type(wrapped))

        self.assertEqual(
            {
                'a_list': [
                    'a',
                    True,
                    109.8277,
                    {'username': 'nick', 'passphrase': 'this should be censored'},
                    {'username': 'allison', 'passphrase': ''},
                ],
                'a_set': {
                    'b',
                    False,
                    18273,
                },
                'a_tuple': (
                    'c',
                    True,
                    42,
                    {'cc_number': '9876543210987654', 'cvv': '987', 'expiration': '12-20', 'pin': '4096'},
                ),
                'passwords': ['Make It Censored', None, '', 'Hello, World!'],
                'credit_card_numbers': ('1234', '5678', '9012'),
                'cvv2': {'a', None, '', 'b'},
                'pin': frozenset({'c', 'd', ''}),
                'foo': 'bar',
                'passphrases': {
                    'not_sensitive': 'not censored',
                    'bankAccount': 'this should also be censored',
                }
            },
            original,
        )


class TestSyslogHandler(object):
    def test_constructor(self):
        handler = SyslogHandler()
        assert handler.socktype == socket.SOCK_DGRAM
        assert handler.unixsocket is False
        assert handler.overflow == SyslogHandler.OVERFLOW_BEHAVIOR_FRAGMENT
        assert handler.maximum_length >= 1252  # (1280 - 28)

        handler = SyslogHandler(overflow=SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE)
        assert handler.socktype == socket.SOCK_DGRAM
        assert handler.unixsocket is False
        assert handler.overflow == SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
        assert handler.maximum_length >= 1252  # (1280 - 28)

        with mock.patch.object(socket.socket, 'connect'):
            handler = SyslogHandler(socket_type=socket.SOCK_STREAM)
            assert handler.socktype == socket.SOCK_STREAM
            assert handler.unixsocket is False
            assert handler.overflow == SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
            assert handler.maximum_length == 1024 * 1024

            handler = SyslogHandler(address='/path/to/unix.socket')
            assert handler.socktype == socket.SOCK_DGRAM
            assert handler.unixsocket is True or handler.unixsocket == 1  # Python 2 compatibility
            assert handler.overflow == SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
            assert handler.maximum_length == 1024 * 1024

            handler = SyslogHandler(address='/path/to/unix.socket', socket_type=socket.SOCK_STREAM)
            assert handler.socktype == socket.SOCK_STREAM
            assert handler.unixsocket is True or handler.unixsocket == 1  # Python 2 compatibility
            assert handler.overflow == SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
            assert handler.maximum_length == 1024 * 1024

    def test_emit_shorter_than_limit(self):
        handler = SyslogHandler()
        handler.maximum_length = 500
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_FRAGMENT
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a fairly short message',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        mock_send.assert_called_once_with([
            priority + b'foo_file: bar_service WARNING This is a fairly short message\000',
        ])

    def test_emit_longer_than_limit_truncate(self):
        handler = SyslogHandler()
        handler.maximum_length = 100
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')
        handler.ident = '5678'

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a much longer message that is going to exceed the maximum byte count and will need truncating',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        expected1 = (
            priority +
            b'5678foo_file: bar_service WARNING This is a much longer message that is going to exceed the max\000'
        )
        assert len(expected1) == 100

        mock_send.assert_called_once_with([
            expected1,
        ])

    def test_emit_longer_than_limit_truncate_unicode_within(self):
        # b'\xf0\x9f\x98\xb1' = u'\U0001f631' = shocked face with hands to cheeks
        handler = SyslogHandler()
        handler.maximum_length = 100
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')
        handler.ident = '5678'

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a much longer message \U0001f631 that is going to exceed the maximum byte count and will '
                'need truncating',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        expected1 = (
            priority +
            b'5678foo_file: bar_service WARNING This is a much longer message \xf0\x9f\x98\xb1 that is going to '
            b'exceed th\000'
        )
        assert len(expected1) == 100

        mock_send.assert_called_once_with([
            expected1,
        ])

    def test_emit_longer_than_limit_truncate_unicode_at_boundary(self):
        # b'\xf0\x9f\x98\xb1' = u'\U0001f631' = shocked face with hands to cheeks
        handler = SyslogHandler()
        handler.maximum_length = 100
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_TRUNCATE
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')
        handler.ident = '5678'

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a much longer message that is going to exceed the \U0001f631 maximum byte count and will '
                'need truncating',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        expected1 = (
            priority +
            b'5678foo_file: bar_service WARNING This is a much longer message that is going to exceed the \000'
        )
        assert len(expected1) == 97

        mock_send.assert_called_once_with([
            expected1,
        ])

    def test_emit_longer_than_limit_fragment(self):
        handler = SyslogHandler()
        handler.maximum_length = 100
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_FRAGMENT
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a much longer message that is going to exceed the maximum byte count and will need truncating',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        expected1 = (
            priority +
            b"foo_file: bar_service WARNING This is a much longer message that is going to exceed... (cont'd)\000"
        )
        assert len(expected1) == 100
        expected2 = (
            priority +
            b"foo_file: bar_service WARNING (cont'd #2) ... the maximum byte count and will need ... (cont'd)\000"
        )
        assert len(expected2) == 100
        expected3 = (
            priority +
            b"foo_file: bar_service WARNING (cont'd #3) ...truncating\000"
        )
        assert len(expected3) < 100

        mock_send.assert_called_once_with([
            expected1,
            expected2,
            expected3,
        ])

    def test_emit_longer_than_limit_fragment_unicode_within(self):
        # b'\xf0\x9f\x98\xb1' = u'\U0001f631' = shocked face with hands to cheeks
        handler = SyslogHandler()
        handler.maximum_length = 100
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_FRAGMENT
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a much longer message \U0001f631 that is going to exceed the maximum byte count and will '
                'need truncating',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        expected1 = (
            priority +
            b"foo_file: bar_service WARNING This is a much longer message \xf0\x9f\x98\xb1 that is going to "
            b"e... (cont'd)\000"
        )
        assert len(expected1) == 100
        expected2 = (
            priority +
            b"foo_file: bar_service WARNING (cont'd #2) ...xceed the maximum byte count and will ... (cont'd)\000"
        )
        assert len(expected2) == 100
        expected3 = (
            priority +
            b"foo_file: bar_service WARNING (cont'd #3) ...need truncating\000"
        )
        assert len(expected3) < 100

        mock_send.assert_called_once_with([
            expected1,
            expected2,
            expected3,
        ])

    def test_emit_longer_than_limit_fragment_unicode_at_boundary(self):
        # b'\xf0\x9f\x98\xb1' = u'\U0001f631' = shocked face with hands to cheeks
        handler = SyslogHandler()
        handler.maximum_length = 100
        handler.overflow = SyslogHandler.OVERFLOW_BEHAVIOR_FRAGMENT
        handler.formatter = Formatter('foo_file: %(name)s %(levelname)s %(message)s')

        record = LogRecord(
            name='bar_service',
            level=WARNING,
            pathname='/path/to/file.py',
            lineno=122,
            msg='This is a much longer message that yes is going to \U0001f631 exceed the maximum byte count and will '
                'need truncating',
            args=(),
            exc_info=None,
        )

        with mock.patch.object(handler, '_send') as mock_send:
            handler.emit(record)

        priority = '<{:d}>'.format(
            handler.encodePriority(handler.facility, handler.mapPriority(record.levelname)),
        ).encode('utf-8')

        expected1 = (
            priority +
            b"foo_file: bar_service WARNING This is a much longer message that yes is going to ... (cont'd)\000"
        )
        assert len(expected1) == 98
        expected2 = (
            priority +
            b"foo_file: bar_service WARNING (cont'd #2) ...\xf0\x9f\x98\xb1 exceed the maximum byte count and"
            b"... (cont'd)\000"
        )
        assert len(expected2) == 100
        expected3 = (
            priority +
            b"foo_file: bar_service WARNING (cont'd #3) ... will need truncating\000"
        )
        assert len(expected3) < 100

        mock_send.assert_called_once_with([
            expected1,
            expected2,
            expected3,
        ])

    # noinspection PyProtectedMember
    def test_send_udp(self):
        handler = SyslogHandler(address=('127.0.0.1', logging.handlers.SYSLOG_UDP_PORT))

        with mock.patch.object(socket.socket, 'sendto') as mock_send_to:
            handler._send(['this is the first part', 'here is another part', 'one more part'])

        mock_send_to.assert_has_calls([
            mock.call('this is the first part', ('127.0.0.1', logging.handlers.SYSLOG_UDP_PORT)),
            mock.call('here is another part', ('127.0.0.1', logging.handlers.SYSLOG_UDP_PORT)),
            mock.call('one more part', ('127.0.0.1', logging.handlers.SYSLOG_UDP_PORT)),
        ])

    # noinspection PyProtectedMember
    def test_send_tcp(self):
        with mock.patch.object(socket.socket, 'connect') as mock_connect:
            handler = SyslogHandler(
                address=('127.0.0.1', logging.handlers.SYSLOG_UDP_PORT),
                socket_type=socket.SOCK_STREAM,
            )

        mock_connect.assert_called_once_with(('127.0.0.1', logging.handlers.SYSLOG_UDP_PORT))

        with mock.patch.object(socket.socket, 'sendall') as mock_send_all:
            handler._send(['this is the first part', 'here is another part', 'one more part'])

        mock_send_all.assert_has_calls([
            mock.call('this is the first part'),
            mock.call('here is another part'),
            mock.call('one more part'),
        ])

    # noinspection PyProtectedMember
    def test_send_unix(self):
        with mock.patch.object(socket.socket, 'connect') as mock_connect:
            handler = SyslogHandler(address='/path/to/unix.socket')

        mock_connect.assert_called_once_with('/path/to/unix.socket')

        with mock.patch.object(socket.socket, 'send') as mock_send:
            handler._send(['this is the first part', 'here is another part', 'one more part'])

        mock_send.assert_has_calls([
            mock.call('this is the first part'),
            mock.call('here is another part'),
            mock.call('one more part'),
        ])

    # noinspection PyProtectedMember
    def test_send_unix_with_failure_part_way_through(self):
        with mock.patch.object(socket.socket, 'connect') as mock_connect:
            handler = SyslogHandler(address='/path/to/a/different.socket')

        mock_connect.assert_called_once_with('/path/to/a/different.socket')

        # This is weird. Creating a new socket actually dynamically creates the `send` method, which breaks mocking.
        # So we have to mock the send, connect, and close methods, and then when the send returns an error on the
        # second call, the close method has to de-mock send so that a new socket can be created, and then the
        # connection method has to re-mock send so that we can capture the send retries. Yuck.
        first_mock_send_patch = mock.patch.object(socket.socket, 'send')
        second_mock_send_patch = mock.patch.object(socket.socket, 'send')
        mock_sends = {'first_mock_send': None, 'second_mock_send': None}

        def close_side_effect(*_, **__):
            first_mock_send_patch.stop()

        def connect_side_effect(*_, **__):
            mock_sends['second_mock_send'] = second_mock_send_patch.start()
            mock_sends['second_mock_send'].side_effect = [True, True]

        try:
            with mock.patch.object(socket.socket, 'close') as mock_close, \
                    mock.patch.object(socket.socket, 'connect') as mock_connect:
                mock_sends['first_mock_send'] = first_mock_send_patch.start()
                mock_sends['first_mock_send'].side_effect = [True, OSError()]

                mock_close.side_effect = close_side_effect
                mock_connect.side_effect = connect_side_effect

                handler._send(['this is the first part', 'here is another part', 'one more part'])
        finally:
            mock.patch.stopall()

        mock_close.assert_called_once_with()
        mock_connect.assert_called_once_with('/path/to/a/different.socket')
        mock_sends['first_mock_send'].assert_has_calls([
            mock.call('this is the first part'),
            mock.call('here is another part'),
        ])
        mock_sends['second_mock_send'].assert_has_calls([
            mock.call('here is another part'),
            mock.call('one more part'),
        ])

    # noinspection PyProtectedMember
    def test_cleanly_slice_encoded_string(self):
        # b'\xf0\x9f\xa4\xae' = barf face
        # b'\xf0\x9f\x98\xbb' = cat with heart eyes
        # b'\xf0\x9f\x9b\x8c' = bed
        # b'\xf0\x9f\x92\xb8' = money with wings
        # b'\xe2\x9c\x8d\xf0\x9f\x8f\xbb' = hand writing with pen, lightest skin
        # b'\xe2\x9c\x8d\xf0\x9f\x8f\xbf' = hand writing with pen, darkest skin

        assert SyslogHandler._cleanly_slice_encoded_string(
            b'Hello world, this has no multi-byte characters',
            15
        ) == (
            b'Hello world, th',
            b'is has no multi-byte characters',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'Hello world, this has no multi-byte characters',
            16
        ) == (
            b'Hello world, thi',
            b's has no multi-byte characters',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'Hello world, this has no multi-byte characters',
            17
        ) == (
            b'Hello world, this',
            b' has no multi-byte characters',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'Hello world, this has no multi-byte characters',
            18
        ) == (
            b'Hello world, this ',
            b'has no multi-byte characters',
        )

        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            12
        ) == (
            b'This string ',
            b'\xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            13
        ) == (
            b'This string ',
            b'\xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            14
        ) == (
            b'This string ',
            b'\xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            15
        ) == (
            b'This string ',
            b'\xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            16
        ) == (
            b'This string \xf0\x9f\xa4\xae',
            b' has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            19
        ) == (
            b'This string \xf0\x9f\xa4\xae ha',
            b's \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            21
        ) == (
            b'This string \xf0\x9f\xa4\xae has ',
            b'\xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            22
        ) == (
            b'This string \xf0\x9f\xa4\xae has ',
            b'\xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            23
        ) == (
            b'This string \xf0\x9f\xa4\xae has ',
            b'\xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            24
        ) == (
            b'This string \xf0\x9f\xa4\xae has ',
            b'\xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            25
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c',
            b' multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            31
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi',
            b'-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            37
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte ',
            b'\xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            38
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte ',
            b'\xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            39
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte ',
            b'\xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            40
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d',
            b'\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            41
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d',
            b'\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            42
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d',
            b'\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            43
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d',
            b'\xf0\x9f\x8f\xbb characters!',
        )
        assert SyslogHandler._cleanly_slice_encoded_string(
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb characters!',
            44
        ) == (
            b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d\xf0\x9f\x8f\xbb',
            b' characters!',
        )

        # There's not really anything we can do about making this detect modifiers and not split between the base
        # character and modifying character. So all we really care about is that the resulting strings successfully
        # decode without errors.
        b'This string \xf0\x9f\xa4\xae has \xf0\x9f\x9b\x8c multi-byte \xe2\x9c\x8d'.decode('utf-8')
        b'\xf0\x9f\x8f\xbb characters!'.decode('utf-8')

# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Hewlett Packard Enterprise Development LP
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Test suite for module topology.platforms.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

# mock is located in unittest from Python 3.3 onwards, but as an external
# package in Python 2.7, that is why the following is done:
try:
    from unittest.mock import patch, Mock, call, ANY
except ImportError:
    from mock import patch, Mock, call, ANY

from pytest import fixture, raises

from topology.platforms.shell import (
    PExpectBashShell, DisconnectedError
)
from topology.platforms.connection import (
    AlreadyDisconnectedError, CommonConnection
)
from topology.platforms.node import (
    NonExistingConnectionError, CommonNode
)


class Node(CommonNode):
    def __init__(self, identifier, **kwargs):
        super(Node, self).__init__(identifier, **kwargs)

        self._register_connection_type('connection', Connection)

    def _get_services_address(self):
        pass

    def _register_shells(self, connectionobj):
        connectionobj._register_shell('shell', Shell('prompt'))
        connectionobj._register_shell('shell_2', Shell('prompt_2'))


class Connection(CommonConnection):
    def __init__(self, identifier, parent_node, **kwargs):
        super(Connection, self).__init__(identifier, parent_node,
                                         **kwargs)

    def _get_connect_command(self):
        return 'test connection command '


class Shell(PExpectBashShell):
    def __init__(self, prompt, **kwargs):
        super(Shell, self).__init__(prompt, **kwargs)


@fixture(scope='function')
def node():
    return Node('node')


@fixture(scope='function')
def connection():
    return Connection('0', Node('node'))


@fixture(scope='function')
def shell():
    return Shell('prompt')


@fixture(scope='function')
def spawn(request):
    patch_spawn = patch('topology.platforms.connection.Spawn')
    mock_spawn = patch_spawn.start()

    def create_mock(*args, **kwargs):
        class SpawnMock(Mock):
            def __init__(self, *args, **kwargs):
                super(SpawnMock, self).__init__(*args, **kwargs)
                self._connected = True
                self.sendline = Mock()
                self.sendline.configure_mock(
                    **{'side_effect': self._check_connection}
                )

            def close(self):
                self._connected = False

            def isalive(self):
                return self._connected

            def _check_connection(self, *args, **kwargs):
                if not self.isalive():
                    raise Exception(
                        'Attempted operation on disconnected connection.'
                    )

        return SpawnMock()

    mock_spawn.configure_mock(**{'side_effect': create_mock})

    def finalizer():
        patch_spawn.stop()

    request.addfinalizer(finalizer)

    return mock_spawn


def test_spawn_args(spawn, connection):
    """
    Test that the arguments for Pexpect spawn are correct.
    """
    connection.connect()

    spawn.assert_called_with(
        'test connection command', echo=False, env={'TERM': 'dumb'},
        logfile=ANY
    )

    connection = Connection(
        '1', Node('node'), spawn_args={'env': {'TERM': 'smart'}, 'echo': True}
    )

    connection.connect()

    spawn.assert_called_with(
        'test connection command', env={'TERM': 'smart'}, echo=True,
        logfile=ANY
    )


def test_create_shell(spawn, node):
    """
    Test that a new connection is added to the node by calling ``connect``.
    """
    assert not list(node._connections.keys())

    node.connect()

    assert list(node._connections.keys()) == ['0']

    node.connect(connection='1')

    assert list(node._connections.keys()) == ['0', '1']


def test_initial_default_connection(spawn, node):
    """
    Test that a default undefined connection exists before attempting a
    connection to the node.
    """

    assert not node._default_connection


def test_specific_default_connection(spawn, node):
    """
    Test that the specified connection is used when specified.
    Test that the default connection is used when the connection is not
    specified.
    """

    node.connect()
    node.connect(connection='1')

    node.get_shell('shell', connection='1').send_command('command')

    node._connections['1']._spawn.sendline.assert_called_with('command')

    with raises(AssertionError):
        node._connections['0']._spawn.sendline.assert_called_with('command')

    node.get_shell('shell').send_command('command')
    node._connections['0']._spawn.sendline.assert_called_with('command')


def test_default_connection(spawn, node):
    """
    Test that the default_connection property works as expected.
    """

    assert node.default_connection is None

    node.connect()

    assert node.default_connection == '0'

    node.connect(connection='1')

    assert node.default_connection == '0'

    with raises(NonExistingConnectionError):
        node.default_connection = '2'

    node.default_connection = '1'

    assert node.default_connection == '1'


def test_send_command(spawn, node):
    """
    Test that send_command works properly.
    """

    with raises(NonExistingConnectionError):
        node.send_command('command')

    node.connect()

    shell = node.get_shell('shell')

    shell.send_command('command')

    shell._parent_connection._spawn.sendline.assert_called_with('command')

    node.disconnect()

    with raises(DisconnectedError):
        node.send_command('command')

    with raises(NonExistingConnectionError):
        node.send_command('command', connection='3')


def test_get_response(spawn, node):
    """
    Test that get_response works properly.
    """

    node.connect()

    shell = node.get_shell('shell')

    shell.send_command('command')

    shell._parent_connection._spawn.configure_mock(
        **{'before.decode.return_value': 'response'}
    )

    assert shell.get_response() == 'response'

    shell._parent_connection._spawn.before.decode.assert_called_with(
        encoding=shell._encoding, errors=shell._errors
    )


def test_non_existing_connection(spawn, node):
    """
    Test that a non existing connection is detected when there is an attempt to
    use it.
    """

    node.connect()
    node.connect(connection='1')

    with raises(NonExistingConnectionError):
        node.is_connected(connection='2')


def test_is_connected(spawn, node):
    """
    Test that is_connected returns correctly.
    """

    with raises(NonExistingConnectionError):
        node.is_connected()

    node.connect()

    assert node.is_connected()

    node.connect(connection='1')

    assert node.is_connected(connection='1')


def test_disconnect(spawn, node):
    """
    Test that disconnect works properly.
    """

    node.connect()
    node.disconnect()

    assert not node.is_connected()

    with raises(AlreadyDisconnectedError):
        node.disconnect()

    node.connect(connection='1')
    node.disconnect(connection='1')

    assert not node.is_connected(connection='1')

    with raises(AlreadyDisconnectedError):
        node.disconnect(connection='1')


def test_setup_shell(spawn, node):
    """
    Test that _setup_shell works properly.
    """

    node.connect()

    initial_prompt = node.get_shell('shell')._initial_prompt

    node._connections[
        node._default_connection
    ]._spawn.sendline.assert_has_calls(
        [
            call('stty -echo'),
            call('export PS1={}'.format(PExpectBashShell.FORCED_PROMPT))
        ]
    )

    assert node.get_shell('shell')._initial_prompt == initial_prompt

    node.connect(connection='1')

    node._connections['1']._spawn.sendline.assert_has_calls(
        [
            call('stty -echo'),
            call('export PS1={}'.format(PExpectBashShell.FORCED_PROMPT))
        ]
    )

    assert node.get_shell('shell')._initial_prompt == initial_prompt


def test_connect_disconnect_connect(spawn, node):
    """
    Test that the connect - disconnect - connect use case works properly.
    """
    for connection in [None, '1']:

        # Connection is not created yet
        with raises(NonExistingConnectionError):
            node.is_connected(connection=connection)

        # First shell call and explicit reconnection case
        for i in [1, 2]:
            node.connect(connection=connection)
            assert node.is_connected(connection=connection)

            node.get_shell('shell', connection=connection).send_command(
               'command'.format(i))
            node._connections[
                connection or '0'
            ]._spawn.sendline.assert_called_with(
                'command'.format(i)
            )
            assert node.is_connected(connection=connection)

            node.disconnect(connection=connection)
            assert not node.is_connected(connection=connection)

        # Second case, automatic reconnect
        node._connections[connection or '0']._auto_reconnect = True

        assert not node.is_connected(connection=connection)
        node.get_shell('shell', connection=connection).send_command(
            'a call to'.format(i))
        node._connections[
            connection or '0'
        ]._spawn.sendline.assert_called_with(
            'a call to'
        )
        assert node.is_connected(connection=connection)


def test_active_shell(spawn, node):
    """
    Test the handling of the active shell
    """

    node.connect()
    connection = node.get_connection(node.default_connection)

    shell_1 = connection.get_shell('shell')
    shell_2 = connection.get_shell('shell_2')

    assert connection._active_shell == shell_1
    assert shell_1._parent_connection._active_shell == shell_1
    assert shell_2._parent_connection._active_shell == shell_1

    shell_2.send_command('command')

    assert connection._active_shell == shell_2
    assert shell_1._parent_connection._active_shell == shell_2
    assert shell_2._parent_connection._active_shell == shell_2

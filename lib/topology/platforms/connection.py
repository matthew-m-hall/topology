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
Base connection module for topology.

This module defines the functionality that a Topology Connection must
implement.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from collections import OrderedDict
from abc import ABCMeta, abstractmethod
from pexpect import spawn as Spawn  # noqa
from six import add_metaclass, iterkeys
from pexpect import EOF

from topology.platforms.shell import BaseShell

from topology.logging import get_logger


class AlreadyConnectedError(Exception):
    """
    Exception raised by the shell API when trying to create a connection
    already created.
    """
    def __init__(self, connection):
        super(Exception, self).__init__(
            self, '{} is already connected.'.format(connection.identifier)
        )


class AlreadyDisconnectedError(Exception):
    """
    Exception raised by the shell API when trying to disconnect an already
    disconnected connection.
    """
    def __init__(self, connection):
        super(Exception, self).__init__(
            self, '{} is already disconnected.'.format(connection.identifier)
        )


@add_metaclass(ABCMeta)
class HighLevelShellAPI(object):
    """
    API used to interact with node shells.

    """

    @property
    def default_shell(self):
        raise NotImplementedError('default_shell')

    @default_shell.setter
    def default_shell(self, value):
        raise NotImplementedError('default_shell.setter')

    @abstractmethod
    def available_shells(self):
        """
        Get the list of available shells.

        :return: The list of all available shells. The first element is the
         default (if any).
        :rtype: List of str.
        """

    @abstractmethod
    def send_command(self, cmd, shell=None, silent=False):
        """
        Send a command to this engine node.

        :param str cmd: Command to send.
        :param str shell: Shell that must interpret the command.
         ``None`` for the default shell. Is up to the engine node to
         determine what its default shell is.
        :param bool silent: True to call the shell logger, False
         otherwise.

        :return: The response of the command.
        :rtype: str
        """

    def __call__(self, *args, **kwargs):
        return self.send_command(*args, **kwargs)


@add_metaclass(ABCMeta)
class LowLevelShellAPI(object):
    """
    API used to interact with low level shell objects.
    """

    @abstractmethod
    def use_shell(self, shell):
        """
        Create a context manager that allows to use a different default shell
        in a context, including access to it's low-level shell object.

        :param str shell: The default shell to use in the context.

        Assuming, for example, that a node has two shells:
        ``bash`` and ``python``:

        ::

            with mynode.use_shell('python') as python:
                # This context manager sets the default shell to 'python'
                mynode('from os import getcwd')
                cwd = mynode('print(getcwd())')

                # Access to the low-level shell API
                python.send_command('foo = (', matches=['... '])
                ...
        """

    @abstractmethod
    def get_shell(self, shell):
        """
        Get the shell object associated with the given name.

        The shell object allows to access the low-level shell API.

        :param str shell: Name of the shell.

        :return: The associated shell object.
        :rtype: BaseShell
        """


@add_metaclass(ABCMeta)
class BaseConnection(HighLevelShellAPI, LowLevelShellAPI):
    """
    Base engine connection class.

    This class represent the base interface that engine connetions require to
    implement.

    See the :doc:`Plugins Development Guide </plugins>` for reference.

    The behavior that these connections must follow is this one:

    #. New connections to the shell are created by calling the ``connect``
       command of the node with the name of the connection to be created
       defined in its ``connection`` attribute.
    #. Connections can be disconnected by calling the ``disconnect`` command of
       the node.
    #. Connections can be either connected or disconnected.
    #. Existing disconnected connections can be connected again by calling the
       ``connect`` command of the connection.
    #. An attempt to connect an already connected shell or to disconnect an
       already disconnected shell will raise an exception.
    #. These node will have a *default* connection that will be used if the
       ``connection`` attribute of the node methods is set to ``None``.
    #. The default connection will be set to ``None`` when the node is
       initialized.
    #. If the default connection is ``None`` and the ``connect`` command is
       called, it will set the default connection as the connection used in
       this call. Also, if the previous condition is true and if this
       connection attribute is set to ``None``, the name of the default
       connection will be set to '0'.
    #. Every time any operation with the node is attempted, a connection needs
       to be specified, if this connection is specified to be ``None``, the
       *default* connection of the shell will be used.
    #. If any method other than ``connect`` is called with
       a connection that is not defined yet, an exception will be raised.

    The behavior of these operations is defined in the following methods,
    implementations of this class are expected to behave as defined here.

    Be aware that the method ``_register_shell`` of the connection will add two
    attributes to the shell objects:

    #. ``_name``: name of the shell, the matching key of the connections's
       dictionary of shells
    #. ``_connection``: connection object that holds the shell object

    The ``_register_shell`` method is usually called in the connections's'
    ``__init__``.

    :param str identifier: User identifier of the connection.

    :var identifier: User identifier of the connection. Please note that
     this identifier is unique with respect to the node.
    :var metadata: Additional metadata (kwargs leftovers).
    """

    @abstractmethod
    def __init__(self, identifier, parent_node, **kwargs):
        self.identifier = identifier
        self.parent_node = parent_node
        self.metadata = kwargs


@add_metaclass(ABCMeta)
class CommonConnection(BaseConnection):
    """
    Base engine connection class with a common base implementation.

    This class provides a basic common implementation for managing shells.
    Internal ordered dictionaries handles the keys for shell objects that
    implement the logic for those shells.

    Child classes will then only require to call registration methods
    :meth:`_register_shell`.

    See :class:`BaseConnection`.
    """

    @abstractmethod
    def __init__(self, identifier, parent_node, initial_command=None,
                 initial_prompt='\w+@.+:.+[#$]', user=None,
                 user_match='[uU]ser:', password=None,
                 password_match='[pP]assword:', timeout=None, spawn_args=None,
                 auto_reconnect=False, **kwargs):
        super(CommonConnection, self).__init__(
            identifier, parent_node, **kwargs)

        # Shell(s) API
        self._default_shell = None
        self._active_shell = None
        self._shells = OrderedDict()
        self._spawn = None
        self._initial_command = initial_command
        self._initial_prompt = initial_prompt
        self._user = user
        self._user_match = user_match
        self._password = password
        self._password_match = password_match
        self._timeout = timeout or -1
        self._auto_reconnect = auto_reconnect
        self._via_connection = None

        pnode = parent_node.identifier if parent_node else ""

        self._pexpect_logger = get_logger(
            OrderedDict([
                ('node_identifier', pnode),
                ('connection', self.identifier)
            ]),
            category='pexpect'
        )
        self._connection_logger = get_logger(
            OrderedDict([
                ('node_identifier', pnode),
                ('connection', self.identifier)
            ]),
            category='connection'
        )

        # Doing this to avoid having a mutable object as default value in the
        # arguments.
        if spawn_args is None:
            self._spawn_args = {'env': {'TERM': 'dumb'}, 'echo': False}
        else:
            self._spawn_args = spawn_args

        self._register_shells()

    def is_connected(self):
        """
        check the connection status

        :rtype: boolean
        :return: true if connected
        """
        return self._spawn and self._spawn.isalive()

    @abstractmethod
    def _get_connect_command(self):
        """
        Get the command to be used when connecting to the node.

        This must be defined by any child connection class as the return value
        of this function will define all the connection details to use when
        creating a connection to the node.

        :rtype: str
        :return: The command to be used when connecting to the node.
        """

    def login(self):
        """
        This method must start by expecting the first prompt of the connection
        and end expecting the final prompt of the loggin. Any overide of this
        functon must do the same.
        """
        def expect_sendline(prompt, command):
            if prompt is not None and command is not None:
                self._spawn.expect(
                    prompt, timeout=self._timeout
                )
                self._spawn.sendline(command)

        # If connection is via user
        expect_sendline(self._user_match, self._user)

        # If connection is via password
        expect_sendline(self._password_match, self._password)

        # If connection is via initial command
        expect_sendline(self._initial_prompt, self._initial_command)

        # Wait for command response to match the prompt
        self._spawn.expect(
            self._initial_prompt, timeout=self._timeout
        )

    def logout(self):
        """
        Set the active shell to the defult shell,
        call exit on the shell to get to the root context
        call exit on the connection
        """
        self.active_shell = self.get_shell(self.default_shell)
        self.active_shell.exit()
        self._spawn.sendline('exit')
        self._spawn.expect([EOF, '.+[#>$@]\s?'])

    def connect(self, via_connection=None):
        """
        See :meth:`BaseShell.connect` for more information.
        """

        if self.is_connected():
            raise AlreadyConnectedError(self)

        if via_connection:
            self._via_connection = via_connection
            self._spawn = via_connection._spawn
            self._spawn.sendline(self._get_connect_command().strip())
        else:
            # Inject framework logger to the spawn object
            spawn_args = {'logfile': self._pexpect_logger}

            # Create a child process
            spawn_args.update(self._spawn_args)

            self._spawn = Spawn(
                self._get_connect_command().strip(), **spawn_args
            )

        # Add a connection logger
        self._spawn._connection_logger = self._connection_logger

        self.login()

        # Setup shell before using it
        shell = self.get_shell(self.default_shell)
        shell._setup_shell()

    def disconnect(self):
        """
        See :meth:`BaseShell.disconnect` for more information.
        """
        if not self._spawn.isalive():
            raise AlreadyDisconnectedError(self)

        self.logout()

        if(self._via_connection):
            self._via_connection.disconnect()
        else:
            self._spawn.close()

    # HighLevelShellAPI

    @property
    def default_shell(self):
        return self._default_shell

    @default_shell.setter
    def default_shell(self, value):
        if value not in self._shells:
            raise KeyError(
                'Cannot set default shell. Unknown shell "{}"'.format(value)
            )
        self._default_shell = value

    @property
    def active_shell(self):
        return self._active_shell

    @active_shell.setter
    def active_shell(self, shellobj):
        if self._active_shell != shellobj:
            self._active_shell.exit()
            shellobj.enter()
            self._active_shell = shellobj

    def available_shells(self):
        """
        Implementation of the public ``available_shells`` interface.

        This method will just list the available keys in the internal ordered
        dictionary.

        See :meth:`HighLevelShellAPI.available_shells` for more information.
        """
        return list(iterkeys(self._shells))

    def send_command(self, cmd, shell=None, silent=False):
        """
        Implementation of the public ``send_command`` interface.

        This method will lookup for the shell argument in an internal ordered
        dictionary to fetch a shell object to delegate the command to.
        If None is provided, the default shell of the node will be used.

        See :meth:`HighLevelShellAPI.send_command` for more information.
        """

        # Check at least one shell is available
        if not self._shells:
            raise Exception(
                'Node {} doens\'t have any shell.'.format(self.identifier)
            )

        # Check requested shell is supported
        if shell is None:
            shell = self._default_shell
        elif shell not in self._shells.keys():
            raise Exception(
                'Shell {} is not supported.'.format(shell)
            )

        _shell = self.get_shell(shell)

        _shell.send_command(cmd, silent=silent)

        response = _shell.get_response(silent=silent)

        return response

    def _register_shell(self, name, shellobj):
        """
        Allow plugin developers to register a shell when initializing
        a connection. The first shell registered will be set as the default
        shell and the active shell.

        :param str name: Unique name of the shell to register.
        :param BaseShell shellobj: The shell object to register.
        """
        assert isinstance(shellobj, BaseShell)

        if name in self._shells:
            raise KeyError('Shell "{}" already registered'.format(name))
        if not name:
            raise KeyError('Invalid name for shell "{}"'.format(name))

        self._shells[name] = shellobj

        if self._active_shell is None:
            self._active_shell = shellobj

        if self._default_shell is None:
            self._default_shell = name

        shellobj._register_connection(self, name)

    def _register_shells(self):
        """
        Create and register the shell object on this connection.

        By default we ask the node to register the shells. This function
        should be overridden when shells differ for connection type
        """

        self.parent_node._register_shells(self)

    # LowLevelShellAPI

    def get_shell(self, shell):
        """
        Implementation of the public ``get_shell`` interface.

        This method will return the shell object associated with the given
        shell name.

        See :meth:`LowLevelShellAPI.get_shell` for more information.
        """
        if shell not in self._shells:
            raise KeyError(
                'Unknown shell "{}"'.format(shell)
            )
        return self._shells[shell]

    def use_shell(self, shell):
        """
        Implementation of the public ``use_shell`` interface.

        This method allows to create contexts (using a Python Context Manager)
        that allows the user, by the means of a ``with`` statement, to create
        a context to use a specific shell in it.

        See :meth:`LowLevelShellAPI.use_shell` for more information.
        """
        return ShellContext(self, shell)


class ShellContext(object):
    """
    Context Manager class for default shell swapping.

    This object will handle the swapping of the default shell when in and out
    of the context.

    :param BaseConnection connection: connection to swap default shell on
    :param str shell_to_use: Shell to use during the context session.
    """

    def __init__(self, connection, shell_to_use):
        self._connection = connection
        self._shell_to_use = shell_to_use
        self._default_shell = connection.default_shell

    def __enter__(self):
        self._connection.default_shell = self._shell_to_use
        return self._connection.get_shell(self._default_shell)

    def __exit__(self, type, value, traceback):
        self._connection.default_shell = self._default_shell


__all__ = [
    'AlreadyConnectedError',
    'AlreadyDisconnectedError',
    'HighLevelShellAPI',
    'LowLevelShellAPI',
    'BaseConnection',
    'CommonConnection',
    'ShellContext'
]

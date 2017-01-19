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
topology shell api module.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from re import sub as regex_sub
from abc import ABCMeta, abstractmethod

from six import add_metaclass


TERM_CODES_REGEX = r'\x1b[E|\[](\?)?([0-9]{1,2}(;[0-9]{1,2})?)?[m|K|h|H|r]?'
"""
Regular expression to match terminal control codes.

A terminal control code is a special sequence of characters that sent by some
applications to control certain features of the terminal. It is responsibility
of the terminal application (driver) to interpret those control codes.
However, when using pexpect, the incoming buffer will still have those control
codes and will not interpret or do anything with them other than store them.
This regular expression allows to remove them as they are unneeded for the
purpose of executing commands and parsing their outputs
(unless proven otherwise).

``\\x1b``
  Match prefix that indicates the next characters are part of a terminal code
  string.
``[E|\\[]``
  Match either ``E`` or ``[``.
``(\\?)?``
  Match zero or one ``?``.
``([0-9]{1,2}``
  Match 1 or 2 numerical digits.
``(;[0-9]{1,2})?``
  Match zero or one occurences of the following pattern: ``;`` followed by 1
  or 2 numerical digits.
``)?``
  Means the pattern composed by the the last 2 parts above can be found zero or
  one times.
``[m|K|h|H|r]?``
  Match zero or one occurrences of either ``m``, ``K``, ``h``, ``H`` or ``r``.
"""


class DisconnectedError(Exception):
    """
    Exception raised by the shell API when trying to perform an operation on a
    disconnected connection.
    """
    def __init__(self, connection_identifier):
        super(Exception, self).__init__(
            self, '{} is disconnected.'.format(connection_identifier)
        )


@add_metaclass(ABCMeta)
class BaseShell(object):
    """
    Base shell class for Topology nodes.

    This class represents a base interface for a Topology node shell. This
    shell is expected to be an interactive shell, where an expect-like
    mechanism is to be used to find a terminal prompt that signals the end of
    the terminal response to a command sent to it.

    Shells of this kind also represent an actual shell in the node's
    connection. This means that one of these objects is expected to exist
    for every one of the shells in the node's connection.

    """

    @abstractmethod
    def send_command(
        self, command, matches=None, newline=True, timeout=None, silent=False
    ):
        """
        Send a command to the shell.

        :param str command: Command to be sent to the shell.
        :param list matches: List of strings that may be matched by the shell
         expect-like mechanism as prompts in the command response.
        :param bool newline: True to append a newline at the end of the
         command, False otherwise.
        :param int timeout: Amount of time to wait until a prompt match is
         found in the command response.
        :param bool silent: True to call the connection logger, False
         otherwise.
        """

    @abstractmethod
    def get_response(self, silent=False):
        """
        Get a response from the shell connection.

        This method can be used to add extra processing to the shell response
        if needed, cleaning up terminal control codes is an example.

        :param bool silent: True to call the connection logger, False
         otherwise.
        :rtype: str
        :return: Shell response to the previously sent command.
        """

    def execute(self, command):
        """
        Executes a command.

        This is just a convenient method that sends a command to the shell
        using send_command and returns its response using get_response.

        :param str command: Command to be sent.
        :rtype: str
        :return: Shell response to the command being sent.
        """
        self.send_command(command)
        return self.get_response()

    def __call__(self, command, ):
        return self.execute(command)

    def _setup_shell(self):
        """
        Method called by connection to perform any initial actions on a shell
        before use.
        """

    @abstractmethod
    def _register_connection(self, connection, shell_name):
        """
        Register the connection and the assigned shell name on that
        connection in the shell.

        :param str connection: The parent connection.
        :param str shell_name: Shell name given in the node to this shell.
        """

    @abstractmethod
    def enter(self):
        """
        enter the shell from the default shell.

        The default shell for a node type will do nothing in this function
        This method is called when is necessary to switch between shells
        """

    @abstractmethod
    def exit(self):
        """
        Exits to the default shell.

        The default shell for a node type will do nothing in this function
        This method is called when is necessary to switch between shells
        """


@add_metaclass(ABCMeta)
class PExpectShell(BaseShell):
    """
    Implementation of the BaseShell class using pexpect.

    This class provides a convenient implementation of the BaseShell using
    the pexpect package. The only thing needed for child classes is to define
    the command that will be used to connect to the shell.

    See :class:`BaseShell`.

    :param str prompt: Regular expression that matches the shell prompt.
    :param str initial_command: Command that is to be sent at the beginning of
     the connection.
    :param str initial_prompt: Regular expression that matches the initial
     prompt. This value will be used to match the prompt before calling private
     method ``_setup_shell()``.
    :param str prefix: The prefix to be prepended to all commands sent to this
     shell.
    :param int timeout: Default timeout to use in send_command.
    :param str encoding: Character encoding to use when decoding the shell
     response.
    :param bool try_filter_echo: On platforms that doesn't support some way of
     turning off the echo of the command try to filter the echo from the output
     by removing the first line of the output if it match the command.
    :param auto_connect bool: Enable the automatic creation of a connection
     when ``send_command`` is called if the connection does not exist or is
     disconnected.
    :param dict spawn_args: Arguments to be passed to the Pexpect spawn
     constructor. If this is left as ``None``, then
     ``env={'TERM': 'dumb'}, echo=False`` will be passed as keyword
     arguments to the spawn constructor.
    :param str errors: Handling of decoding errors in ``get_response``. The
     values available are the same ones that the ``decode`` method of a bytes
     object expects in its ``error`` keyword argument. Defaults to ``ignore``.
    """

    def __init__(
            self, prompt, initial_prompt=None,
            prefix=None, timeout=None, encoding='utf-8',
            try_filter_echo=True,
            errors='ignore', **kwargs):

        self._prompt = prompt
        self._initial_prompt = initial_prompt

        self._prefix = prefix
        self._timeout = timeout or -1
        self._encoding = encoding
        self._try_filter_echo = try_filter_echo
        self._command_logger = None
        self._response_logger = None
        self._parent_connection = None
        self._shell_name = None
        self._errors = errors

        self._last_command = None

        # Set the initial prompt not specified
        if self._initial_prompt is None:
            self._initial_prompt = prompt

        super(PExpectShell, self).__init__(**kwargs)

    def send_command(
        self, command, matches=None, newline=True, timeout=None, silent=False
    ):
        """
        See :meth:`BaseShell.send_command` for more information.
        """

        # If auto re-connect is false, fail if connection is disconnected
        if not self._parent_connection._auto_reconnect:
            if not self._parent_connection.is_connected():
                raise DisconnectedError(self._parent_connection.identifier)
        # If auto re-connect is true, always reconnect unless already connected
        else:
            if not self._parent_connection.is_connected():
                self._parent_connection.connect()

        self._parent_connection.active_shell = self

        spawn = self._parent_connection._spawn

        # Create possible expect matches
        if matches is None:
            matches = [self._prompt]

        # Append prefix if required
        if self._prefix is not None:
            command = '{}{}'.format(self._prefix, command)

        # Save last command in cache to allow to remove echos in get_response()
        self._last_command = command

        # Send line and expect matches
        if newline:
            spawn.sendline(command)
        else:
            spawn.send(command)

        # Log log_send_command
        if not silent:
            spawn._connection_logger.log_send_command(
                self._shell_name, command, matches, newline, timeout
            )

        # Expect matches
        if timeout is None:
            timeout = self._timeout

        match_index = spawn.expect(
            matches, timeout=timeout
        )
        return match_index

    def get_response(self, silent=False):
        """
        See :meth:`BaseShell.get_response` for more information.
        """

        if not self._parent_connection.is_connected():
            raise DisconnectedError(self._parent_connection.identifier)

        spawn = self._parent_connection._spawn

        # Convert binary representation to unicode using encoding
        text = spawn.before.decode(
            encoding=self._encoding, errors=self._errors
        )

        # Remove leading and trailing whitespaces and normalize newlines
        text = text.strip().replace('\r', '')

        # Remove control codes
        text = regex_sub(TERM_CODES_REGEX, '', text)

        # Split text into lines
        lines = text.splitlines()

        # Delete buffer with output right now, as it can be very large
        del text

        # Remove echo command if it exists
        if self._try_filter_echo and \
                lines and self._last_command is not None \
                and lines[0].strip() == self._last_command.strip():
            lines.pop(0)

        response = '\n'.join(lines)

        # Log response
        if not silent:
            spawn._connection_logger.log_get_response(
                self._shell_name, response)

        return response

    def _register_connection(self, connection, shell_name):
        self._parent_connection = connection
        self._shell_name = shell_name


class PExpectBashShell(PExpectShell):
    """
    Custom shell class for Bash.

    This custom base class will setup the prompt ``PS1`` to the
    ``FORCED_PROMPT`` value of the class and will disable the echo of the
    device by issuing the ``stty -echo`` command. All this is done in the
    ``_setup_shell()`` call, which is overriden by this class.
    """
    FORCED_PROMPT = '@~~==::BASH_PROMPT::==~~@'

    def __init__(self, initial_prompt='\w+@.+:.+[#$] ', try_filter_echo=False,
                 **kwargs):

        super(PExpectBashShell, self).__init__(
            PExpectBashShell.FORCED_PROMPT,
            initial_prompt=initial_prompt,
            try_filter_echo=try_filter_echo,
            **kwargs
        )

    def _setup_shell(self):
        """
        Overriden setup function that will disable the echo on the device on
        the shell and set a pexpect-safe prompt.
        """

        spawn = self._parent_connection._spawn

        # Remove echo
        spawn.sendline('stty -echo')
        spawn.expect(
            self._initial_prompt, timeout=self._timeout
        )

        # Change prompt to a pexpect secure prompt
        spawn.sendline(
            'export PS1={}'.format(PExpectBashShell.FORCED_PROMPT)
        )
        self._prompt = PExpectBashShell.FORCED_PROMPT

        spawn.expect(
            self._prompt, timeout=self._timeout
        )

    def enter(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.enter` for more
        information.
        """
        pass

    def exit(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.exit` for more
        information.
        """
        pass

__all__ = [
    'TERM_CODES_REGEX',
    'DisconnectedError',
    'BaseShell',
    'PExpectShell',
    'PExpectBashShell',
]

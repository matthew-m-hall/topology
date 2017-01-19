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
Base platform engine module for topology.

This module defines the functionality that a Topology Engine Node must
implement to be able to create a network using a specific environment.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

import logging
from collections import OrderedDict
from abc import ABCMeta, abstractmethod

from six import add_metaclass, iterkeys

from topology.platforms.service import BaseService
from topology.platforms.connection import HighLevelShellAPI, LowLevelShellAPI
from topology.libraries.manager import LibsProxy

log = logging.getLogger(__name__)


class NonExistingConnectionError(Exception):
    """
    Exception raised by the connection API when trying to use a non-existent
    connection.
    """
    def __init__(self, connection):
        super(Exception, self).__init__(
            self, 'Non-existing connection {}.'.format(connection)
        )


class UnsupportedConnectionTypeError(Exception):
    """
    Exception raised by the connection API when trying to use an unsupported
    connection type.
    """
    def __init__(self, connection_type):
        super(Exception, self).__init__(
            self, '{} connections are not supported on this node.'
            .format(connection_type)
        )


@add_metaclass(ABCMeta)
class ConnectionAPI(object):
    """
    API used to manage connections
    """

    @property
    def default_connection(self):
        raise NotImplementedError('default_connection')

    @default_connection.setter
    def default_connection(self, connection):
        raise NotImplementedError('default_connection.setter')

    @abstractmethod
    def is_connected(self, connection=None):
        """
        Shows if the connection to the n is active.

        :param str connection: Name of the connection to check if connected. If
         not defined, the default connection will be checked.
        :rtype: bool
        :return: True if there is an active connection to the shell, False
         otherwise.
        """

    @abstractmethod
    def login(self, connection=None):
        """
        Login on the given connection
        """

    @abstractmethod
    def connect(self, connection=None, connection_type=None,
                via_node=None):
        """
        Creates a connection to the node.

        :param str connection: Name of the connection to be created. If not
         defined, an attempt to create the default connection will be done. If
         the default connection is already connected, an exception will be
         raised. If defined in the call but no default connection has been
         defined yet, this connection will become the default one. If the
         connection is already connected, an exception will be raised.
        :param str connection_type: The connection type. If the given
         connection type not supported by the node an Exeption will be raised.
         If a type is specified and the connection already exists, an Exception
         will be raised
        """

    @abstractmethod
    def disconnect(self, connection=None):
        """
        Terminates a connection to the shell.

        :param str connection: Name of the connection to be disconnected. If
         not defined, the default connection will be disconnected. If the
         default connection is disconnected, no attempt will be done to define
         a new default connection, the user will have to either create a new
         default connection by calling ``connect`` or by defining another
         existing connection as the default one.
        """

    @abstractmethod
    def available_connection_types(self):
        """
        get a list of connection types avaliable

        This method will just list the available keys in the internal ordered
        dictionary.
        """

    @abstractmethod
    def _get_connection_type(self, connection_type=None):
        """
        get a connection class to instantiate. If the type is
        not provided the default connection type for the node
        will be returned. If the type requested is not registered
        with the node, an exception will be raised

        :param str connection_type: The connection type. If not specified, the
         default connection type is returned. If the given connection
         type not supported by the node an Exeption will be raised.
        """

    @abstractmethod
    def available_connections(self):
        """
        get a list of the connection that have been made

        This method will just list the available keys in the internal ordered
        dictionary.
        """

    @abstractmethod
    def get_connection(self, connection=None):
        """
        Get the connection object for the given connection name.

        :param str connection: Name of the connection.
        :rtype: BaseConnection
        :return: The the connection objectthat handles the connection.
        """


@add_metaclass(ABCMeta)
class ServicesAPI(object):
    """
    API to gather information and connection parameters to a node services.
    """

    @abstractmethod
    def available_services(self):
        """
        Get the list of all available services.

        :return: The list of all available services.
        :rtype: List of str.
        """

    @abstractmethod
    def get_service(self, service):
        """
        Get the service object associated with the given name.

        The service object holds all connection parameters.

        :param str service: Name of the service.

        :return: The associated service object.
        :rtype: BaseService
        """

    @abstractmethod
    def _register_service(self, name, serviceobj):
        """
        Allow plugin developers to register a service when initializing a node.

        :param str name: Unique name of the service to register.
        :param serviceobj: The service object to register with all connection
         related parameters.
        :type serviceobj: BaseService
        """

    @abstractmethod
    def _get_services_address(self):
        """
        Returns the IP or FQDN of the node so users can connect to the
        registered services.

        .. note::

           This method should be implemented by the platform engine base node.

        :returns: The IP or FQDM of the node.
        :rtype: str
        """


@add_metaclass(ABCMeta)
class StateAPI(object):
    """
    API to control the enable/disabled state of a node.
    """

    @abstractmethod
    def is_enabled(self):
        """
        Query if the node is enabled.

        :return: True if the node is enabled, False otherwise.
        :rtype: bool
        """

    @abstractmethod
    def enable(self):
        """
        Enable this node.

        An enabled node allows communication.
        """

    @abstractmethod
    def disable(self):
        """
        Disable this node.

        A disabled node doesn't allow communication.
        """


@add_metaclass(ABCMeta)
class BaseNode(ConnectionAPI, HighLevelShellAPI, LowLevelShellAPI,
               ServicesAPI, StateAPI):
    """
    Base engine node class.

    This class represent the base interface that engine nodes require to
    implement.

    See the :doc:`Plugins Development Guide </plugins>` for reference.

    :param str identifier: User identifier of the engine node.

    :var identifier: User identifier of the engine node. Please note that
     this identifier is unique in the topology being built, but is not unique
     in the execution system.
    :var metadata: Additional metadata (kwargs leftovers).
    :var ports: Mapping between node ports and engine ports. This variable
     is populated by the :class:`topology.manager.TopologyManager`.
    """

    @abstractmethod
    def __init__(self, identifier, **kwargs):
        self.identifier = identifier
        self.metadata = kwargs
        self.ports = OrderedDict()


@add_metaclass(ABCMeta)
class CommonNode(BaseNode):
    """
    Base engine node class with a common base implementation.

    This class provides a basic common implementation for managing connections
    and services. Internal ordered dictionaries handles the keys for
    connection types and services objects that implements the logic for those
    connections or services.

    Child classes will then only require to call registration methods
    :meth:`_register_connection_type` and :meth:`_register_service`.

    In particular, this class implements support for Communication Libraries
    using class :class:`LibsProxy` that will hook with all available libraries.

    See :class:`BaseNode`.

    .. note::

       The method :meth: ``_get_services_address`` should be provided by the
       Platform Engine base node.
    """

    @abstractmethod
    def __init__(self, identifier, **kwargs):
        super(CommonNode, self).__init__(identifier, **kwargs)

        # connections API
        self._default_connection = None
        self._connections = OrderedDict()
        self._default_connection_type = None
        self._connection_types = OrderedDict()

        # Services API
        self._services = OrderedDict()

        # State API
        self._enabled = True

        # Communication Libraries support
        self.libs = LibsProxy(self)

    # ConnectionAPI

    @property
    def default_connection(self):
        return self._default_connection

    @default_connection.setter
    def default_connection(self, connection):
        if connection not in self._connections:
            raise NonExistingConnectionError(connection)
        self._default_connection = connection

    def is_connected(self, connection=None):
        """
        See :meth:`ConnectionAPI.is_connected` for more information.
        """
        return self.get_connection(connection).is_connected()

    def login(self, connection=None):
        """
        Login on the given connection
        """
        self.get_connection(connection).login()

    def connect(self, connection=None, connection_type=None,
                via_node=None, **kwargs):
        """
        See :meth:`ConnectionAPI.connect` for more information.
        """
        connection = connection or self._default_connection or '0'

        if connection not in self._connections:
            typeobj = self._get_connection_type(connection_type)
            new_connection = typeobj(connection, self, **kwargs)
            self._connections[connection] = new_connection

        try:
            via_connection = None

            if(via_node and via_node is not self):
                via_name = 'to_{}_{}'.format(self.identifier, connection)
                via_node.connect(connection=via_name, via_node=via_node)
                via_connection = via_node.get_connection(via_name)

            self.get_connection(connection).connect(
                via_connection=via_connection
            )
        except:
            # Always remove a bad connection if it failed
            del self._connections[connection]
            raise

        # Set connection as default connection if required
        if self.default_connection is None and via_node is None:
            self.default_connection = connection

    def disconnect(self, connection=None):
        """
        See :meth:`ConnectionAPI.disconnect` for more information.
        """
        self.get_connection(connection).disconnect()

    def disconnect_all(self):
        """
        disconnect all the connections to this node
        """
        for connection in self.available_connections():
            conn = self.get_connection(connection)
            if conn.is_connected():
                conn.disconnect()

    def available_connection_types(self):
        """
        See :meth:`ConnectionAPI.available_connection_types` for more
        information.
        """
        return list(iterkeys(self._connection_types))

    def _get_connection_type(self, connection_type=None):
        """
        See :meth:`ConnectionAPI._get_connection_type` for more information.
        """

        connection_type = connection_type or self._default_connection_type

        if connection_type not in self._connection_types:
            raise UnsupportedConnectionTypeError(connection_type)

        return self._connection_types[connection_type]

    def available_connections(self):
        """
        See :meth:`ConnectionAPI.available_connections` for more information.
        """
        return list(iterkeys(self._connections))

    def get_connection(self, connection=None):
        """
        See :meth:`ConnectionAPI.get_connection` for more information.
        """

        connection = connection or self._default_connection or '0'

        if connection not in self._connections:
            raise NonExistingConnectionError(connection)

        return self._connections[connection]

    def _register_connection_type(self, name, typeobj):
        """
        Allow plugin developers to register a connection type when initializing
        a node. the first type registered will be set as the default type

        :param str name: Unique name of the connection type to register.
        :param type type: The connection type to register.
        """
        assert isinstance(typeobj, type)

        if name in self._connection_types:
            raise KeyError(
                'Connection type "{}" already registered'.format(name))
        if not name:
            raise KeyError('Invalid name for connection "{}"'.format(name))

        self._connection_types[name] = typeobj

        if self._default_connection_type is None:
            self._default_connection_type = name

    @abstractmethod
    def _register_shells(self, connectionobj):
        """
        Create and register shells on the given connection
        This funcion should to be called by the connections
        _register_shells function.
        This function should then call the connections
        _register_shell function for each shell to register
        """
        raise NotImplementedError('_register_shells')

    # HighLevelShellAPI

    @property
    def default_shell(self):
        return self.get_connection(self.default_connection).default_shell()

    @default_shell.setter
    def default_shell(self, value):
        self.get_connection(self.default_connection).default_shell(value)

    def available_shells(self, connection=None):
        """
        Implementation of the public ``available_shells`` interface.

        This method will just list the available keys in the internal ordered
        dictionary.

        See :meth:`HighLevelShellAPI.available_shells` for more information.
        """
        return self.get_connection(connection).available_shells()

    def send_command(self, cmd, shell=None, silent=False, connection=None):
        """
        Implementation of the public ``send_command`` interface.

        This method will lookup for the shell argument in an internal ordered
        dictionary to fetch a shell object to delegate the command to.
        If None is provided, the default shell of the node will be used.

        See :meth:`HighLevelShellAPI.send_command` for more information.
        """

        return self.get_connection(connection).send_command(
            cmd, shell=shell, silent=silent
        )

    # LowLevelShellAPI

    def get_shell(self, shell, connection=None):
        """
        Implementation of the public ``get_shell`` interface.

        This method will return the shell object associated with the given
        shell name.

        See :meth:`LowLevelShellAPI.get_shell` for more information.
        """

        return self.get_connection(connection).get_shell(shell)

    def use_shell(self, shell, connection=None):
        """
        Implementation of the public ``use_shell`` interface.

        This method allows to create contexts (using a Python Context Manager)
        that allows the user, by the means of a ``with`` statement, to create
        a context to use a specific shell in it.

        See :meth:`LowLevelShellAPI.use_shell` for more information.
        """

        return self.get_connection(connection).use_shell(shell)

    # ServicesAPI

    def available_services(self):
        """
        Implementation of the public ``available_services`` interface.

        This method will just list the available keys in the internal ordered
        dictionary.

        See :meth:`ServicesAPI.available_services` for more information.
        """
        return list(iterkeys(self._services))

    def get_service(self, service):
        """
        Implementation of the public ``get_service`` interface.

        This method will return the service object associated with the given
        service name.

        See :meth:`ServicesAPI.get_service` for more information.
        """
        if service not in self._services:
            raise KeyError(
                'Unknown service "{}"'.format(service)
            )

        # Set the node address
        serviceobj = self._services[service]
        serviceobj.address = self._get_services_address()

        return serviceobj

    def _register_service(self, name, serviceobj):
        """
        Implementation of the private ``_register_service`` interface.

        This method will lookup for the service name argument in an internal
        ordered dictionary and, if inexistent, it will register the given
        service object.

        See :meth:`ServicesAPI._register_service` for more information.
        """
        assert isinstance(serviceobj, BaseService)

        if name in self._services:
            raise KeyError('Service "{}" already registered'.format(name))
        if not name:
            raise KeyError('Invalid name for service "{}"'.format(name))

        self._services[name] = serviceobj

    # StateAPI

    def is_enabled(self):
        """
        Implementation of the ``is_enabled`` interface.

        This method will just return the internal value of the ``_enabled``
        flag.

        See :meth:`StateAPI.is_enabled` for more information.
        """
        return self._enabled

    def enable(self):
        """
        Implementation of the ``enable`` interface.

        This method will just set the value of the ``_enabled`` flag to True.

        See :meth:`StateAPI.enable` for more information.
        """
        self._enabled = True

    def disable(self):
        """
        Implementation of the ``disable`` interface.

        This method will just set the value of the ``_enabled`` flag to False.

        See :meth:`StateAPI.disable` for more information.
        """
        self._enabled = False


__all__ = [
    'NonExistingConnectionError',
    'UnsupportedConnectionTypeError',
    'ConnectionAPI',
    'ServicesAPI',
    'StateAPI',
    'BaseNode',
    'CommonNode'
]

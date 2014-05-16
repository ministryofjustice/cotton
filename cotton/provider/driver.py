from __future__ import print_function
import importlib
from exceptions import NotImplementedError


class Provider(object):
    def __init__(self, **kwargs):
        """
        initializes connection object
        """
        raise NotImplementedError()

    def status(self):
        raise NotImplementedError()

    def create(self, **kwargs):
        """
        return: server object
        """
        raise NotImplementedError()

    def terminate(self, server):
        raise NotImplementedError()

    def exists(self, name):
        servers = self.filter(name=name)
        return len(servers) > 0

    def filter(self, **kwargs):
        """
        return: list of objects matching filter args
        typically provide should support filter 'name'='foo'
        """
        raise NotImplementedError()

    def info(self, server):
        """
        returns dictionary with info about server (????)
        """
        raise NotImplementedError()

    def host_string(self, server):
        """
        returns host_string in fab format such that we can ssh to server
        """
        raise NotImplementedError()



def provider_class(provider_name):
    """
    returns class object for specific provider_name

    if provider_name is a path (has dots) than it is being imported
    otherwise maps it into:
    aws -> cotton.provider.aws.Driver

    """
    if '.' not in provider_name:
        provider_path = 'cotton.provider.{}.Driver'.format(provider_name)
    else:
        provider_path = provider_name

    #pickup provider module
    provider_module = importlib.import_module('.'.join(provider_path.split('.')[:-1]))

    #pickup provider class
    p_class = getattr(provider_module, provider_path.split('.')[-1])
    assert issubclass(p_class, Provider)
    return p_class


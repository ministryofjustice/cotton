from __future__ import print_function
import pprint
import time
from functools import wraps
from cotton.config import get_env_config
from cotton.fabextras import wait_for_shell
from cotton.provider.driver import provider_class
from cotton.common import *
from cotton.colors import *

def ensure_provider(func):
    """
    Decorator for all functions that need access to cloud
    Make sure that env.environment is initialized beforehand
    """
    @wraps(func)
    def inner(*args, **kwargs):
        start_time = time.clock()
        get_provider_connection()
        ret = func(*args, **kwargs)
        end_time = time.clock()
        print(yellow("Duration: %.2gs" % (end_time-start_time)))
        return ret
    return inner


def get_provider_connection():
    """
    returns initialized provider object and caches it in env.provider
    """
    env_config = get_env_config()
    if not 'provider' in env or not env.provider:
        p_class = provider_class(env_config['driver'])
        env.provider = p_class(**env_config)
    return env.provider


def work_on_vm_name(name):
    """
    updates fabric env context to work on selected vm
    sets:
    env.vm
    env.host_string
    """
    get_provider_connection()
    vms = env.provider.filter(name=name)
    assert len(vms) == 1
    work_on_vm_object(vms[0])
    return env.vm, env.host_string


def work_on_vm_object(server):
    get_provider_connection()
    env.vm = server
    env.host_string = env.provider.host_string(env.vm)
    env.host = env.provider.host_string(env.vm)
    apply_configuration()
    return env.vm, env.host_string


@task
@ensure_provider
def create(name=None, size=None):
    vm = env.provider.create(name=name, size=size)
    work_on_vm_object(vm)
    wait_for_shell()


@task
@ensure_provider
def destroy(name=None):
    work_on_vm_name(name)
    env.provider.terminate(env.vm)


@task
@ensure_provider
def info(name=None):
    work_on_vm_name(name)
    pprint.pprint(env.provider.info(env.vm))


@task
@ensure_provider
def status():
    #TODO: format output
    statuses = env.provider.status()
    for line in statuses:
        pprint.pprint(line)


@task
@ensure_provider
def filter(**kwargs):
    """
    supported args:
    name
    """
    hosts = env.provider.filter(**kwargs)
    assert len(hosts) == 1
    work_on_vm_object(hosts[0])


@task
@ensure_provider
def workon(name=None):
    """
    shortcut to filter host based on name (falls back to env.vm_name)
    """
    if name is None and 'vm_name' in env and env.vm_name:
        name = env.vm_name
    hosts = env.provider.filter(name=name)
    assert len(hosts) == 1
    work_on_vm_object(hosts[0])

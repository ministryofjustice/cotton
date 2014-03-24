"""
basic api

it's recommended to wrap every task with decorator @workon_fallback

@vm_task
def mytask():
    pass

TODO: create task decorator that does the above

"""
from __future__ import print_function
import pprint
import time
from functools import wraps
import fabric.decorators
from cotton.config import get_provider_zone_config

from cotton.provider.driver import provider_class
from cotton.common import *
from cotton.colors import *


def load_provider(func):
    """
    Decorator for all functions that need access to cloud
    Sets: env.provider to initialized driver object
    Make sure that env.provider_zone is initialized beforehand
    """
    @wraps(func)
    def inner(*args, **kwargs):
        start_time = time.time()

        get_provider_connection()
        ret = func(*args, **kwargs)

        end_time = time.time()
        print(yellow("Duration: {:.2f}s".format(end_time - start_time)))
        return ret
    return inner


def get_provider_connection():
    """
    returns initialized provider object and caches it in env.provider
    """
    zone_config = get_provider_zone_config()

    print(green("Selected provider zone config:"))
    print(green(zone_config))

    if not 'provider' in env or not env.provider:
        p_class = provider_class(zone_config['driver'])
        env.provider = p_class(**zone_config)
    return env.provider

def workon_fallback(func):
    raise NotImplementedError, "workon_fallback has been removed. Replace @workon_fallback and @task with just @vm_task"

def vm_task(func):
    """
    Decorate this task as operating on a VM, and set up fabric ``env`` object to target this host.
    Decorator loads provider and configures current host based on env.vm_name
    unless env.vm is already set

    updated variables:
    env.provider
    env.vm
    env.host_string
    env.host
    env.key_filename
    env.user if in provisioning mode
    """

    @wraps(func)
    def inner(*args, **kwargs):
        start_time = time.time()

        if  'vm' not in env or not env.vm:
            assert env.vm_name
            configure_fabric_for_host(env.vm_name)
        ret = func(*args, **kwargs)

        end_time = time.time()
        print(yellow("Duration: {:.2f}s".format(end_time - start_time)))
        return ret
    return fabric.decorators.task(inner)


def configure_fabric_for_host(name):
    """
    loads provider and configures current host based on env.vm_name
    unless env.vm is already set

    updated variables:
    env.provider
    env.vm
    env.host_string
    env.host
    env.key_filename
    env.user if in provisioning mode
    """

    get_provider_connection()
    vms = env.provider.filter(name=name)
    assert len(vms) == 1
    env.vm = vms[0]

    get_provider_connection()
    env.host = env.provider.host_string(env.vm)

    zone_config = get_provider_zone_config()
    if env.provisioning:
        env.key_filename = zone_config['provisioning_ssh_key']
        env.user = zone_config['provisioning_user']
    else:
        if 'ssh_key' in zone_config:
            env.key_filename = zone_config['ssh_key']


@task
@load_provider
def create(name=None, size=None):
    if size:
        print(red("size argument for cotton.api.create is deprecated and will be removed shortly"))
    from cotton.fabextras import wait_for_shell
    vm = env.provider.create(name=name)
    workon_vm_object(vm)
    wait_for_shell()


@vm_task
def destroy():
    env.provider.terminate(env.vm)


@vm_task
def info():
    pprint.pprint(env.provider.info(env.vm))


@task
@load_provider
def status():
    #TODO: format output
    statuses = env.provider.status()
    for line in statuses:
        pprint.pprint(line)

@task
@load_provider
def workon(name=None):
    """
    shortcut to filter host based on name (falls back to env.vm_name)
    """
    if name is None and 'vm_name' in env and env.vm_name:
        name = env.vm_name
    configure_fabric_for_host(name)

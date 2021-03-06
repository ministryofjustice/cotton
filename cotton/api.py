"""
basic api

it's recommended to wrap every task with decorator @vm_task

@vm_task
def mytask():
    pass


"""
from __future__ import print_function
import pprint
import time
from functools import wraps

from pptable import pptable
import fabric.decorators
from fabric.api import abort

from cotton.provider.driver import provider_class
from cotton.common import *
from cotton.colors import *
from cotton.config import get_provider_zone_config


def load_provider(func):
    """
    Decorator for all functions that need access to cloud
    Sets: env.provider to initialized driver object
    Make sure that env.provider_zone is initialized beforehand
    """
    @wraps(func)
    def inner(*args, **kwargs):
        print(green("[{}]:".format(func.__name__)))
        start_time = time.time()
        get_provider_connection()
        ret = func(*args, **kwargs)

        end_time = time.time()
        print(green("[{}] finished in: {:.2f}s".format(func.__name__, end_time - start_time)))
        return ret
    return inner


def get_provider_connection():
    """
    returns initialized provider object and caches it in env.provider
    """
    zone_config = get_provider_zone_config()

    if 'verbose' in env and env.verbose:
        print("Selected provider zone config:")
        print(zone_config)

    if not 'provider' in env or not env.provider:
        p_class = provider_class(zone_config['driver'])
        env.provider = p_class(**zone_config)
    return env.provider


def workon_fallback(func):
    raise NotImplementedError("workon_fallback has been removed. Replace @workon_fallback and @task with just @vm_task")


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

        if 'vm' not in env or not env.vm:
            assert env.vm_name
            configure_fabric_for_host(env.vm_name)

        print(green("[{}:{}]".format(func.__name__, env.vm_name)))
        start_time = time.time()

        ret = func(*args, **kwargs)

        end_time = time.time()
        print(green("[{}] finished in: {:.2f}s".format(func.__name__, end_time - start_time)))
        return ret
    return fabric.decorators.task(inner)


def configure_fabric_for_host(name):
    """
    loads provider and configures current host based on name

    if zone_config['gateway'] than it will be configured
    if zone_config['ssh_key'] is supplied then we use it
    if we are in provisioning mode than zone_config['provisioning_ssh_key'] & zone_config['provisioning_user'] & zone_config['provisioning_password'] is used

    updated variables:
    env.provider
    env.vm
    env.vm_name
    env.host_string
    env.host
    env.key_filename
    env.user if in provisioning mode
    """
    get_provider_connection()
    vms = env.provider.filter(name=name)
    if not vms:
        abort(red("VM name='{}' not found".format(name)))
    # will pick first vm from list in case more are available
    env.vm = vms[0]

    env.vm_name = name

    get_provider_connection()
    env.host_string = env.provider.host_string(env.vm)

    zone_config = get_provider_zone_config()

    if env.provisioning:
        if 'provisioning_user' in zone_config:
            env.user = zone_config['provisioning_user']
        else:
            print(yellow("No 'provisioning_user' defined in zone config"))

        if 'provisioning_ssh_key' in zone_config:
            env.key_filename = zone_config['provisioning_ssh_key']
        else:
            print(yellow("No 'provisioning_ssh_key' defined in zone config"))
            print(yellow("Falling back to 'provisioning_password'"))
            if 'provisioning_password' in zone_config:
                env.password = zone_config['provisioning_password']
            else:
                print(yellow("No 'provisioning_password' defined in zone config"))
    else:
        if 'ssh_key' in zone_config:
            env.key_filename = zone_config['ssh_key']

    if 'gateway' in zone_config:
        if 'gateway_user' in env and env.gateway_user:
            env.gateway = '{}@{}'.format(env.gateway_user, zone_config['gateway'])
        else:
            env.gateway = '{}@{}'.format(env.user, zone_config['gateway'])


def dict_stringize_keys(data):
    """
    converts all keys within dictionary to strings
    """
    assert isinstance(data, dict)
    res = {}

    for k, v in data.iteritems():
        if isinstance(v, dict):
            res[str(k)] = dict_stringize_keys(v)
        else:
            res[str(k)] = v
    return res


@task
@load_provider
def create(name=None):
    from cotton.fabextras import wait_for_shell

    zone_config = get_provider_zone_config()
    vm_spec = zone_config.get('vm-defaults', {})
    vm_spec['name'] = name

    try:
        vm_spec['tags']
    except KeyError:
        vm_spec['tags'] = {}

    if 'environment' in env:
        vm_spec['tags']['env'] = env.environment
    if 'project' in env:
        vm_spec['tags']['project'] = env.project

    try:
        vm = env.provider.create(**vm_spec)
    except ValueError as e:
        abort(red(e))
    configure_fabric_for_host(name)  # TODO: we used to pass server object, check impact
    wait_for_shell()
    return vm


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
    pptable(statuses)


@task
@load_provider
def workon(name=None):
    """
    shortcut to filter host based on name (falls back to env.vm_name)
    """
    if name is None and 'vm_name' in env and env.vm_name:
        name = env.vm_name
    configure_fabric_for_host(name)

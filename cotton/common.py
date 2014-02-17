import sys
import time
import importlib
import json

import getpass
from fabric.api import (run, task, env, local, hide, parallel, sudo, reboot,
    settings, abort)
from fabric.contrib.files import upload_template
from fabric.contrib.project import rsync_project
from fabric.operations import open_shell
from fabric.exceptions import NetworkError
from functools import wraps

from cotton.colors import *
from functools import wraps

import cotton.config as config


if 'blueprintforhost' not in env:
    env.blueprintforhost = {}


if 'providerforhost' not in env:
    env.providerforhost = {}


if 'provisioning' not in env:
    env.provisioning = False


if 'project' not in env:
    env.project = 'default'


if 'profile' not in env:
    env.profile = 'default'

if 'insecure' not in env:
    env.insecure = False

if 'force' not in env:
    env.force = False

if 'os' not in env:
    env.os = 'ubuntu'

try:
    import config_common
    config.common = config_common
except ImportError as e:
    import imp
    config.common = imp.new_module("common")


def blueprint2roles(blueprint):
    """
    works with all three formats:
     - web,db,master
     - web;db;master
     - fullstack
    """
    blueprint = blueprint.replace(';', ',').replace(':', ',')
    if ',' in blueprint:
        return blueprint.split(',')
    if blueprint in config.common.BLUEPRINTS:
        return config.common.BLUEPRINTS[blueprint]
    return [blueprint]


def provider_module():
    """
    returns provider module that supports specific hostname
    """
    if env.host_string in env.providerforhost:
        provider = env.providerforhost[env.host_string]
    else:
        provider = env.providerforhost[env.hostname]

    provider_module = importlib.import_module("cotton.{}".format(provider))
    return provider_module


def hostroles():
    return provider_module().hostroles()


def hoststack():
    return provider_module().hoststack()


def getgrains():
    """
    returns initial grains as configured in central database
    """
    return provider_module().getgrains()


@task
@parallel
def uptime():
    """
    execute uptime
    """
    with hide('running'):
        run("uptime")


@task
def ping():
    """
    ssh ping
    """
    with hide('running'):
        run("echo OK")


@task
def forward(lport, rport):
    """
    open ssh session and tunnel port
    """
    local('ssh -o "ServerAliveInterval 30" -A -i {key} -p {port} -L {lport}:127.0.0.1:{rport} {user}@{host}'.format(key=env.key_filename, user=env.user, host=env.host, port=env.port, lport=lport, rport=rport))


@task
def ipython():
    """
    starts ipython within fabric context
    useful for development
    """
    # import IPython internally to make it optional
    import IPython
    IPython.embed()


@task
def ssh():
    """
    ssh to host (keep alive, forward key)
    """
    local('ssh -o "ServerAliveInterval 30" -A -i "{key}" -p {port} {user}@{host}'.format(key=env.key_filename, user=env.user, host=env.host, port=env.port))


@task
def getroles():
    """
    get roles for selected host
    """
    print hostroles()


@task
def provisioning():
    """
    switch into provisioning mode
    this modifies username and ssh key we use to reach the host
    """
    env.provisioning = True


@task
def insecure():
    """
    switch into insecure mode
    this skips ssh host key verification for rsync
    """
    env.insecure = True


@task
def force():
    """
    skips questions, assumes you are always right
    """
    env.force = True


@task(alias='p')
def project(project_name):
    """
    select project (i.e.: lpa)
    """
    env.project = project_name


@task
def profile(profile_name):
    """
    selects specific profile (i.e. can be used on aws to change aws api account)
    """
    print green("Profile: {}".format(profile_name))
    env.profile = profile_name


@task(alias='prod')
def production():
    """
    selects profile: production
    """
    profile('production')

@task
def provider(provider_name):
    """
    overwrites provider for selected host
    """
    provider_module = importlib.import_module("cotton.{}".format(provider_name))
    env.providerforhost[env.host_string] = provider_name
    if callable(getattr(provider_module, 'setup_instance')):
        provider_module.setup_instance()

@task
def wait_for_shell():
    """
    infinitely waits for shell on remote host
    i.e. after creation or reboot
    """
    print("Waiting for shell")
    with settings(hide('running')):
        while True:
            try:
                run("uptime")
                break
            except NetworkError:
                sys.stdout.write(".")
                sys.stdout.flush()
                time.sleep(1)
    print(" OK")

def smart_rsync_project(*args, **kwargs):
    """
    rsync_project wrapper that is aware of insecure fab argument

    :param for_user: optional, chowns the directory to this user at the end
    """
    if 'for_user' in kwargs:
        for_user = kwargs.pop('for_user')
    else:
        for_user = None
    directory = args[0]

    if env.insecure:
        kwargs['ssh_opts'] = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

    if for_user:
        sudo("find {} -type d -print0 | xargs -0 chmod u+rwx".format(directory))
        sudo("chown -R {} {}".format(env.user, directory))

    rsync_project(*args, **kwargs)

    if for_user:
        sudo("chown -R {} {}".format(for_user, directory))


def get_password(system, username, desc=None):
    """
    Wraps getpass and keyring to provide secure password functions.

    keyring will store the password in the system's password manager, i.e. Keychain
    on OS X.

    """
    import keyring
    if not desc:
        desc = "Password for user '%s': " % username

    password = keyring.get_password(system, username)
    if not password:
        password = getpass.getpass(desc)
        keyring.set_password(system, username, password)
    return password

def current_instance(func):
    """
    Decorator for task that will abort the task if no instances are selected.
    """
    @wraps(func)
    def inner(*args, **kwargs):
        if env.host is None:
            if env.force:
                print(red("No host selected - skipping execution", bold=True))
                sys.exit(0)
            else:
                abort(red("No host selected - skipping execution", bold=True))
        else:
            if env.host_string in env.instances:
                instance = env.instances[env.host_string]
            else:
                instance = env.instances[env.host]
            kwargs['instance'] = instance
            return func(*args, **kwargs)
    return inner

def push_grains_to_host(roles):
    grains = getgrains()
    provider = env.providerforhost[env.host_string]
    grains['provider'] = provider
    grains['roles'] = roles
    grains['project'] = env.project

    upload_template("salt.minion.conf", "/etc/salt.minion.conf",
                    template_dir=env.templates_dir,
                    use_jinja=True,
                    use_sudo=True,
                    context={'grains_text': json.dumps({'grains': grains})})

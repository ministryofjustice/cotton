from __future__ import print_function
from fabric.api import task, env
from cotton.config import get_env_config

if 'provisioning' not in env:
    env.provisioning = False

if 'project' not in env:
    env.project = None

if 'environment' not in env:
    env.environment = None

if 'insecure' not in env:
    env.insecure = False

if 'force' not in env:
    env.force = False


#???????
if 'instances' not in env:
    env.instances = {}
#env.instance = {
#    'host_string': {
#        'instance': InstanceObject(),
#        'privider': 'AWS',
#    }
#}
@task
def provisioning():
    """
    switch into provisioning mode
    this modifies username and ssh key we use to reach the host
    """
    env.provisioning = True


@task
def project(name):
    """
    sets project name
    """
    env.project = name


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


@task
def environment(env_name):
    """
    wrapper to set env.environment for the session
    """
    env.environment = env_name


def apply_configuration():
    """
    in provisioning mode it sets the ssh key from config file
    if ssh_key is available than uses it as user ssh key

    """
    env_config = get_env_config()
    if env.provisioning:
        env.key_filename = env_config['provisioning_ssh_key']
        env.user = env_config['provisioning_user']
    else:
        if 'ssh_key' in env_config:
            env.key_filename = env_config['ssh_key']

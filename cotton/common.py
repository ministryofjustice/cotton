from __future__ import print_function
from fabric.api import task, env
from cotton.config import get_provider_zone_config

if 'provisioning' not in env:
    env.provisioning = False

if 'project' not in env:
    env.project = None

if 'provider_zone' not in env:
    env.provider_zone = None

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

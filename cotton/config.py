"""
root/
|-- application-deployment/
|   `-- fabfile.py
|
|-- ~/.cotton.yaml / ${COTTON_CONFIG}
|-- config/projects/{env.project}/cotton.yaml
...
|-- config/projects/{env.project|split('/')[1]}/cotton.yaml
|-- config/projects/{env.project|split('/')[0]}/cotton.yaml
|-- config/projects/cotton.yaml
|-- config/cotton.yaml
|-- application-deployment/vagrant/cotton.yaml  # deprecated in favour to application-deployment/cotton.yaml
`-- application-deployment/cotton.yaml

I.e.:
env.project = nomis/pvb/production

cotton.yaml search path will look like:
root/
|
|-- ~/.cotton.yaml / ${COTTON_CONFIG}
|
|-- config/projects/nomis/pvb/production/cotton.yaml
|-- config/projects/nomis/pvb/cotton.yaml
|-- config/projects/nomis/cotton.yaml
|
|-- config/projects/cotton.yaml
|-- config/cotton.yaml
|
`-- application-deployment/cotton.yaml


Note:
env.project can be a path and in such case cotton.yaml will be ingested on every directory level

"""
from __future__ import print_function
import yaml
import os
import copy

from fabric.api import env
from cotton.colors import *


def dict_deepmerge(source, target):
    """
    deep merges two dictionaries and returns merged value
    'source' is merged on top of 'target'
    think:
     - python inheritance pattern
     - final dictionary simulates left hand search
    """
    assert isinstance(source, dict)
    assert isinstance(target, dict)

    if not target:
        return source.copy()

    merged = copy.deepcopy(target)

    for k, v in source.iteritems():
        if k in merged and isinstance(v, dict) and isinstance(merged[k], dict):
            merged[k] = dict_deepmerge(v, merged[k])
        else:
            merged[k] = copy.deepcopy(v)

    return merged


def _load_config_file(path):
    fab_location = os.path.dirname(env.real_fabfile)
    config_location = os.path.abspath(os.path.join(fab_location, path))

    with open(config_location) as f:
        return yaml.load(f)


def get_config():
    """
    merges user config with global config and project config
    """
    if '__config' in env and env.__config:
        return env.__config
    print("Merging config files:")
    # TODO: allow in COTTON_CONFIG to specify location of config repo
    # I.e.: cotton.config = ../config

    # If a preferred location is specified in the hash the old path is deprecated and a warning
    # should be shown
    # Last file in the list is the most important

    config_base_dir = '../config'
    if 'project' in env and env.project:
        path = '{}/projects/{}'.format(config_base_dir, env.project)
    else:
        path = '{}/projects'.format(config_base_dir)
    config_dirs = []

    #let's walk config dir
    while True:
        config_dirs.append(path)
        path = os.path.dirname(path)
        if path == config_base_dir:
            config_dirs.append(path)
            break

    config_files = []
    for path in reversed(config_dirs):
        config_files.append({'path': os.path.join(path, 'config.yaml'),
                             'preferred': os.path.join(path, 'cotton.yaml')})
        config_files.append({'path': os.path.join(path, 'project.yaml'),
                             'preferred': os.path.join(path, 'cotton.yaml')})
        config_files.append({'path': os.path.join(path, 'cotton.yaml')})

    if 'provider_zone' in env and 'vagrant' in env.provider_zone:
        config_files.append({'path': 'vagrant/cotton.yaml',
                             'preferred': 'cotton.yaml'})

    os_env_cotton_config = os.environ.get('COTTON_CONFIG', None)
    if os_env_cotton_config:
        config_files.append({'path': os_env_cotton_config})
    else:
        config_files.append({'path': '~/.config.yaml',
                             'preferred': '~/.cotton.yaml'})
        config_files.append({'path': '~/.cotton.yaml'})

    merged_config = {}
    for config_file in config_files:
        config_filename = os.path.expanduser(config_file.get('path'))
        if os.path.exists(config_filename):
            try:
                loaded_config = _load_config_file(config_filename)
                print(green("Loaded:  {}".format(config_filename)))
                if config_file.get('preferred'):
                    print(red("Deprecated location for {} - Please use {}".format(config_filename, config_file.get('preferred'))))
                merged_config = dict_deepmerge(loaded_config, merged_config)
            except Exception as e:
                if 'preferred' not in config_file:
                    print(yellow("Warning - error loading config: {}".format(config_filename)))
                    print(yellow(e))
        else:
            # let's only print preferred locations that we skipped
            if 'preferred' not in config_file:
                print("Skipped: {}".format(config_filename))

    env.__config = merged_config
    return merged_config


def get_provider_zone_config():
    """
    return get_config()['provider_zones'][env.provider_zone]
    if key does not exist than falls back to default zone
    """
    config = get_config()

    if env.provider_zone in config['provider_zones']:
        zone = env.provider_zone
    else:
        zone = config['provider_zones']['default']


    cfg = config['provider_zones'][zone]
    if 'driver' not in cfg:
        raise RuntimeError("Provider zone %s is missing the 'driver' option!" % zone)

    return cfg


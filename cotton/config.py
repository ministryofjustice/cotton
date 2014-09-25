"""
root/
|-- application-deployment/
|   `-- fabfile.py
|
|-- ~/.cotton.yaml / ${COTTON_CONFIG}
|-- config/projects/{project}/project.yaml
`-- config/cotton.yaml

"""
from __future__ import print_function
import yaml
import os
import copy

from fabric.api import env
from cotton.colors import *
#TODO: add /etc/cotton/config.yaml support


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
    # TODO: Potentially cotton.yaml could contain key that will manage the list of files being merged.
    # I.e.: cotton.configs = []

    # If a preferred location is specified in the hash the old path is deprecated and a warning
    # should be shown
    # Last file in the list is the most important
    config_files = [
        {'path': '../config/config.yaml',
         'preferred': '../config/cotton.yaml'},
        {'path': '../config/cotton.yaml'},
    ]
    if 'project' in env and env.project:
        config_files.append({'path': '../config/projects/{}/config.yaml'.format(env.project),
                             'preferred': '../config/projects/{}/project.yaml'.format(env.project)})
        config_files.append({'path': '../config/projects/{}/cotton.yaml'.format(env.project),
                             'preferred': '../config/projects/{}/project.yaml'.format(env.project)})
        config_files.append({'path': '../config/projects/{}/project.yaml'.format(env.project)})

    if 'provider_zone' in env and 'vagrant' in env.provider_zone:
        config_files.append({'path': 'vagrant/project.yaml'})

    os_env_cotton_config = os.environ.get('COTTON_CONFIG', None)
    if os_env_cotton_config:
        config_files.append({'path': os_env_cotton_config})
    else:
        config_files.append({'path': '../config.user/config.yaml',
                             'preferred': '~/.cotton.yaml'})
        config_files.append({'path': '~/.config.yaml',
                             'preferred': '~/.cotton.yaml'})
        config_files.append({'path': '~/.cotton.yaml'})

    merged_config = {}
    for config_file in config_files:
        config_filename = os.path.expanduser(config_file.get('path'))
        try:
            loaded_config = _load_config_file(config_filename)
            print(green("Loaded config: {}".format(config_filename)))
            if config_file.get('preferred'):
                print(red("Deprecated location for {} - Please use {}".format(config_filename, config_file.get('preferred'))))
            merged_config = dict_deepmerge(loaded_config, merged_config)
        except Exception as e:
            if 'preferred' not in config_file:
                print(yellow("Warning - error loading config: {}".format(config_filename)))
                print(yellow(e))

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


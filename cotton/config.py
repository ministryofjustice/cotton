"""
root/
|-- application-deployment/
|   `-- fabfile.py
|
|-- ~/.cotton.yaml
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
    a is merged on top of b (think python inheritance pattern)
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

    # If a preferred location is specified in the hash the old path is deprecated and a warning
    # should be shown
    config_files = [
        {'path': '../config/config.yaml',      'preferred': '../config/cotton.yaml'},
        {'path': '../config/cotton.yaml'},
        {'path': '../config.user/config.yaml', 'preferred': '~/.cotton.yaml'},
        {'path': '~/.config.yaml',             'preferred': '~/.cotton.yaml'},
        {'path': '~/.cotton.yaml'}
    ]
    if 'project' in env and env.project:
        config_files.append({'path': '../config/projects/{}/project.yaml'.format(env.project)})
        config_files.append({'path': '../config/projects/{}/config.yaml'.format(env.project),
                             'preferred': '../config/projects/{}/project.yaml'.format(env.project)})

    config = {}
    for config_file in config_files:
        config_filename = os.path.expanduser(config_file.get('path'))
        try:
            data = _load_config_file(config_filename)
            print(green("Loaded config: {}".format(config_filename)))
            if config_file.get('preferred'):
                print(red("Deprecated location for {} - Please use {}".format(config_filename, config_file.get('preferred'))))
            config = dict_deepmerge(data, config)
        except Exception as e:
            if 'preferred' not in config_file:
                print(yellow("Warning - error loading config: {}".format(config_filename)))
                print(yellow(e))

    env.__config = config
    return config


def get_provider_zone_config():
    """
    return get_config()['provider_zones'][env.provider_zone]
    if key does not exist than falls back to default zone
    """
    config = get_config()

    if env.provider_zone in config['provider_zones']:
        return config['provider_zones'][env.provider_zone]
    else:
        return config['provider_zones'][config['provider_zones']['default']]


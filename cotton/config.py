"""
root/
|-- application-deployment/
|   `-- fabfile.py
|-- config.user/config.yaml
|-- config/projects/{project}/config.yaml
`-- config/config.yaml

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
    fab_location = os.path.dirname(env['real_fabfile'])
    config_location = os.path.abspath(os.path.join(fab_location, path))

    with open(config_location) as f:
        return yaml.load(f)


def get_config():
    """
    merges user config with global config and project config
    """
    if '__config' in env and env.__config:
        return env.__config

    config_files = ['../config.user/config.yaml', '../config/config.yaml']
    if 'project' in env and env.project:
        config_files.insert(1, '../config/projects/{}/config.yaml'.format(env.project))

    config = {}

    while config_files:
        config_file = config_files.pop()
        try:
            data = _load_config_file(config_file)
            print(green("Loaded config: {}".format(config_file)))
        except Exception as e:
            print(yellow("Warning - error loading config: {}".format(config_file)))
            print(yellow(e))
        config = dict_deepmerge(data, config)

    env.__config = config
    return config


def get_env_config():
    """
    return get_config()['environment'][env.environment]
    if key does not exist than falls back to default environment
    """
    config = get_config()
    if env.environment in config['environment']:
        return config['environment'][env.environment]
    else:
        return config['environment'][config['environment']['default']]


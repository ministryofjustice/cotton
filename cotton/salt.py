"""
root/
|-- application-deployment/
|   `-- fabfile.py
`-- config/projects/{project}/pillar/
"""

import os
from fabric.api import env


def get_pillar_location():
    """
    returns local pillar location
    """
    assert 'project' in env
    assert env.project

    fab_location = os.path.dirname(env['real_fabfile'])
    pillar_location = os.path.abspath(os.path.join(fab_location, '../config/projects/{}/pillar'.format(env.project)))

    return pillar_location

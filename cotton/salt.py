"""
root/
|-- application-deployment/
|   `-- fabfile.py
`-- config/projects/{project}/pillar/
"""

import os
import pkgutil
import tempfile
import yaml

from StringIO import StringIO

from fabric.api import env, put, sudo

from cotton.colors import *
from cotton.api import vm_task, get_provider_zone_config


def get_unrendered_pillar_location():
    """
    returns local pillar location
    """
    assert 'project' in env
    assert env.project

    # TODO: render pillar template to stdout / temp directory to sync it? (or just generate one file for remote)
    fab_location = os.path.dirname(env.real_fabfile)
    pillar_location = os.path.abspath(os.path.join(fab_location, '../config/projects/{}/pillar'.format(env.project)))

    return pillar_location


def _get_projects_location():
    fab_location = os.path.dirname(env.real_fabfile)
    return os.path.abspath(os.path.join(fab_location, '../config/projects/'))


def get_rendered_pillar_location():
    """
    Returns path to rendered pillar.
    Use to render pillars written in jinja locally not to upload unwanted data to network.

    i.e. you can use constructs like:
    {% include 'opg-lpa-dev/pillar/services.sls' %}

    In case there is no top.sls in pillar root than it returns: None
    """
    from jinja2 import Environment
    from jinja2 import FileSystemLoader
    from jinja2.exceptions import TemplateNotFound

    assert env.project
    projects_location = _get_projects_location()

    jinja_env = Environment(
        loader=FileSystemLoader([os.path.join(projects_location, env.project, 'pillar'),
                                 projects_location]))

    # let's get rendered top.sls for configured project
    try:
        top_sls = jinja_env.get_template('top.sls').render(env=env)
    except TemplateNotFound as e:
        print(red("Missing top.sls in pillar location. Skipping rendering."))
        return None

    top_content = yaml.load(top_sls)

    dest_location = tempfile.mkdtemp()

    with open(os.path.join(dest_location, 'top.sls'), 'w') as f:
        f.write(top_sls)

    # get list of files referenced by top.sls
    files_to_render = []
    for k0, v0 in top_content.iteritems():
        for k1, v1 in v0.iteritems():
            for file_short in v1:
                # We force this file to be relative in case jinja failed rendering 
                # a variable. This would make the filename start with / and instead of 
                # writing under dest_location it will try to write in / 
                files_to_render.append('./' + file_short.replace('.','/') + '.sls')

    # render and save templates
    for template_file in files_to_render:
        filename = os.path.abspath(os.path.join(dest_location, template_file))
        print(yellow("Pillar template_file: {} --> {}".format(template_file, filename)))
        if os.path.isdir(os.path.dirname(filename)) == False:
            os.makedirs(os.path.dirname(filename))
        try: 
            template_rendered = jinja_env.get_template(template_file).render(env=env)
        except TemplateNotFound as e:
            template_rendered = ''
            print(yellow("Pillar template_file not found: {} --> {}".format(template_file, filename)))
        with open(os.path.join(dest_location, template_file), 'w') as f:
            f.write(template_rendered)

    print(green("Pillar was rendered in: {}".format(dest_location)))
    return dest_location


get_pillar_location = get_rendered_pillar_location

@vm_task
def reset_roles():
    """
    reset role grains to the defaults specified in the provider_zone configuration
    """
    assert(env.vm_name)
    (host,) = [x for x in get_provider_zone_config()['hosts'] if x['name'] == env.vm_name]
    grains = host.get('roles', [])
    print (env.domainname)
    sudo('salt-call --local grains.setval roles "{}"'.format(grains))


def _reconfig_minion(salt_server):
    """

    """
    assert(salt_server)
    assert(env.vm_name)
    # The base-image may have a minion_id already defined - delete it
    sudo('/bin/rm -f /etc/salt/minion_id')

    fqdn = "{}.{}".format(env.vm_name, env.domainname)
    minion_contents = {
        'master': salt_server,
        'id': fqdn
    }

    minion_configIO = StringIO(repr(minion_contents))
    env.sudo_user = 'root'
    put(minion_configIO, "/etc/salt/minion", use_sudo=True, mode=0644)
    sudo("/bin/chown root:root /etc/salt/minion")

def _bootstrap_salt(salt_server=None, flags=''):
    if salt_server is None:

        (master,) = [x for x in get_provider_zone_config()['hosts'] if x['name'] == 'master']
        salt_server = master['ip']

    _reconfig_minion(salt_server)
    bootstrap_fh = StringIO(pkgutil.get_data(__package__, 'share/bootstrap-salt.sh'))
    put(bootstrap_fh, "/tmp/bootstrap-salt.sh")
    sudo("bash /tmp/bootstrap-salt.sh {} -A {}".format(flags, salt_server))
    reset_roles()


@vm_task
def bootstrap_minion():
    _bootstrap_salt()


@vm_task
def bootstrap_master():
    # One extra step = push master config file
    master_conf_fh = StringIO(pkgutil.get_data(__package__, 'share/bootstrap_master.conf'))
    put(master_conf_fh, "/etc/salt/master", use_sudo=True, mode=0644)
    sudo("/bin/chown root:root /etc/salt/master")

    # Pass the -M flag to ensure master is created
    _bootstrap_salt(flags='-M')

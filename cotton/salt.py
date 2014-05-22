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

from fabric.api import task  # noqa

from cotton.colors import red, yellow, green
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
    except TemplateNotFound:
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
                files_to_render.append('./' + file_short.replace('.', '/') + '.sls')

    # render and save templates
    for template_file in files_to_render:
        filename = os.path.abspath(os.path.join(dest_location, template_file))
        print(yellow("Pillar template_file: {} --> {}".format(template_file, filename)))
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        try:
            template_rendered = jinja_env.get_template(template_file).render(env=env)
        except TemplateNotFound:
            template_rendered = ''
            print(yellow("Pillar template_file not found: {} --> {}".format(template_file, filename)))
        with open(os.path.join(dest_location, template_file), 'w') as f:
            f.write(template_rendered)

    print(green("Pillar was rendered in: {}".format(dest_location)))
    return dest_location


get_pillar_location = get_rendered_pillar_location


@vm_task
def reset_roles(roles=None):
    """
    Reset salt role grains to the values specified in the provider_zone
    configuration for the current host
    """
    if roles is None:
        assert(env.vm_name)
        (host,) = [x for x in get_provider_zone_config()['hosts'] if x['name'] == env.vm_name]
        roles = host.get('roles', [])
    sudo('salt-call --local grains.setval roles "{}"'.format(roles))


def _reconfig_minion(salt_server):
    """

    """
    assert(salt_server)
    assert(env.vm_name)
    assert(env.domainname)
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


def _bootstrap_salt(master=None, flags='', install_type='', roles=None):
    if master is None:
        (master_info,) = [x for x in get_provider_zone_config()['hosts'] if x['name'] == 'master']
        master = master_info['ip']

    _reconfig_minion(master)
    bootstrap_fh = StringIO(pkgutil.get_data(__package__, 'share/bootstrap-salt.sh'))
    put(bootstrap_fh, "/tmp/bootstrap-salt.sh")
    sudo("bash /tmp/bootstrap-salt.sh {} -A {} {}".format(flags, master, install_type))
    reset_roles(roles)


@vm_task
def bootstrap_minion(master=None):
    """
    Bootstrap a salt minion and connect it to the master in the current
    enviroment.

    It relies upon get_provider_zone_config_ to have a host called 'master'. It
    will also set the roles via `reset_roles`_ funciton.

    An example of the provider config project.yaml::

        provider_zones:
          mv_project_staging2:
            driver: static
            domainname: staging2.my_project
            hosts:
              - name: jump
                ip: 10.3.31.10
                roles: [ jump ]
              - name: master
                ip: 10.3.31.11
                roles: [ master ]
              - name: monitoring-01
                ip: 10.3.31.20
                roles: [ monitoring.server ]
                aliases: [ monitoring.local, sensu.local, graphite.local ]


    ``roles`` is the authoritative list of salt roles to apply to this box.

    ``aliases`` can be used by putting this snippet in your pillar/hosts.yaml file::

        hosts:
        {%- for host in env.zone_config['hosts'] %}
          {{ host['ip'] }}:
            - {{ host['name'] }}.{{ env.environment }}
            {% for alias in host['aliases'] -%}
            - {{ alias }}
            {% endfor %}
        {% endfor -%}

    """
    _bootstrap_salt(master, roles)


@vm_task
def bootstrap_master(roles=None):
    """
    Bootstrap a minimal salt master on the current server (as configued via
    ``workon``).

    """
    # One extra step = push master config file
    master_conf_fh = StringIO(pkgutil.get_data(__package__, 'share/bootstrap_master.conf'))
    put(master_conf_fh, "/etc/salt/master", use_sudo=True, mode=0644)
    sudo("/bin/chown root:root /etc/salt/master")

    # Pass the -M flag to ensure master is created
    _bootstrap_salt(master='localhost', flags='-M', roles=roles)

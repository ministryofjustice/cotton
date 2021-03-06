"""
root/
|-- application-deployment/
|   `-- fabfile.py
`-- config/projects/{project}/pillar/
"""

import os
import sys
import pkgutil
import tempfile
import yaml
import json

from StringIO import StringIO
from collections import defaultdict
from collections import OrderedDict
from pprint import pformat

from fabric.api import env, put, sudo, task, get, abort

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


def get_rendered_pillar_location(pillar_dir=None, projects_location=None, parse_top_sls=True):
    """
    Returns path to rendered pillar.
    Use to render pillars written in jinja locally not to upload unwanted data to network.

    i.e. you can use constructs like:
    {% include 'opg-lpa-dev/pillar/services.sls' %}

    If you want salt to later render pillars with grain context use constructs like:
    {% raw %} {{grains.get('roles')}} {% endraw %}
    {{" {{grains.get('roles')}} "}}

    To allow for server side templating of top.sls, you will need set: `parse_top_sls=False`

    In case there is no top.sls in pillar root than it returns: None
    """
    from jinja2 import Environment
    from jinja2 import FileSystemLoader
    from jinja2.exceptions import TemplateNotFound

    if projects_location is None:
        projects_location = _get_projects_location()

    if pillar_dir is None:
        if "pillar_dir" in env:
            pillar_dir = env.pillar_dir
        else:
            assert env.project, "env.project or env.pillar_dir must be specified"
            pillar_dir = os.path.join(projects_location, env.project, 'pillar')

    jinja_env = Environment(
        loader=FileSystemLoader([pillar_dir, projects_location]))

    files_to_render = []
    dest_location = tempfile.mkdtemp()

    if parse_top_sls:
        # let's parse top.sls to only select files being referred in top.sls
        try:
            top_sls = jinja_env.get_template('top.sls').render(env=env)
        except TemplateNotFound:
            raise RuntimeError("Missing top.sls in pillar location. Skipping rendering.")

        top_content = yaml.load(top_sls)

        filename = os.path.join(dest_location, 'top.sls')
        with open(filename, 'w') as f:
            print("Pillar template_file: {} --> {}".format('top.sls', filename))
            f.write(top_sls)

        for k0, v0 in top_content.iteritems():
            for k1, v1 in v0.iteritems():
                for file_short in v1:
                    # We force this file to be relative in case jinja failed rendering
                    # a variable. This would make the filename start with / and instead of
                    # writing under dest_location it will try to write in /
                    if isinstance(file_short, str):
                        files_to_render.append('./' + file_short.replace('.', '/') + '.sls')
    else:
        # let's select all files from pillar directory
        for root, dirs, files in os.walk(pillar_dir):
            rel_path = os.path.relpath(root, pillar_dir)
            for file_name in files:
                files_to_render.append(os.path.join(rel_path, file_name))

    # render and save templates
    for template_file in files_to_render:
        filename = os.path.abspath(os.path.join(dest_location, template_file))
        print("Pillar template_file: {} --> {}".format(template_file, filename))
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        try:
            template_rendered = jinja_env.get_template(template_file).render(env=env)
        except TemplateNotFound:
            template_rendered = ''
            print(red("Pillar template_file not found: {} --> {}".format(template_file, filename)))
        with open(os.path.join(dest_location, template_file), 'w') as f:
            f.write(template_rendered)

    print(green("Pillar was successfully rendered in: {}".format(dest_location)))
    return dest_location


get_pillar_location = get_rendered_pillar_location


@vm_task
def reset_roles(salt_roles=None):
    """
    Reset salt role grains to the values specified in the provider_zone
    configuration for the current host
    """
    if isinstance(salt_roles, basestring):
        salt_roles = salt_roles.split(';')
    elif salt_roles is None:
        assert env.vm
        info = env.provider.info(env.vm)
        salt_roles = info.get('roles', [])
    sudo('salt-call --local grains.setval roles "{}"'.format(salt_roles))


def _reconfig_minion(salt_server):
    """

    """
    assert salt_server
    assert env.vm_name
    assert env.domainname
    # The base-image may have a minion_id already defined - delete it
    sudo('/bin/rm -f /etc/salt/minion_id')

    if '.' in env.vm_name:
        fqdn = env.vm_name
    else:
        fqdn = "{}.{}".format(env.vm_name, env.domainname)
    minion_contents = {
        'master': salt_server,
        'id': str(fqdn),
    }
    put(StringIO(fqdn), '/etc/hostname', use_sudo=True, mode=0644)
    sudo("echo '127.0.0.1 {}' >> /etc/hosts".format(fqdn))
    sudo("hostname {}".format(fqdn))


    minion_configIO = StringIO(repr(minion_contents))
    env.sudo_user = 'root'
    sudo("mkdir -p /etc/salt")
    put(minion_configIO, "/etc/salt/minion", use_sudo=True, mode=0644)
    sudo("/bin/chown root:root /etc/salt/minion")


def _bootstrap_salt(master=None, flags='', install_type='', salt_roles=None):
    if master is None:
        (server,) = env.provider.filter(name="master")
        if server:
            master_info = env.provider.info(server)
            master = master_info['ip']
        else:
            raise ValueError("No salt master hostname provided and no server 'master' found")

    _reconfig_minion(master)
    bootstrap_fh = StringIO(pkgutil.get_data(__package__, 'share/bootstrap-salt.sh'))
    put(bootstrap_fh, "/tmp/bootstrap-salt.sh")
    sudo("bash /tmp/bootstrap-salt.sh {} -A {} {}".format(flags, master, install_type))
    reset_roles(salt_roles)


@vm_task
def bootstrap_minion(**kwargs):
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
    _bootstrap_salt(**kwargs)


@vm_task
def bootstrap_master(salt_roles=None, master='localhost', flags='-M', **kwargs):
    """
    Bootstrap a minimal salt master on the current server (as configued via
    ``workon``).

    """
    # One extra step = push master config file
    master_conf_fh = StringIO(pkgutil.get_data(__package__, 'share/bootstrap_master.conf'))
    sudo("mkdir -p /etc/salt")
    put(master_conf_fh, "/etc/salt/master", use_sudo=True, mode=0644)
    sudo("/bin/chown root:root /etc/salt/master")

    # Pass the -M flag to ensure master is created
    _bootstrap_salt(master=master, flags=flags, salt_roles=salt_roles, **kwargs)


@task
def salt(selector, args, parse_highstate=False, timeout=60):
    """
    `salt` / `salt-call` wrapper that:
    - checks if `env.saltmaster` is set to select between `salt` or `salt-call` command
    - checks for output state.highstate and aborts on failure
    param selector: i.e.: '*', -G 'roles:foo'
    param args: i.e. state.highstate
    """

    def dump_json(data):
        return json.dumps(data, indent=4)

    def stream_jsons(data):
        """
        ugly semi (assumes that input is a pprinted jsons' sequence) salt specific json stream parser as generator of jsons
        #TODO: work on stream instead of big data blob
        """
        data_buffer = []
        for line in data.splitlines():
            assert isinstance(line, basestring)
            data_buffer.append(line)
            if line.startswith("}"):  # as salt output is a pretty json this means - end of json blob
                if data_buffer:
                    yield json.loads("".join(data_buffer), object_pairs_hook=OrderedDict)
                    data_buffer = []
        assert not data_buffer

    if parse_highstate:
        remote_temp = sudo('mktemp')
        # Fabric merges stdout & stderr for sudo. So output is useless
        # Therefore we will store the stdout in json format to separate file and parse it later
        if 'saltmaster' in env and env.saltmaster:
            sudo("salt {} {} --out=json -t {}| tee {}".format(selector, args, timeout, remote_temp))
        else:
            sudo("salt-call {} --out=json | tee {}".format(args, remote_temp))

        sudo("chmod 664 {}".format(remote_temp))
        output_fd = StringIO()
        get(remote_temp, output_fd)
        output = output_fd.getvalue()
        failed = 0
        summary = defaultdict(lambda: defaultdict(lambda: 0))

        for out_parsed in stream_jsons(output):
            for server, states in out_parsed.iteritems():
                if isinstance(states, list):
                    failed += 1
                else:
                    for state, state_fields in states.iteritems():
                        summary[server]['states'] += 1
                        color = green
                        if state_fields['changes']:
                            color = yellow
                            summary[server]['changed'] += 1
                        if not state_fields['result']:
                            color = red
                            summary[server]['failed'] += 1
                            failed += 1
                            print(color("{}: ".format(state), bold=True))
                            print(color(dump_json(state_fields)))
                        else:
                            summary[server]['passed'] += 1
                            print(color("{}: ".format(state), bold=True))
                            print(color(dump_json(state_fields)))

        if failed:
            print
            print(red("Summary", bold=True))
            print(red(dump_json(summary)))
            abort('One of states has failed')
        else:
            print
            print(green("Summary", bold=True))
            print(green(dump_json(summary)))

        # let's cleanup but only if everything was ok
        sudo('rm {}'.format(remote_temp))
    else:
        if 'saltmaster' in env and env.saltmaster:
            sudo("salt {} {} -t {}".format(selector, args, timeout))
        else:
            sudo("salt-call {}".format(args))


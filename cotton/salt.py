"""
root/
|-- application-deployment/
|   `-- fabfile.py
`-- config/projects/{project}/pillar/
"""

import os
import re
import shutil
import stat
import sys
import tempfile
import yaml

from fabric.api import env
from git import Repo


from cotton.colors import *




def get_unrendered_pillar_location():
    """
    returns local pillar location
    """
    assert 'project' in env
    assert env.project

    #TODO: render pillar template to stdout / temp directory to sync it? (or just generate one file for remote)
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


def install_vendored_formulas(root_dir):

    roots_dir = os.path.join(root_dir, 'vendor', '_root')
    repos_dir = os.path.join(root_dir, 'vendor', 'formula-repos')
    if os.path.exists(roots_dir):
        shutil.rmtree(roots_dir)
    os.makedirs(roots_dir)

    if not os.path.exists(repos_dir):
        os.makedirs(repos_dir)

    # Setup SSH to remove VisualHostKey - it breaks GitPython's attempt to
    # parse git output :(

    # Will delete file once the object gets GC'd
    git_ssh_wrapper = tempfile.NamedTemporaryFile(prefix='cotton-git-ssh')

    git_ssh_wrapper.write("""#!/bin/bash
    ssh -o VisualHostKey=no "$@"
    """)
    git_ssh_wrapper.file.flush()
    os.fchmod(git_ssh_wrapper.file.fileno(), stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    os.environ['GIT_SSH'] = git_ssh_wrapper.name

    fetched_formulas = {}

    def get_formula_requirements(filename):

        wanted_formulas = {}
        with open(filename, 'r') as fh:
            for url in fh.readlines():
                url = url.strip()

                # TODO: Is this too simple parsing?
                (name,) = re.search(r'/([^/]*?)(?:-formula)?(?:\.git)?$', url).groups()
                wanted_formulas[name] = url
        return wanted_formulas

    requirements_files = [
        os.path.join(root_dir, 'formula-requirements.txt'),
    ]

    while len(requirements_files):
        req_file = requirements_files.pop()

        wanted_formulas = get_formula_requirements(req_file)
        for formula, url in wanted_formulas.iteritems():
                if formula in fetched_formulas:
                    assert fetched_formulas[formula] == url
                    continue

                repo_dir = os.path.join(repos_dir, formula + "-formula")

                # Split things out into multiple steps and checks to be Ctrl-c resilient
                if os.path.isdir(repo_dir):
                    repo = Repo(repo_dir)
                else:
                    repo = Repo.init(repo_dir)

                try:
                    origin = repo.remotes.origin
                except AttributeError:
                    origin = repo.create_remote('origin', url)

                try:
                    wanted_ref = origin.refs.master
                except (AttributeError, AssertionError):
                    sys.stdout.write("Fetching %s" % url)
                    origin.fetch()
                    print(" done")
                    wanted_ref = origin.refs.master

                if repo.head.reference != wanted_ref:
                    repo.head.reference = wanted_ref
                    repo.head.reset(index=True, working_tree=True)

                source = os.path.join(repo_dir, formula)
                target = os.path.join(root_dir, 'vendor', '_root', formula)
                if not os.path.exists(source):
                    raise RuntimeError("%s: Source '%s' does not exist" % (name, source))
                if os.path.exists(target):
                    raise RuntimeError("%s: Target '%s' conflicts with something else" % (name,target))
                os.symlink(source, target)

                fetched_formulas[formula] = url

                # Check for recursive formula dep.
                req_file = os.path.join(repo_dir, 'formula-requirements.txt')
                if os.path.isfile(req_file):
                    requirements_files.append(req_file)


"""
root/
|-- application-deployment/
|   `-- fabfile.py
`-- config/projects/{project}/pillar/
"""

import logging
import os
import re
import shutil
import stat
import sys
import tempfile
import yaml

from textwrap import dedent

from fabric.api import env
from git import Repo


from cotton.colors import *

logging.basicConfig()
logger = logging.getLogger(__name__)


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
        top_sls = jinja_env.get_template('top.sls').render()
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
                files_to_render.append(file_short + '.sls')

    # render and save templates
    for template_file in files_to_render:
        template_rendered = jinja_env.get_template(template_file).render()
        with open(os.path.join(dest_location, template_file), 'w') as f:
            f.write(template_rendered)

    print(green("Pillar was rendered in: {}".format(dest_location)))
    return dest_location


get_pillar_location = get_rendered_pillar_location


def install_vendored_formulas(root_dir):
    """
    Recursively walk formula-requirements.txt and manully pull in those
    versions of the specified formulas.

    The format of the file is simply a list of git-cloneable urls with an
    optional revision specified on the end. At the moment the only form a
    version comparison accepted is `==`. At the moment the version is anything
    that git rev-parse understands.

    Example::

        git@github.com:ministryofjustice/ntp-formula.git==v1.2.3
        git@github.com:ministryofjustice/repos-formula.git==my_branch
        git@github.com:ministryofjustice/php-fpm-formula.git
        git@github.com:ministryofjustice/utils-formula.git==
        git@github.com:ministryofjustice/java-formula.git
        git@github.com:ministryofjustice/redis-formula.git
        git@github.com:ministryofjustice/logstash-formula.git
        git@github.com:ministryofjustice/sensu-formula.git
        git@github.com:ministryofjustice/rabbitmq-formula.git
        git@github.com:saltstack-formulas/users-formula.git
    """

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
                (url, name, rev,) = re.search(r'(.*?/([^/]*?)(?:-formula)?(?:\.git)?)(?:==(.*?))?$', url).groups()
                wanted_formulas[name] = {
                    'url': url,
                    'revision': rev or 'master',
                    'source': filename,
                }

        return wanted_formulas

    def rev_to_sha(repo, origin, rev):
        from git.exc import GitCommandError

        # Try to resovle the revision into a SHA. If rev is a tag or a SHA then
        # try to avoid doing a fetch on the repo. If it is a branch then make
        # sure it is the tip of that branch

        have_updated = False
        is_branch = False
        sha = None

        for attempt in range(0, 2):
            try:
                # Try a tag first. Treat it as immutable so if we find it then
                # we don't have to fetch the remote repo
                tag = repo.tags[rev]
                return tag.commit.hexsha
            except IndexError:
                pass

            try:
                # Next check for a branch - if it is one then we want to udpate
                # as it might have changed since we last fetched
                (full_ref,) = filter(lambda r: r.remote_head == rev, origin.refs)
                is_branch = True

                # Don't treat the sha as resolved until we've updated the
                # remote
                if have_updated:
                    sha = full_ref.commit.hexsha
            except (ValueError, AssertionError):
                pass

            # Could just be a SHA
            try:
                sha = repo.git.rev_parse(formula['revision'])
            except GitCommandError:
                # Maybe we just need to fetch first.
                pass

            if sha is not None:
                return sha

            if have_updated:
                # If we've already updated once and get here then we can't find it :(
                raise RuntimeError("Could not find out what revision '{rev}' was for {url} (defined in {source}".format(
                    rev=formula['revision'],
                    url=formula['url'],
                    source=formula['source'],
                ))

            msg = "Fetching %s" % origin.url
            if is_branch:
                msg = msg + " to see if %s has changed" % rev
            sys.stdout.write(msg)
            origin.fetch(refspec="refs/tags/*:refs/tags/*")
            origin.fetch()
            print(" done")

            have_updated = True

    requirements_files = [
        os.path.join(root_dir, 'formula-requirements.txt'),
    ]

    while len(requirements_files):
        req_file = requirements_files.pop()
        logger.info("Checking %s" % req_file)

        wanted_formulas = get_formula_requirements(req_file)
        for formula_name, formula in wanted_formulas.iteritems():
            previously_fetched = None
            if formula_name in fetched_formulas:
                previously_fetched = fetched_formulas[formula_name]
                if previously_fetched['url'] != formula['url']:
                    raise RuntimeError(dedent("""
                        Formula URL clash for {name}:
                        - {old[url]} (defined in {old[source]})
                        + {new[url]} (defined in {new[source]})""".format(
                        name=formula_name,
                        old=previously_fetched,
                        new=formula)
                    ))

            repo_dir = os.path.join(repos_dir, formula_name + "-formula")

            # Split things out into multiple steps and checks to be Ctrl-c resilient
            if os.path.isdir(repo_dir):
                repo = Repo(repo_dir)
            else:
                repo = Repo.init(repo_dir)

            try:
                origin = repo.remotes.origin
            except AttributeError:
                origin = repo.create_remote('origin', formula['url'])

            # Work out what the wanted sha is
            if 'sha' not in formula:
                target_sha = rev_to_sha(repo, origin, formula['revision'])
                if target_sha is None:
                    # This shouldn't happen as rev_to_sha should throw. Safety net
                    raise RuntimeError("No sha resolved!")
                formula['sha'] = target_sha

            if previously_fetched is not None:
                # The revisions might be specified as different strings but
                # resolve to the same. So resolve both and check
                if previously_fetched['sha'] != formula['sha']:
                    raise RuntimeError(dedent("""
                        Formula revision clash for {name}:
                        - {old[revision]} <{old_sha}> (defined in {old[source]})
                        + {new[revision]} <{new_saw}> (defined in {new[source]})""".format(
                        name=formula_name,
                        old=previously_fetched,
                        old_sha=previously_fetched['sha'][0:7],
                        new=formula,
                        new_sha=formula['sha'][0:7])
                    ))
                continue

            if not repo.head.is_valid() or repo.head.commit.hexsha != target_sha:
                repo.head.reset(commit=target_sha, index=True, working_tree=True)

            logger.debug("{formula} {revision}".format(formula=formula_name, revision=formula['revision']))

            source = os.path.join(repo_dir, formula_name)
            target = os.path.join(root_dir, 'vendor', '_root', formula_name)
            if not os.path.exists(source):
                raise RuntimeError("%s: Source '%s' does not exist" % (name, source))
            if os.path.exists(target):
                raise RuntimeError("%s: Target '%s' conflicts with something else" % (name, target))
            os.symlink(source, target)

            fetched_formulas[formula_name] = formula

            # Check for recursive formula dep.
            new_req_file = os.path.join(repo_dir, 'formula-requirements.txt')
            if os.path.isfile(new_req_file):
                logger.info(
                    "Adding {new} to check form {old} {revision}".format(
                        new=new_req_file,
                        old=req_file,
                        revision=formula['revision']))
                requirements_files.append(new_req_file)

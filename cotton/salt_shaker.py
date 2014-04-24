import logging
import os
import sys
import re
import tempfile
import shutil
import stat

from git import Repo
from git.exc import GitCommandError
from textwrap import dedent


class Shaker(object):
    def __init__(self, root_dir, salt_root_path='vendor',
                 clone_path='formula-repos', salt_root='_root'):
        """
        There is a high chance you don't want to change the paths here.

        If you do, you'll need to change the paths in your salt config to ensure
        that there is an entry in `file_roots` that matches self.roots_dir
        (i.e., root_dir + salt_root_path + salt_root)
        """

        self.roots_dir = os.path.join(root_dir, salt_root_path, salt_root)
        self.repos_dir = os.path.join(root_dir, salt_root_path, clone_path)

        self._setup_git()
        self._setup_logger()
        self.fetched_formulas = {}
        self.parsed_requirements_files = set()
        self.first_requirement_file = os.path.join(root_dir, 'formula-requirements.txt')
        self.requirements_files = [
            self.first_requirement_file
        ]

        # This makes any explicit version requirements in from the
        # first_requirement_file override anything from further down. This is a
        # hack to avoid dependency hell until we get SemVer in
        self.override_version_from_toplevel = True

    def _create_dirs(self):
        """
        Keep this out of init, so we don't remove files without re-adding them.
        """

        # Delete the salt roots dir on each run.
        # This is because the files in roots_dir are just symlinks
        if os.path.exists(self.roots_dir):
            shutil.rmtree(self.roots_dir)
        os.makedirs(self.roots_dir)

        # Ensure the repos_dir exists
        if not os.path.exists(self.repos_dir):
            os.makedirs(self.repos_dir)

    def _setup_logger(self):
        logging.basicConfig()
        self.logger = logging.getLogger(__name__)

    def _setup_git(self):
        """
        Setup SSH to remove VisualHostKey - it breaks GitPython's attempt to
        parse git output :(

        Will delete file once the object gets GC'd
        """
        self.git_ssh_wrapper = tempfile.NamedTemporaryFile(prefix='cotton-git-ssh')

        self.git_ssh_wrapper.write("""#!/bin/bash
        ssh -o VisualHostKey=no "$@"
        """)
        self.git_ssh_wrapper.file.flush()
        os.fchmod(self.git_ssh_wrapper.file.fileno(), stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        os.environ['GIT_SSH'] = self.git_ssh_wrapper.name

    def _is_from_top_level_requirement(self, file):
        return file == self.first_requirement_file

    def parse_requirement(self, requirement_str):
        """
        Requirement parsing.  Returns a dict containg the full URL to clone
        (`url`), the name of the formula (`name`), a revision (if one is
        specified or 'master' otherwise) (`revision`), and a indication of if
        the revision was explicit or defaulted (`explicit_revision`).
        """
        requirement_str = requirement_str.strip()

        (url, name, rev,) = re.search(r'(.*?/([^/]*?)(?:-formula)?(?:\.git)?)(?:==(.*?))?$', requirement_str).groups()
        return {
            'url': url,
            'name': name,
            'revision': rev or 'master',
            'explicit_revision': bool(rev),
        }

    def parse_requirements_lines(self, lines, source_name):
        """
        Parse requirements from a list of lines, strips out comments and blank
        lines and yields the list of requirements contained, as returned by
        parse_requirement
        """
        for line in lines:
            line = re.sub('#.*$', '', line).strip()
            if not line or line.startswith('#'):
                continue

            req = self.parse_requirement(line)
            if req is None:
                continue

            req['source'] = source_name

            if self._is_from_top_level_requirement(source_name):
                req['top_level_requirement'] = True

            yield req

    def parse_requirements_file(self, filename):
        """
        Parses the formula requirements, and yields dict objects for each line.

        The parsing of each line is handled by parse_requirement
        """
        with open(filename, 'r') as fh:
            return self.parse_requirements_lines(fh.readlines(), filename)

    def install_requirements(self):
        self._create_dirs()

        while len(self.requirements_files):
            req_file = self.requirements_files.pop()
            if req_file in self.parsed_requirements_files:
                # Already parsed.
                continue

            self.parsed_requirements_files.add(req_file)

            self.logger.info("Checking %s" % req_file)
            for formula in self.parse_requirements_file(req_file):
                dir = self.install_requirement(formula)

                self.fetched_formulas[formula['name']] = formula

                # Check for recursive formula dep.
                new_req_file = os.path.join(dir, 'formula-requirements.txt')
                if os.path.isfile(new_req_file):
                    self.logger.info(
                        "Adding {new} to check form {old} {revision}".format(
                            new=new_req_file,
                            old=req_file,
                            revision=formula['revision']))
                    self.requirements_files.append(new_req_file)

    def check_for_version_clash(self, formula):
        """
        Will check to see if `formula` has already been installed and the
        version we requested clashes with the version we've already
        vendored/installed
        """
        previously_fetched = self.fetched_formulas.get(formula['name'], None)
        if previously_fetched:
            if previously_fetched['url'] != formula['url']:
                raise RuntimeError(dedent("""
                    Formula URL clash for {name}:
                    - {old[url]} (defined in {old[source]})
                    + {new[url]} (defined in {new[source]})""".format(
                    name=formula['name'],
                    old=previously_fetched,
                    new=formula)
                ))
        return previously_fetched

    def install_requirement(self, formula):
        """
        Install the requirement as specified by the formula dictionary and
        return the directory symlinked into the roots_dir
        """
        self.check_for_version_clash(formula)

        repo_dir = os.path.join(self.repos_dir, formula['name'] + "-formula")

        repo = self._open_repo(repo_dir, formula['url'])

        sha = self._resolve_sha(formula, repo)

        target = os.path.join(self.roots_dir, formula['name'])
        if sha is None:
            if os.path.exists(target):
                raise RuntimeError("%s: Formula marked as resolved but target '%s' didn't exist" % (formula['name'], target))
            return target

        # TODO: Check if the working tree is ditry, and (if request/flagged)
        # reset it to this sha
        if not repo.head.is_valid() or repo.head.commit.hexsha != sha:
            repo.head.reset(commit=sha, index=True, working_tree=True)

        self.logger.debug("{formula[name]} {formula[revision]}".format(formula=formula))

        source = os.path.join(repo_dir, formula['name'])
        if not os.path.exists(source):
            raise RuntimeError("%s: Source '%s' does not exist" % (formula['name'], source))
        if os.path.exists(target):
            raise RuntimeError("%s: Target '%s' conflicts with something else" % (formula['name'], target))
        os.symlink(source, target)

        return target

    def _resolve_sha(self, formula, repo):
        """
        Work out what the wanted sha is for this formula. If we have already
        satisfied this requirement then return None, else return the sha we
        want `repo` to be at
        """

        previously_fetched = self.fetched_formulas.get(formula['name'], None)

        if previously_fetched is not None and \
           previously_fetched.get('top_level_requirement', False) and \
           previously_fetched['explicit_revision'] and self.override_version_from_toplevel:
            self.logger.info("Overriding {name} version of {new_ver} to {old_ver} from project formula requirements".format(
                name=formula['name'],
                new_ver=formula['revision'],
                old_ver=previously_fetched['revision'],
            ))
            formula['sha'] = previously_fetched['sha']

            # Should already be up to date from when we installed
            # previously_fetched
            return None

        elif 'sha' not in formula:
            self.logger.debug("Resolving {formula[revision]} for {formula[name]}".format(
                formula=formula))

            target_sha = self._rev_to_sha(formula, repo)
            if target_sha is None:
                # This shouldn't happen as _rev_to_sha should throw. Safety net
                raise RuntimeError("No sha resolved!")
            formula['sha'] = target_sha

        if previously_fetched is not None:
            # The revisions might be specified as different strings but
            # resolve to the same. So resolve both and check
            if previously_fetched['sha'] != formula['sha']:

                raise RuntimeError(dedent("""
                    Formula revision clash for {new[name]}:
                    - {old[revision]} <{old_sha}> (defined in {old[source]})
                    + {new[revision]} <{new_sha}> (defined in {new[source]})""".format(
                    old=previously_fetched,
                    old_sha=previously_fetched['sha'][0:7],
                    new=formula,
                    new_sha=formula['sha'][0:7])
                ))

            # Nothing needed - we're already at the right sha
            return None

    def _open_repo(self, repo_dir, upstream_url):
        # Split things out into multiple steps and checks to be Ctrl-c resilient
        if os.path.isdir(repo_dir):
            repo = Repo(repo_dir)
        else:
            repo = Repo.init(repo_dir)

        try:
            repo.remotes.origin
        except AttributeError:
            repo.create_remote('origin', upstream_url)
        return repo

    def _rev_to_sha(self, formula, repo):
        """
        Try to resovle the revision into a SHA. If rev is a tag or a SHA then
        try to avoid doing a fetch on the repo if we already know about it. If
        it is a branch then make sure it is the tip of that branch (i.e. this
        will do a git fetch on the repo)
        """

        have_updated = False
        is_branch = False
        sha = None
        origin = repo.remotes.origin

        for attempt in range(0, 2):
            try:
                # Try a tag first. Treat it as immutable so if we find it then
                # we don't have to fetch the remote repo
                tag = repo.tags[formula['revision']]
                return tag.commit.hexsha
            except IndexError:
                pass

            try:
                # Next check for a branch - if it is one then we want to udpate
                # as it might have changed since we last fetched
                (full_ref,) = filter(lambda r: r.remote_head == formula['revision'], origin.refs)
                is_branch = True

                # Don't treat the sha as resolved until we've updated the
                # remote
                if have_updated:
                    sha = full_ref.commit.hexsha
            except (ValueError, AssertionError):
                pass

            # Could just be a SHA
            try:
                if not is_branch:
                    # Don't try to pass it to `git rev-parse` if we know it's a
                    # branch - this would just return the *current* SHA but we
                    # want to force an update
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
                msg = msg + " to see if %s has changed" % formula['revision']
            sys.stdout.write(msg)
            origin.fetch(refspec="refs/tags/*:refs/tags/*")
            origin.fetch()
            print(" done")

            have_updated = True

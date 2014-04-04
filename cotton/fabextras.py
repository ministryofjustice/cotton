from __future__ import print_function
import re
import sys
import time
import getpass
from fabric.api import settings, sudo, run, hide, local, task, parallel, env

from cotton.ssh_utils import rsync_project

from fabric.exceptions import NetworkError
from cotton.api import vm_task

# thanks to
# http://stackoverflow.com/questions/14693701/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
ansi_escape = re.compile(r'\x1b[^m]*m')

@vm_task
def iptables():
    """ 
    retrieve all iptables rules
    """
    command = "iptables -L"
    run_on_all_hosts(command)

def run_on_all_hosts(cmd):
    """ 
    Wrapper to run a given command on all hosts (including the master)
    """
    wrapped_command = "sudo salt '*' cmd.run '%s'" % cmd 
    run(wrapped_command)

@vm_task
def uptime():
    """
    execute uptime
    """
    run("uptime")


@vm_task
def ipython():
    """
    starts ipython within fabric context
    useful for development
    """
    # imports IPython internally to make it optional
    import IPython
    IPython.embed()


@vm_task
def ssh():
    from cotton.ssh_utils import ssh
    # Insecure
    insecure_string = ''
    if env.disable_known_hosts:
        insecure_string = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

    ssh(ssh_opts=insecure_string)


@vm_task
def ssh_forward(lport, rport):
    """
    open ssh session and tunnel port ssh_forward:local_port,remote_port
    """
    #TODO: enable it to work with env.gateway
    if 'key_filename' in env and env.key_filename:
        local('ssh -o "ServerAliveInterval 30" -A -i {key} -p {port} -L {lport}:127.0.0.1:{rport} {user}@{host}'.format(key=env.key_filename, user=env.user, host=env.host, port=env.port, lport=lport, rport=rport))
    else:
        local('ssh -o "ServerAliveInterval 30" -A -p {port} -L {lport}:127.0.0.1:{rport} {user}@{host}'.format(key=env.key_filename, user=env.user, host=env.host, port=env.port, lport=lport, rport=rport))


def is_not_empty(path, use_sudo=False, verbose=False):
    """
    Return True if given path exists on the current remote host.

    If ``use_sudo`` is True, will use `sudo` instead of `run`.

    `exists` will, by default, hide all output (including the run line, stdout,
    stderr and any warning resulting from the file not existing) in order to
    avoid cluttering output. You may specify ``verbose=True`` to change this
    behavior.
    """
    func = use_sudo and sudo or run
    cmd = 'test -s %s' % path  # was _expand_path
    # If verbose, run normally
    if verbose:
        with settings(warn_only=True):
            return not func(cmd).failed
    # Otherwise, be quiet
    with settings(hide('everything'), warn_only=True):
        return not func(cmd).failed


def wait_for_shell():
    """
    infinitely waits for shell on remote host
    i.e. after creation or reboot
    """
    print("Waiting for shell")
    with settings(hide('running')):
        while True:
            try:
                run("uptime")
                break
            except NetworkError:
                sys.stdout.write(".")
                sys.stdout.flush()
                time.sleep(1)
    print(" OK")


# [GR] Slightly modified to use Paul's new rsync library - old one will be deprecate once we're happy with this.
def smart_rsync_project(*args, **kwargs):
    """ 
    rsync_project wrapper that is aware of insecure fab argument and can chown the target directory

    :param for_user: optional, chowns the directory to this user at the end
    """
    if 'for_user' in kwargs:
        for_user = kwargs.pop('for_user')
    else:
        for_user = None
    directory = args[0]
  
    if env.disable_known_hosts:
        kwargs['ssh_opts'] = kwargs.get('ssh_opts', '') + " -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

    if for_user:
        with settings(warn_only=True):
            sudo("find {} -type d -exec chmod u+rwx {{}} +".format(directory))
            sudo("chown -R {} {}".format(env.user, directory))

    rsync_project(*args, **kwargs)

    if for_user:
        sudo("chown -R {} {}".format(for_user, directory))


def get_password(system, username, desc=None):
    """
    Wraps getpass and keyring to provide secure password functions.

    keyring will store the password in the system's password manager, i.e. Keychain
    on OS X.

    """
    import keyring
    if not desc:
        desc = "Password for user '%s': " % username

    password = keyring.get_password(system, username)
    if not password:
        password = getpass.getpass(desc)
        keyring.set_password(system, username, password)
    return password

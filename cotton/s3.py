"""
Tasks for managing Route S3
"""

import os
from functools import wraps

import boto
from boto.s3.connection import S3Connection, Location

from fabric.api import task, env
from fabric.contrib.console import confirm

from cotton import config

try:
    import config_aws
    config.aws = config_aws
except ImportError as e:
    import imp
    config.aws = imp.new_module("aws")


def requires_s3conn(func):
    """
    Decorator for all functions that need to access S3. Sets env.s3conn using
    get_s3_connection().
    """
    @wraps(func)
    def inner(*args, **kwargs):
        get_s3_connection()
        return func(*args, **kwargs)
    return inner

def get_s3_connection():
    """Establish a connection to S3.  Sets env.s3conn and return the conn."""
    if not env.get('s3conn'):
        env.s3conn = S3Connection(
            aws_access_key_id=config.aws.ACCESS_KEY_ID,
            aws_secret_access_key=config.aws.SECRET_ACCESS_KEY,
            host="s3-eu-west-1.amazonaws.com") # See https://github.com/boto/boto/issues/621#issuecomment-5417889
        assert env.s3conn is not None
    return env.s3conn

@requires_s3conn
def get_s3_id(name=None, all_images=False):
    """"""
    bucket = Bucket(env.s3conn, config.aws.S3_BUCKETS['GOLDEN_IMAGE_BUCKET'])
    if all_images:
        return [s3object for s3object in bucket]
    for s3object in bucket:
        for k, v in s3object.iteritems():
            print(k, v)


@task
@requires_s3conn
def create_bucket(name):
    """
    Makes a new S3 bucket.  Can use public_put to make a bucket public.
    """
    kwargs = {
        'location' : Location.EU
    }
    if env.get('s3_public'):
        kwargs['policy'] = 'public-read'
    bucket = env.s3conn.create_bucket(name, **kwargs)
    if env.get('s3_public'):
        bucket.set_acl('public-read')


@task
@requires_s3conn
def bucket(name):
    """
    Sets the bucket name to work on.
    """
    env.bucket = env.s3conn.get_bucket(name)


@task
def public_put():
    """
    Set any uploaded file to boto's public permissions.
    """
    env.s3_public = True


def put_file(source, filename, dest):
    key_name = os.path.join(dest, filename)
    print 'Copying %s to %s/%s' % (filename, env.bucket.name, key_name)
    key = env.bucket.new_key(key_name)
    metadata = key.metadata
    
    # Set text/html mime types
    html_mime_types = ['.html', '.php', '.htm']
    for mime_type in html_mime_types:
        if key.name.endswith(mime_type):
            metadata['Content-Type'] = 'text/html'
            
    kwargs = {}
    if env.get('s3_public'):
        kwargs['policy'] = 'public-read'
    key.set_contents_from_filename(source, **kwargs)
    


@task
def put(source, dest=""):
    """
    Upload a file or directory to an S3 bucket.
    
    Usage:
    
    fab a.s3.bucket:[bucket_name] a.s3.put:[dir or file][,dest_root]
    
    Add `a.s3.public_put` if the uploaded files should be publicly readable.
    
    """
    
    ignore = [
        '/.git'
    ]
    
    if dest.endswith('/'):
        # Strip a trailing slash
        dest = "%s*" % dest
    if env.bucket.name:
        if os.path.isdir(source):
            # We're putting a folder, so set dest to the folder name
            dest = os.path.split(source)[-1]
            # Find everything *before* the dir we're uploading
            local_root = os.path.join(*os.path.split(source)[:-1])
            for root, dirs, files in os.walk(source):
                for i in ignore:
                    if i in root:
                        break
                else:
                    # Strip the local path from the remote root
                    remote_root = root[len(local_root):]
                    for file in files:
                        # Full path to the local file
                        source = os.path.join(root, file)
                        filename = os.path.join(remote_root, file)
                        put_file(source, filename, dest)
        else:
            filename = os.path.split(source)[-1]
            put_file(source, filename, dest)

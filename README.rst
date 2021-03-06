cotton
======

Project independent shared fabric extensions to bootstrap first VM.

It solves three problems:
 - how to easily bootstrap VM in any supported environment
 - how to easily reach and manage this node
 - how to store
   - shared organisation config
   - shared project config
   - user unique/confidential config (typically used to store credentials only)

Depends on following fabric env variables::

    env.provider_zone = 'aws_dev'
    env.project = 'foo-dev'  # can also be a path
    env.vm_name = 'foo.master'

    #uncomment to always use shared provisioning key (only for early dev)
    env.provisioning = True


Environment is provider configuration.


Assumes that your config directory is next to directory containing fabfile.py::

    root/
    |-- application-deployment/
    |   `-- fabfile.py
    |
    |-- ~/.cotton.yaml / ${COTTON_CONFIG}
    |-- config/projects/{env.project}/cotton.yaml
    ...
    |-- config/projects/{env.project|split('/')[1]}/cotton.yaml
    |-- config/projects/{env.project|split('/')[0]}/cotton.yaml
    |-- config/projects/cotton.yaml
    |-- config/cotton.yaml
    |-- application-deployment/vagrant/cotton.yaml  # deprecated in favour to application-deployment/cotton.yaml
    `-- application-deployment/cotton.yaml

    I.e.:
    env.project = nomis/pvb/production

    cotton.yaml search path will look like:
    root/
    |
    |-- ~/.cotton.yaml / ${COTTON_CONFIG}
    |
    |-- config/projects/nomis/pvb/production/cotton.yaml
    |-- config/projects/nomis/pvb/cotton.yaml
    |-- config/projects/nomis/cotton.yaml
    |
    |-- config/projects/cotton.yaml
    |-- config/cotton.yaml
    |
    `-- application-deployment/cotton.yaml


example ~/.cotton.yaml::

    provider_zones:
      aws_dev:
        driver: aws
        aws_access_key_id: 'TBV'
        aws_secret_access_key: 'TBD'
        ssh_key: /Users/aceventura/.ssh/default
      my_static_name:
        driver: static
        hosts:
          - name: master
            ip: 1.2.3.4
          - name: master-staging
            ip: 1.2.3.5
      aws_staging:
        image_id: ami-3a689f4d
        provisioning_ssh_key: ../config/default.pem
        provisioning_ssh_key_name: default
        provisioning_user: ubuntu
        gateway: 1.2.3.4
        instance_type: m1.small
        security_groups:
          - default
          - ssh
          - web-server
          - salt-master
        region_name: eu-west-1
        driver: aws


driver status
-------------

:aws: fully implemented
:static: fully implemented (a good fallback if api access is not available)
:vcloud: only selection, status, filtering, termination, no provisioning part

cotton
======
Project independent shared fabric extensions to bootstrap first VM.

It solves three problems:
 - how to easily bootstrap VM in any supported environment
 - how to easily reach and manage this node
 - how to store
   - shared organisation config
   - shared project config
   - user unique/confidential config

Depends on following fabric env variables::

    env.environment = 'aws_dev'
    env.project = 'foo-dev'
    env.vm_name = 'foo.master'

    #uncomment to always use shared provisioning key (only for early dev)
    env.provisioning = True


Environment is provider configuration.


Assumes that your config directory is next to directory containing fabfile.py::


    root/
    |-- application-deployment/
    |   `-- fabfile.py
    |-- config.user/config.yaml
    |-- config/projects/{project}/config.yaml
    `-- config/config.yaml



example config.user/config.yaml::


    environment:
      aws_dev:
        aws_access_key_id: 'TBV'
        aws_secret_access_key: 'TBD'
        ssh_key: /Users/aceventura/.ssh/default

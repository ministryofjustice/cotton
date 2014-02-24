cotton
======
Project independent shared fabric extensions to bootstrap first VM.

It solves two problems:
 - how to easily bootstrap VM in any supported environment
 - how to store
   - shared organisation config
   - shared project config
   - user unique/confidential config


Assumes that your config directory is next to directory containing fabfile.py:

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

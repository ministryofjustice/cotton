cotton
======
Project independent shared fabric extensions code to bootstrap first VM.

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

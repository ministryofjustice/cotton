## Version 0.2.5

* Salt Shaker will now link custom states,modules,grain facts etc. into the managed root dir so we can write them in our formulas.
* salt/salt-call wrapper that parses output of highstate and aborts on state failure (a must have for jenkins)
* Salt Shaker shell magic tasks (check, freeze, shaker) that helps to understand status of modules
* fix for fabric taks argument naming conflict: roles->salt_roles

## Version 0.2.4

* Fix setup.py to install data files (salt bootstrap scripts)

## Version 0.2.3

* Start of changelog

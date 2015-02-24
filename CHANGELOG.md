## Version 0.5.1

 * Allow to ssh through jumpbox to VMs w/o public dns entry (EC2)

## Version 0.5.0

 * Allow to disable top.sls parsing when shipping pillars

## Version 0.4.0

 * Enable env.project to be a path
 * Remove deprecated ../config.user

## Version 0.3.3

 * Allow AWS driver to supply other boto connection objects

## Version 0.3.2

 * Bump version in setup.py

## Version 0.3.1

 * Allow to disable key based authentication during provisioning
 * Allow to manage gateway/jump box user separately
 * Add vitruvius file
 * Allow to provide cotton config for vagrant
 * Allow to configure EBS
 * Bugfixes

## Version 0.2.5

* Salt Shaker will now link custom states,modules,grain facts etc. into the managed root dir so we can write them in our formulas.
* salt/salt-call wrapper that parses output of highstate and aborts on state failure (a must have for jenkins)
* Salt Shaker shell magic tasks (check, freeze, shaker) that helps to understand status of modules
* fix for fabric taks argument naming conflict: roles->salt_roles

## Version 0.2.4

* Fix setup.py to install data files (salt bootstrap scripts)

## Version 0.2.3

* Start of changelog

%%%MetaData
status: Live
version: v0.2.4
author: webops <webops@digital.justice.gov.uk>
description: Project independent shared fabric extensions to bootstrap first VM and manage configuration within team
lastUpdated: 7/10/2014
department: MOJ DS
tags: fabric, ops, webops, deployment, aws, boto, libcloud, python
type: component
%%%

# cotton
Project independent shared fabric extensions to bootstrap first VM.

It solves three problems:

 - how to easily bootstrap VM in any supported environment
 - how to easily reach and manage this node
 - how to store
   - shared organisation config
   - shared project config
   - user unique/confidential config (typically used to store credentials only)

import sys
import libcloud
from fabric.api import task, env
from cotton.api import vm_task, load_provider
from cotton.colors import *
from pptable import pptable

@task
def debug():
    """
    Enable vcloud/libcloud logging
    """
    libcloud.enable_debug(sys.stdout)

@task
@load_provider
def vdcs():
    """
    vcloud: Lists information about the VDCs in this organization
    """
    items = []

    for vdc in env.provider.connection.vdcs:
        items.append({
            'vDC Name': vdc.name,
            'CPU used': vdc.cpu.used,
            'CPU limit': vdc.cpu.limit,
            'Mem used': vdc.memory.used,
            'Mem limit': vdc.memory.limit,
            'Storage': vdc.storage.used,
            'Storage limit': vdc.storage.limit
        })
    pptable(items, headers=['vDC Name', 'CPU used', 'CPU limit', 'Mem used', 'Mem limit', 'Storage', 'Storage limit'])

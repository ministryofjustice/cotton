from __future__ import print_function

from functools import wraps

from fabric.api import task, env, prompt, abort, warn
import re

from cotton import common
from cotton import config
from cotton.colors import *
from cotton.common import current_instance


try:
    import config_vcloud
    config.vcloud = config_vcloud
except ImportError as e:
    import imp
    config.vcloud = imp.new_module('vcloud')


def requires_vcloud_conn(func):
    """
    Decorator for all functions that need vCloud access.

    Sets env.vcloud_conn using get_vcloud_connection
    """
    @wraps(func)
    def inner(*args, **kwargs):
        get_vcloud_connection()
        return func(*args, **kwargs)
    return inner

# Monkey patched into the VCloud Driver instance
import libcloud.compute.drivers.vcloud
from libcloud.compute.drivers.vcloud import \
    fixxpath, get_url_path, VCloudResponse, VCloud_1_5_Connection
from libcloud.compute.types import NodeState, MalformedResponseError
from libcloud.utils.py3 import urlencode


# Switch over to lxml for parsing/finding rather than xml.etree - we need the
# better xpath support
class ImprovedVCloudResponse(VCloudResponse):
    def parse_body(self):
        from lxml import etree as lxml_ET
        if len(self.body) == 0 and not self.parse_zero_length_body:
            return self.body

        try:
            body = lxml_ET.XML(self.body)
        except Exception as e:
            raise MalformedResponseError('Failed to parse XML %s' % e,
                                         body=self.body,
                                         driver=self.connection.driver)
        return body

    def parse_error(self):
        res = self.parse_body()

        return ET.tostring(res)

class ImprovedVCloud_1_5_Connection(VCloud_1_5_Connection):
    responseCls = ImprovedVCloudResponse

class ImprovedVCloud_5_1_Driver(libcloud.compute.drivers.vcloud.VCloud_5_1_NodeDriver):

    connectionCls = ImprovedVCloud_1_5_Connection

    def _ex_connection_class_kwargs(self):
        return { 'timeout': 20000 }

    # The base implementation of this doesn't cope with you have a net work
    # called "Default" in every VDC - it would just pick one at random. This
    # hack lets us specify the network name as a URL and just use it as is.
    def _get_network_href(self, network_name):
        if network_name.startswith("http://") or network_name.startswith("https://"):
            return network_name
        return super(ImprovedVCloud_5_1_Driver, self)._get_network_href(network_name)


    # Based on
    # http://pubs.vmware.com/vcloud-api-1-5/api_prog/
    # GUID-843BE3AD-5EF6-4442-B864-BCAE44A51867.html

    # Mapping from vCloud API state codes to libcloud state codes
    NODE_STATE_MAP = {'-1': NodeState.UNKNOWN,
                      '0': NodeState.PENDING,
                      '1': NodeState.PENDING,
                      '2': NodeState.PENDING,
                      '3': NodeState.PENDING,
                      '4': NodeState.RUNNING,
                      '5': NodeState.RUNNING,
                      '6': NodeState.UNKNOWN,
                      '7': NodeState.UNKNOWN,
                      # Change this from TERMINATED (which means can't be started) to just STOPPED
                      '8': NodeState.STOPPED,
                      '9': NodeState.UNKNOWN,
                      '10': NodeState.UNKNOWN}

    # Pull out CPU, Memory and creator in addition to defaults.
    def _to_node(self, node_elm):
        node = super(ImprovedVCloud_5_1_Driver, self)._to_node(node_elm)

        virt_hardware = node_elm.find('.//ovf:VirtualHardwareSection', namespaces=node_elm.nsmap)

        n_cpu = 0
        n_ram = 0
        for item in virt_hardware.findall('ovf:Item', namespaces=node_elm.nsmap):

            res_type = item.findtext("{%s}ResourceType" % item.nsmap['rasd'])

            if res_type == '3': # CPU
                n_cpu = int(item.findtext('{%s}VirtualQuantity' % item.nsmap['rasd']))
            elif res_type == '4': # Memory
                n_ram = int(item.findtext('{%s}VirtualQuantity' % item.nsmap['rasd']))

        node.size = self._to_size(n_ram)
        node.size.cpus = n_cpu
        node.extra['size'] = _find_node_size(node.size)

        user = node_elm.find(fixxpath(node_elm, 'Owner/User'))
        node.extra['creator'] = user.get('name')
        return node

    # Same as base, but length of 30, not 15
    @staticmethod
    def _validate_vm_names(names):
        if names is None:
            return
        hname_re = re.compile(
            '^(([a-zA-Z]|[a-zA-Z][a-zA-Z0-9]*)[\-])*([A-Za-z]|[A-Za-z][A-Za-z0-9]*[A-Za-z0-9])$')  # NOQA
        for name in names:
            if len(name) > 30:
                raise ValueError(
                    'The VM name "' + name + '" is too long for the computer '
                    'name (max 30 chars allowed).')
            if not hname_re.match(name):
                raise ValueError('The VM name "' + name + '" can not be '
                                 'used. "' + name + '" is not a valid '
                                 'computer name for the VM.')

    # As a hack pass an IP address in the ipmode parameter. Until we fix
    # libcloud to support this its the only way to get the info nicely down
    # to a layer we can add support on without having to re-write the
    # entirety of create_node
    def _validate_vm_ipmode(self, vm_ipmode):
        if type(vm_ipmode) is tuple and vm_ipmode[0] is 'MANUAL':
            return True
        else:
            return super(ImprovedVCloud_5_1_Driver, self)._validate_vm_ipmode(vm_ipmode)

    # Related to above manual IP mode addition
    def _change_vm_ipmode(self, vapp_or_vm_id, vm_ipmode):
        if type(vm_ipmode) is not tuple or vm_ipmode[0] is not 'MANUAL':
            return super(ImprovedVCloud_5_1_Driver, self)._change_vm_ipmode(vapp_or_vm_id, vm_ipmode)

        vm_ipmode, ip_address = vm_ipmode
        vms = self._get_vm_elements(vapp_or_vm_id)

        for vm in vms:
            res = self.connection.request(
                '%s/networkConnectionSection' % get_url_path(vm.get('href')))
            net_conns = res.object.findall(
                fixxpath(res.object, 'NetworkConnection'))
            for c in net_conns:
                # TODO: What if we want a network other than 'default'
                c.attrib['network'] = 'Default'
                c.find(fixxpath(c, 'IpAddressAllocationMode')).text = vm_ipmode
                c.find(fixxpath(c, 'IsConnected')).text = "true"

                # This is quite hacky. We probably don't want the same IP on
                # each interface etc.
                # We might not have an IP node
                ip = c.find(fixxpath(c, 'IpAddress'))
                if ip is None:
                    ip = ET.SubElement(c, fixxpath(c, 'IpAddress'))
                    # The order of the IpAddress element matter. Has to be after this :(
                    conIdx = c.find(fixxpath(c, 'NetworkConnectionIndex'))
                    c.remove(ip)
                    c.insert(c.index(conIdx)+1, ip)
                ip.text = ip_address

            headers = {
                'Content-Type':
                'application/vnd.vmware.vcloud.networkConnectionSection+xml'
            }

            res = self.connection.request(
                '%s/networkConnectionSection' % get_url_path(vm.get('href')),
                data=ET.tostring(res.object),
                method='PUT',
                headers=headers
            )
            self._wait_for_task_completion(res.object.get('href'))

    # New method. Set multiple metadata entries in a single request rather than
    # one req per entry
    def ex_set_metadata_entries(self, node, **kwargs):
        from xml.etree import ElementTree as ET
        """
        :param node: node
        :type node: :class:`Node`

        :param key: metadata key to be set
        :type key: ``str``

        :param value: metadata value to be set
        :type value: ``str``

        :rtype: ``None``
        """
        metadata_elem = ET.Element(
            'Metadata',
            {'xmlns': "http://www.vmware.com/vcloud/v1.5",
             'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance"}
        )

        for key,value in kwargs.items():
            entry = ET.SubElement(metadata_elem, 'MetadataEntry')
            key_elem = ET.SubElement(entry, 'Key')
            key_elem.text = key
            value_elem = ET.SubElement(entry, 'Value')
            value_elem.text = value

        # send it back to the server
        res = self.connection.request(
            '%s/metadata' % get_url_path(node.id),
            data=ET.tostring(metadata_elem),
            headers={
                'Content-Type': 'application/vnd.vmware.vcloud.metadata+xml'
            },
            method='POST')
        self._wait_for_task_completion(res.object.get('href'))


    # Added the format parameter. Most of this function is just a duplication
    # of the super method
    def ex_query(self, type, filter=None, format='records', page=1, page_size=100, sort_asc=None,
                 sort_desc=None):
        """
        Queries vCloud for specified type. See
        http://www.vmware.com/pdf/vcd_15_api_guide.pdf for details. Each
        element of the returned list is a dictionary with all attributes from
        the record.

        :param type: type to query (r.g. user, group, vApp etc.)
        :type  type: ``str``

        :param filter: filter expression (see documentation for syntax)
        :type  filter: ``str``

        :param format: format type from query
        :type  format: ``str``

        :param page: page number
        :type  page: ``int``

        :param page_size: page size
        :type  page_size: ``int``

        :param sort_asc: sort in ascending order by specified field
        :type  sort_asc: ``str``

        :param sort_desc: sort in descending order by specified field
        :type  sort_desc: ``str``

        :rtype: ``list`` of dict
        """
        # This is a workaround for filter parameter encoding
        # the urllib encodes (name==Developers%20Only) into
        # %28name%3D%3DDevelopers%20Only%29) which is not accepted by vCloud
        params = {
            'type': type,
            'pageSize': page_size,
            'page': page,
            'format': format,
        }
        if sort_asc:
            params['sortAsc'] = sort_asc
        if sort_desc:
            params['sortDesc'] = sort_desc

        url = '/api/query?' + urlencode(params)
        if filter:
            if not filter.startswith('('):
                filter = '(' + filter + ')'
            url += '&filter=' + filter.replace(' ', '+')

        results = []
        res = self.connection.request(url)
        for elem in res.object:
            if not elem.tag.endswith('Link'):
                result = elem.attrib
                result['type'] = elem.tag.split('}')[1]
                results.append(result)
        return results

    # Print '.' while waiting rather than just being silent
    def _wait_for_task_completion(self, task_href,
                                  timeout=6000):

        import time
        from sys import stdout
        start_time = time.time()
        res = self.connection.request(get_url_path(task_href))
        status = res.object.get('status')
        while status != 'success':
            if status == 'error':
                # Get error reason from the response body
                error_elem = res.object.find(fixxpath(res.object, 'Error'))
                error_msg = "Unknown error"
                if error_elem is not None:
                    error_msg = error_elem.get('message')
                raise Exception("Error status returned by task %s.: %s"
                                % (task_href, error_msg))
            if status == 'canceled':
                raise Exception("Canceled status returned by task %s."
                                % task_href)
            if (time.time() - start_time >= timeout):
                raise Exception("Timeout (%s sec) while waiting for task %s."
                                % (timeout, task_href))

            stdout.write('.')
            stdout.flush()
            time.sleep(5)
            res = self.connection.request(get_url_path(task_href))
            status = res.object.get('status')

# Used by the requires_vcloud_conn decorator - connect to the vCloud director
# with the right org.
def get_vcloud_connection():
    if not env.get('vcloud_conn'):
        orgs = config.vcloud.ORGANIZATIONS
        org = orgs[ env.get('vcloud_org', orgs.keys()[0]) ]
        env.vcloud_conn = ImprovedVCloud_5_1_Driver(
            key='%(user)s@%(org)s' % {
                'user': config.vcloud.USERNAME,
                # Does the org we use matter? Probably!
                'org': org['name']
            },
            secret=config.vcloud.PASSWORD,
            host=config.vcloud.API_HOST,
        )
        env.vcloud_conn.connection.check_org()
    return env.vcloud_conn

@task
def org(name):
    """
    vcloud: Select an organization.

    Must be specified before any other node selector.

    For example:

      fab vc.org:org-2 vc.name:bastion vc.info

    name is one of the keys in config.vcloud.ORGANIZATIONS. The default is the
    first key in this dict
    """
    if env.has_key('vcloud_conn'):
        abort(red("Already connected - can't change organization!", bold=True))

    orgs = config.vcloud.ORGANIZATIONS
    if not orgs.has_key(name):
        abort(red('No configuration found for %s under ORGANIZATIONS' % name, bold=True))
    env.vcloud_org = name


@requires_vcloud_conn
def create_vapp(name, size, vdc,
    image=None,
    net_fence='bridged',
    network='Default',
    ip_address=None,
    tags={}):

    size = config.vcloud.VM_SIZES.get(size, None)
    if size is None:
        abort(red('VM size %s is not defined in the config' % size, bold=True))

    conn = env.vcloud_conn

    if image is None:
        cfg = _org_config()
        from libcloud.compute.base import NodeImage

        image = NodeImage(
            id = 'https://%s/api/vAppTemplate/vappTemplate-%s' %
                ( conn.connection.host, cfg['default-template'] ),
            name = 'unkown name',
            driver = conn,
        )

    # Libcloud doesn't find networks right when the name is shared across vDCs.
    res = conn.ex_query(
        type='orgVdcNetwork',
        filter='vdcName==%s;name==%s' % ( vdc, network ),
        format='references'
    )

    if not res:
        abort(red("Cannot find network '%s' in vDC '%s'!" % ( network, vdc), bold=True) )
    network = res[0]['href']

    node = conn.create_node(
        image=image,
        name=name,
        ex_vdc=vdc,
        ex_vm_fence=net_fence,
        ex_network=network,
        ex_vm_memory=size['memory'],
        ex_vm_cpu=size['cpu'],
        ex_vm_names=[name],
        ex_vm_ipmode=ip_address,
    )

    conn.ex_set_metadata_entries(node, **tags)


@requires_vcloud_conn
def _org_config():
    env.vcloud_conn.connection.check_org()
    our_org = env.vcloud_conn.org
    for name, conf in config.vcloud.ORGANIZATIONS.items():
        if our_org.endswith( '/' + conf['uuid']):
            return conf
    abort("Could not find org config blog for %s" % our_our)

@requires_vcloud_conn
def org_name():
    env.vcloud_conn.connection.check_org()
    our_org = env.vcloud_conn.org
    for name, conf in config.vcloud.ORGANIZATIONS.items():
        if our_org.endswith( '/' + conf['uuid']):
            return name
    return our_org

@task
@requires_vcloud_conn
def name(name):
    """
    vcloud: Select a host by name from the current vCloud org
    """
    res = env.vcloud_conn.ex_query('vApp', 'name==%s' % name)

    if not res:
        warn(red("vApp {} cannot be found".format(name)))
    else:
        driver = env.vcloud_conn
        for i in res:
            res = driver.connection.request(
                i['href'],
                headers={'Content-Type':
                         'application/vnd.vmware.vcloud.vApp+xml'}
            )
            node = driver._to_node(res.object)
            env.hosts.append(node.name)
            env.providerforhost[node.name] = 'vcloud'
            env.instances[node.name] = node

@task
@requires_vcloud_conn
@current_instance
def terminate(instance):
    """
    vcloud: poweroff vApp and contained VMs then delete it
    """
    info()

    if env.force:
        sure = 'T'
    else:
        sure = prompt(red("Type 'T' to confirm termination"), default='N')

    if sure == 'T':
        print("Terminating")
        env.vcloud_conn.destroy_node(instance)
    else:
        print("Aborting termination")

@task
@requires_vcloud_conn
@current_instance
def info(instance):
    """
    vcloud: display detailed info about vApp instance
    """
    NODE_STATE_TO_STRING = {
        NodeState.RUNNING: 'running',
        NodeState.REBOOTING: 'rebooting',
        NodeState.TERMINATED: 'terminated',
        NodeState.PENDING: 'pending',
        NodeState.UNKNOWN: 'unknown',
        NodeState.STOPPED: 'stopped',
    }

    p_info = lambda key, value: print(yellow("{:<12} {}".format(key, value)))

    print(green("Info", bold=True))
    p_info("vApp", instance.name)
    p_info("vDC", instance.extra['vdc'])
    p_info("id", instance.uuid)
    p_info("Creator", instance.extra['creator'])
    p_info("Size", _find_node_size(instance.size))

    if len(instance.extra['vms']) > 1:
        print(red("vApp contains more than one VM - this is discoureaged"))

    for vm in instance.extra['vms']:
        ips = vm['private_ips']
        p_info("Machine name", vm['name'])
        p_info("IP", ips[0] if len(ips) else 'None')
        p_info("State", NODE_STATE_TO_STRING[ vm['state'] ] )

# Walk the defined sizes in the config and work out which bucket we fit into.
def _find_node_size(node_size):
    for name,size in sorted(config.vcloud.VM_SIZES.items(), key=lambda t: t[1]):
        if node_size.ram <= size['memory'] and node_size.cpus <= size['cpu']:
            return name
    return 'xx-large-unknown'



@requires_vcloud_conn
def _wait_for_private_ips(node):
    import time
    from sys import stdout
    conn = env.vcloud_conn
    stdout.write("Waiting for private IPs to be allocated")
    stdout.flush()
    timeout = 600
    wait_period = 3
    start = time.time()
    end = start + timeout
    while time.time() < end:
        node = conn._to_node(conn.connection.request(node.id).object)

        if node.private_ips:
            print("")
            return node

        stdout.write('.')
        stdout.flush()
        time.sleep(wait_period)
        continue
    raise "Exception - timed out waiting for IPs to be allocated"

@requires_vcloud_conn
def _get_bastion_ip(vdc, network='Default'):
    conn = env.vcloud_conn
    # We need query format of references else we can't search by the related
    # (i.e. to find the network in the given org)
    res = conn.ex_query(
        type='orgVdcNetwork',
        filter='vdcName==%s;name==%s' % ( vdc, network ),
        format='references')

    if not res:
        abort(red("Cannot find network '%s' in vDC '%s'!" % ( network, vdc), bold=True) )

    net = conn.connection.request(res[0]['href']).object
    # Bit of a complex xpath expression. We want to find the ExternalIpAddress from this block:
    # <PortForwardingRule>
    #   <ExternalIpAddress>a.b.c.d</ExternalIpAddress>
    #   <ExternalPort>22</ExternalPort>
    #   <InternalIpAddress>10.220.0.2</InternalIpAddress>
    #   <InternalPort>22</InternalPort>
    #   <Protocol>TCP</Protocol>
    # </PortForwardingRule>
    #
    # Everything is namespaced though. Sigh.
    # http://stackoverflow.com/questions/6920073/how-to-use-xpath-from-lxml-on-null-namespaced-nodes
    nsmap = net.nsmap
    nsmap['vmware'] = nsmap.pop(None)

    ip = net.xpath("""
      .//vmware:PortForwardingRule[
          vmware:InternalPort/text()="22"
      ]/vmware:ExternalIpAddress/text()
      """,
      namespaces=nsmap)

    if not ip:
        raise Exception("Could not find a PortForwardingRule with InternalPort of 22 in %s"
            % (vdc))

    return ip[0]

@task
@requires_vcloud_conn
def vdcs():
    """
    vcloud: List informmation about the VDCs in this organization
    """
    table = TextTable(max_width=0)
    table.set_deco(0) # Don't draw any border chars
    headers = ('vDC Name', 'CPU used', 'CPU limit', 'Mem used', 'Mem limit', 'Storage', 'Storage limit')
    table.header([green(h, bold=True) for h in headers])
    table.set_cols_align(['l' ] * len(headers))

    for vdc in env.vcloud_conn.vdcs:
        table.add_row([
            yellow(vdc.name),
            vdc.cpu.used,
            vdc.cpu.limit,
            vdc.memory.used,
            vdc.memory.limit,
            vdc.storage.used,
            vdc.storage.limit
        ])

    print(table.draw())

@requires_vcloud_conn
@current_instance
def hostroles(instance):
    """
    Return the host's roles based on the vCloud metadata tags
    """
    metadata = env.vcloud_conn.ex_get_metadata(instance)

    return metadata.get('roles', '').split(',')

@requires_vcloud_conn
@current_instance
def hoststack(instance):
    """
    Return the host's roles based on the vCloud metadata tags
    """
    metadata = env.vcloud_conn.ex_get_metadata(instance)

    return metadata.get('stack', 'dev')

@requires_vcloud_conn
@current_instance
def getgrains(instance):
    grains = env.vcloud_conn.ex_get_metadata(instance)
    grains['name'] = instance.name
    grains['roles'] = grains.get('roles', '').split(',')
    return grains

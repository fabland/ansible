#!/usr/bin/python

# Copyright: (c) 2015, Ansible, Inc.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# copied and modified from vca_vapp.py

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: vcd_network

short_description: Manages networks in vCloud Director instances.

description:
  - "This module create networks if they don't exist or delete them (if state == absent).
  It is not modifying networks at the moment if they already exist."

version_added: "2.5"

author:
- Fabian Landis (@fabland)

options:
  state:
    description:
      - "State present will create the network if it doesn't exist, state absent will delete it."
    default: present
    choices: ['present', 'absent']
  metadata:
    description:
      - "Dictionary of name and value entries that are added to the network (as vcloud metadata type string)"
  network_name:
    description:
    - "Name of the network"      
  network_type:
    description:
    - "Type of network to create. Depending on type some parameters might be needed."
    choices: ['isolated', 'direct', 'bridged', 'natRouted']
    default: isolated
  parent:
    description:  
    - "Name of the parent network (for direct networks)"
  primary_dns_ip:
    description:
    - "IP of the primary DNS server for this network (for isolated networks)"   
  secondary_dns_ip:
    description:
    - "IP of the secondary DNS server for this network (for isolated networks)"   
  dns_suffix:
    description:
    - "DNS suffix (for isolated networks)"   
  gateway_ip:
    description:
    - "IP address of the gateway of the new network (for isolated networks)"   
  netmask:
    description:
    - "network mask for the gateway (for isolated networks)"   
  ip_range_start:
    description:
    - "Start address of the IP ranges used for static pool allocation in the network (for isolated networks)"   
  ip_range_end:
    description:
    - "End address of the IP ranges used for static pool allocation in the network (for isolated networks)"   
  dhcp_enabled:
    description:
    - "Enable/Disable DHCP service on the new network (for isolated networks)"
    default: false
    type: bool
  dhcp_ip_range_start:
    description:
    - "Start address of the IP range used for DHCP addresses (for isolated networks)"   
  dhcp_ip_range_end:
    description:
    - "End address of the IP range used for DHCP addresses (for isolated networks)"
  shared:
    description:
    - "Share network with VDC"
    default: false
    type: bool
extends_documentation_fragment: vcd_utils
'''

EXAMPLES = '''
  vars:
     internal_vm_ip: 10.0.0.50
     vcd_connection_common:
        host: "my.vcloud.host"
        username: "{{ vcloud_user_name }}"
        password: "{{ vcloud_password }}"
        org: myorg
        vdc_name: myvdc
        verify_certs: no
        api_version: "29.0"
  tasks:
   # Example how to create an isolated network
     - name: Isolated net
       vcd_network:
         vcd_connection: "{{ vcd_connection_common }}"
         network_name: my-vapp-net01
         network_type: isolated
         state: present
         primary_dns_ip: "8.8.8.8"
         secondary_dns_ip: "8.8.4.4"
         dns_suffix: "example.com"
         gateway_ip: "192.168.7.1"
         netmask: "255.255.255.0"
         ip_range_start: "192.168.7.2"
         ip_range_end: "192.168.7.100"
         dhcp_enabled: true
         dhcp_ip_range_start: "192.168.7.100"
         dhcp_ip_range_end: "192.168.7.150"
         metadata:
           mytagx: metadatavalue
           mytagy: "some other value"
'''

from ansible.module_utils.vcd_utils import VcdAnsibleModule, VcdError
import logging

NET_STATES = ['present', 'absent']

NET_TYPES = ['isolated', 'direct', 'bridged', 'natRouted']

def get_instance(module):
    network_type = module.params['network_type']
    network_name = module.params['network_name']
    inst = dict(network_name=network_name, network_type=network_type, state='absent')
    net_dict = None
    if network_type == 'isolated':
        nets = module.vdc.list_orgvdc_isolated_networks()
        for net in nets:
            if net.get('name') == network_name:
                net_dict = net
                break
    elif network_type == 'direct':
        nets = module.vdc.list_orgvdc_direct_networks()
        for net in nets:
            if net.get('name') == network_name:
                net_dict = net
                break
    else:
        module.fail('Not implemented yet')

    try:
        if net_dict is not None:
            status = net_dict['status']
            inst['status'] = VAPP_STATUS.get(status, 'unknown')
            inst['state'] = 'deployed' if status in ['Deployed', 'Powered on'] else 'undeployed'
        return inst
    except VcdError:
        return inst


def create(module):
    # TODO implement metadata setting
    network_type = module.params['network_type']
    network_name = module.params['network_name']
    if network_type == 'isolated':
        result = module.vdc.create_isolated_vdc_network(
            network_name=network_name,
            gateway_ip=module.params['gateway_ip'],
            netmask=module.params['netmask'],
            description='created by ansible',
            primary_dns_ip=module.params['primary_dns_ip'],
            secondary_dns_ip=module.params['secondary_dns_ip'],
            dns_suffix=module.params['dns_suffix'],
            ip_range_start=module.params['ip_range_start'],
            ip_range_end=module.params['ip_range_end'],
            is_dhcp_enabled=module.params['dhcp_enabled'],
            dhcp_ip_range_start=module.params['dhcp_ip_range_start'],
            dhcp_ip_range_end=module.params['dhcp_ip_range_end'],
            is_shared=module.params['shared'])
        for task in result.Tasks.Task:
            module.wait_for_task(task)
    elif network_type == 'direct':
        result = module.vdc.create_directly_connected_vdc_network(
            network_name=network_name,
            parent_network_name=module.params['parent_network_name'],
            description='created by ansible',
            is_shared=module.params['shared'])
        for task in result.Tasks.Task:
            module.wait_for_task(task)
    else:
        module.fail('Not implemented yet')

    module.vdc.reload()

    # TODO: for network
    # if module.params['metadata'] is not None:
    #     vapp = module.get_vapp(vapp_name)
    #     for name, value in module.params['metadata'].items():
    #         vapp.set_metadata(key=name, value=value, domain='GENERAL', visibility='READWRITE')

def delete(module):
    network_type = module.params['network_type']
    network_name = module.params['network_name']
    if network_type == 'isolated':
        task = module.vdc.delete_isolated_orgvdc_network(
            name=network_name,
            force=True)
        module.wait_for_task(task)
    elif network_type == 'direct':
        task = module.vdc.delete_direct_orgvdc_network(
            name=network_name,
            force=True)
        module.wait_for_task(task)
    else:
        module.fail('Not implemented yet')

def main():

    argument_spec = dict(
        network_name=dict(required=True),
        metadata=dict(required=False, type='dict'),
        state=dict(default='present', choices=NET_STATES),
        network_type=dict(default='isolated', choices=NET_TYPES),
        parent=dict(required=False, type='str'),
        primary_dns_ip=dict(required=False, type='str'),
        secondary_dns_ip=dict(required=False, type='str'),
        dns_suffix=dict(required=False, type='str'),
        gateway_ip=dict(required=False, type='str'),
        netmask=dict(required=False, type='str'),
        ip_range_start=dict(required=False, type='str'),
        ip_range_end=dict(required=False, type='str'),
        dhcp_enabled=dict(default=False, type='bool'),
        dhcp_ip_range_start=dict(required=False, type='str'),
        dhcp_ip_range_end=dict(required=False, type='str'),
        shared=dict(default=False, type='bool')
    )

    module = VcdAnsibleModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    state = module.params['state']

    instance = get_instance(module)

    result = dict(changed=False)

    if state == 'absent':
        if not module.check_mode and instance['state'] != 'absent':
            delete(module)
            result['changed'] = True
    elif state != 'absent':
        if not module.check_mode:
            create(module)
            result['changed'] = True

    return module.exit(**result)


if __name__ == '__main__':
    main()

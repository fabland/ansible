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
module: vcd_vm

short_description: Manages VMs in vCloud Director instances.

description:
  - "This module will actively managed VMs in vCloud Director instances.
  Instances can be created and deleted as well as both started and stopped."

version_added: "2.5"

author:
- Fabian Landis (@fabland)

options:
  vm_name:
    description:
      - The name of the vCloud VM
    required: true
  vm_hostname:
    description:
      - The hostname of the VM
    required: true
  catalog:
    description:
      - Catalog that contains the template to use for VM.
  template:
    description:
      - Template name to use for VM creation. Required if vm does not exist.
  vapp_name:
    description:
      - The name of the vCloud vApp instance. The vApp has to exist.
    required: true
  admin_password:
    description:
      - The root or administrator password if it should be set.
  interfaces:
    description:
      - "List of of network interfaces to create. Each interface is a dictionary."
    suboptions:
      primary:
        description:
          - True for primary interface
      network:
        description:
          - The network name to link the interface to
      addressing_type:
        description:
          - Interface ip allocation type
        choices: ['pool', 'dhcp', 'static']
      ip_address:
        description:
          - "for static addressing_type the ip that should be assigned"
  vm_cpus:
    description:
      - Number of CPUs
  vm_memory:
    description:
      - MBytes of memory for VM
  custom_script:
    description:
      - Customization script that should be executed when VM is created.
  state:
    description:
      - Configures the state of the vApp.
    default: present
    choices: ['present', 'absent', 'poweron', 'poweroff']
  metadata:
    description:
      - Dictionary of name and value entries that are added to the vm (as vcloud metadata type string)
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
     - name: VM1 add to Demo app
       vcd_vm:
         vcd_connection: "{{ vcd_connection_common }}"
         vm_name: myvm
         catalog: mycatalog
         template: centos7template
         vapp_name: demo_app
         vm_hostname: 'my-vm-host-name'
         admin_password: mypasswd
         interfaces:
           - primary: true
             network: my_main_org_net
             addressing_type: static
             ip_address: "{{ internal_vm_ip }}"
           - network: my_secondary_org_net
             addressing_type: pool
         vm_cpus: 2
         vm_memory: 1024
         custom_script: |
           echo 123
           touch /tmp/file1
           touch /tmp/file2
         metadata:
           mytag1: value123
           mytag2: xyz
'''

from ansible.module_utils.vcd_utils import VcdAnsibleModule, VcdError
import json

VM_STATUS = {
    'Powered off': 'poweroff',
    'Powered on': 'poweron',
    'Suspended': 'suspend',
    'Resolved': 'resolved'
}

VM_STATES = ['present', 'absent', 'poweron', 'poweroff']

VM_DIFF_PROPS = ['vm_memory',
                 'vm_cpus',
                 'metadata',
                 'vm_hostname',
                 'admin_password',
                 'interfaces',
                 'custom_script']


def get_instance(module):
    vapp_name = module.params['vapp_name']
    vm_name = module.params['vm_name']
    inst = dict(vapp_name=vapp_name,
                vapp_state='absent',
                vm_name=vm_name,
                vm_state='absent')
    try:
        vapp_dict = module.get_vapp_dict(vapp_name)
        module.debug("Vapp dict -- %s" % vapp_dict.__repr__())
        if not vapp_dict or VM_STATUS.get(vapp_dict['status'], 'unknown') is 'unknown':
            return inst
        else:
            inst['vapp_state'] = 'present'
    except VcdError:
        return inst

    try:
        vm_dict = module.get_vm_dict(vapp_name, vm_name)
        if vm_dict is not None:
            module.debug("VM dictionary %s" % json.dumps(vm_dict, indent=4))
            inst['vm_state'] = 'present'
            inst['vm_status'] = vm_dict['status']
            inst['vm_memory'] = str(vm_dict['memoryMB'])
            inst['vm_cpus'] = str(vm_dict['numberOfCpus'])
            inst['interfaces'] = vm_dict['interfaces']
            inst['custom_script'] = vm_dict['custom_script']
            inst['admin_password'] = vm_dict['admin_password']
            inst['metadata'] = vm_dict.get('metadata', [])
            inst['vm_hostname'] = vm_dict['hostname']
        return inst
    except VcdError:
        return inst


def create_vm(module):
    spec = get_vm_spec(module)

    vapp_name = module.params['vapp_name']
    vapp = module.get_vapp(vapp_name)
    task = vapp.add_vms([spec], all_eulas_accepted=True)
    module.wait_for_task(task)

    update_vm_cpu(module)
    update_vm_memory(module)
    update_vm_metadata(module)

    # TODO: Connect rest of interfaces


def change_vm(module, difference):
    needs_change = len(difference) > 0
    changed = False
    if module.check_mode:
        return True
    if needs_change:
        for diff in difference:
            if diff == 'vm_cpus':
                changed = changed | update_vm_cpu(module)
            elif diff == 'vm_memory':
                changed = changed | update_vm_memory(module)
            elif diff == 'metadata':
                changed = changed | update_vm_metadata(module)
    return changed


def delete_vm(module):
    if module.check_mode:
        pass
    vapp_name = module.params['vapp_name']
    vm_name = module.params['vm_name']
    if module.check_mode:
        module.log("Would delete vm %s" % vm_name)
        pass
    vapp = module.get_vapp(vapp_name)
    vm = module.get_vm(vapp_name, vm_name)
    task1 = vm.undeploy()
    module.wait_for_task(task1)
    task2 = vapp.delete_vms([vm_name])
    module.wait_for_task(task2)


def has_difference(param, actual_state, desired_state):
    return actual_state.get(param, '') != desired_state[param]


def update_vm_cpu(module):
    return update_vm_with(module, param='vm_cpus', function=module.vm_modify_cpu())


def update_vm_memory(module):
    return update_vm_with(module, param='vm_memory', function=module.vm_modify_memory())


def update_vm_metadata(module):
    if 'metadata' in module.params:
        vapp_name = module.params['vapp_name']
        vm_name = module.params['vm_name']
        vm = module.get_vm(vapp_name, vm_name)
        module.vm_set_metadata(vm=vm, metadata_dict=module.params['metadata'])
        return True
    else:
        return False


def update_vm_with(module, param, function):
    if param in module.params:
        vapp_name = module.params['vapp_name']
        vm_name = module.params['vm_name']
        vm = module.get_vm(vapp_name, vm_name)
        module.wait_for_task(vm.power_off())
        module.wait_for_task(function(vm, module.params[param]))
        vm.reload()
        module.wait_for_task(vm.power_on())
        return True
    else:
        return False


def get_vm_spec(module):
    vm_name = module.params['vm_name']
    spec = {
        'target_vm_name': vm_name,
        'hostname': module.params.get('vm_hostname', vm_name)
    }

    if 'custom_script' in module.params:
        spec['cust_script'] = module.params['custom_script']

    if 'admin_password' in module.params:
        spec['password'] = module.params['admin_password']

    if 'catalog' in module.params and 'template' in module.params:
        catalog_item = module.org.get_catalog_item(module.params['catalog'], module.params['template'])
        source_vapp_resource = module.client.get_resource(
            catalog_item.Entity.get('href'))
        spec['source_vm_name'] = module.params['template']
        spec['vapp'] = source_vapp_resource

    # for the moment, just connect up the first interface?
    if 'interfaces' in module.params:
        for interface in module.params['interfaces']:
            if module.boolean(interface.get('primary', 'false')):
                spec['network'] = interface['network']
                spec['ip_allocation_mode'] = interface['addressing_type']

    module.debug("Composed target vm spec: %s" % spec.__repr__())
    return spec


def main():
    interface_sub_spec = dict(
        primary=dict(default=False, type='bool'),
        network=dict(required=True, type='str'),
        addressing_type=dict(required=True, choices=['pool', 'static', 'dhcp']),
        ip_address=dict(type='str')
    )

    argument_spec = dict(
        vm_name=dict(required=True, type='str'),
        vm_hostname=dict(required=True, type='str'),
        admin_password=dict(required=False, no_log=True, type='str'),
        interfaces=dict(required=False, type='list', elements='dict', options=interface_sub_spec),
        vm_cpus=dict(required=False, type='str'),
        vm_memory=dict(required=False, type='str'),
        custom_script=dict(required=False, type='str'),
        metadata=dict(required=False, type='dict'),
        catalog=dict(required=False, type='str'),
        template=dict(required=False, type='str'),
        vapp_name=dict(required=True, type='str'),
        state=dict(default='present', choices=VM_STATES)
    )

    module = VcdAnsibleModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    desired_state = module.params['state']

    instance = get_instance(module)

    module.debug("Instance returned from get_instance %s" % instance)

    result = dict(changed=False, diff=list())

    result['diff'] = [diff_tag for diff_tag in VM_DIFF_PROPS if has_difference(param=diff_tag, actual_state=instance, desired_state=module.params)]

    module.debug("Diff %s" % result['diff'].__repr__())
    if instance is not None and desired_state == 'absent':
        if instance['vm_state'] != 'absent':
            delete_vm(module)
            result['changed'] = True

    elif desired_state != 'absent':
        if instance['vm_state'] == 'absent':
            create_vm(module)
            result['changed'] = True
        else:
            result['changed'] = change_vm(module, result['diff'])
    if result['changed'] != True:
        del result['diff']
    return module.exit(**result)


if __name__ == '__main__':
    main()

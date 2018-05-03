#!/usr/bin/python

# Copyright: (c) 2015, Ansible, Inc.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# copied and modified from vca_vapp.py

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: vcd_vapp
short_description: Manages vApp vCloud Director instances.
description:
  - This module will actively managed vCloud Director vApp instances.  Instances
    can be created and deleted as well as both deployed and undeployed.
version_added: "2.0"
author:
- Fabian Landis (@fabland)
options:
  vapp_name:
    description:
      - The name of the vCloud vApp instance
    required: yes
  state:
    description:
      - Configures the state of the vApp.
    default: present
    choices: ['present', 'absent', 'deployed', 'undeployed']
  tags:
    description:
      - Adds list of meta info tags as ansibleX - mytag to the vApp
  username:
    description:
      - The vCloud username to use during authentication
  password:
    description:
      - The vCloud password to use during authentication
  org:
    description:
      - The org to login to for creating vapp.
  host:
    description:
      - The authentication host to be used when service type  is vcd.
  api_version:
    description:
      - The api version to be used with the vca
    default: "29.0"
  vdc_name:
    description:
      - The name of the virtual data center (VDC) where the vm should be created or contains the vAPP.
  network_name:
      - Name of the network to connect the vapp to. Other networks can be created and added with the vcd_net module.
extends_documentation_fragment: vcd
'''

EXAMPLES = '''

- name: Creates a new vApp in a VCD instance
  vca_vapp:
    vapp_name: myVapp
    state: present
    vdc_name: VDC1
    username: '<your username here>'
    password: '<your password here>'
    network_name: my-net

'''

from ansible.module_utils.vcd_utils import VcdAnsibleModule, VcdError
import logging

VAPP_STATUS = {
    'Powered off': 'poweroff',
    'Powered on': 'poweron',
    'Suspended': 'suspend'
}

VAPP_STATES = ['present', 'absent', 'deployed', 'undeployed']

def get_instance(module):
    vapp_name = module.params['vapp_name']
    inst = dict(vapp_name=vapp_name, state='absent')
    try:
        vapp_dict = module.get_vapp_dict(vapp_name)
        if vapp_dict:
            status = vapp_dict['status']
            inst['status'] = VAPP_STATUS.get(status, 'unknown')
            inst['state'] = 'deployed' if status in ['Deployed', 'Powered on'] else 'undeployed'
        return inst
    except VcdError:
        return inst


def create(module):
    vapp_name = module.params['vapp_name']
    network_name = module.params['network_name']

    vapp_resource = module.vdc.create_vapp(
        name=vapp_name,
        description="Created by ansible",
        network=network_name
    )
    module.wait_for_task(vapp_resource.Tasks.Task[0])

    if module.params['tags'] is not None:
        vapp = module.get_vapp(vapp_name)
        for name, value in module.params['tags'].items():
            vapp.set_metadata(key=name, value=value)

def delete(module):
    vapp_name = module.params['vapp_name']
    module.vdc.delete_vapp(name=vapp_name, force=True)

def main():

    argument_spec = dict(
        vapp_name=dict(required=True),
        network_name=dict(required=True),
        vdc_name=dict(required=True),
        tags=dict(required=False, type='dict'),
        state=dict(default='present', choices=VAPP_STATES)
    )

    module = VcdAnsibleModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    state = module.params['state']

    instance = get_instance(module)

    result = dict(changed=False)

    if instance and state == 'absent':
        if not module.check_mode and instance['state'] != 'absent':
            delete(module)
            result['changed'] = True

    elif state != 'absent':
        if instance['state'] == 'absent':
            if not module.check_mode:
                create(module)
            result['changed'] = True

    return module.exit(**result)


if __name__ == '__main__':
    main()

#
# Copied and modified from ansible module_utils/vca.py
# Author: Fabian Landis (@fabland)

try:
    from pyvcloud.vcd.client import Client, TaskStatus
    from pyvcloud.vcd.client import VcdErrorResponseException
    from pyvcloud.vcd.client import BasicLoginCredentials
    from pyvcloud.vcd.client import EntityType
    from pyvcloud.vcd.org import Org
    from pyvcloud.vcd.vdc import VDC
    from pyvcloud.vcd.vapp import VApp
    from pyvcloud.vcd.utils import vapp_to_dict
    from pyvcloud.vcd.utils import to_dict
    import requests

    HAS_PYVCLOUD = True
except ImportError:
    HAS_PYVCLOUD = False

from ansible.module_utils.basic import AnsibleModule
from ansible.errors import AnsibleError
import logging
import json

DEFAULT_VERSION = '29.0'


class VcdError(Exception):

    def __init__(self, msg, **kwargs):
        self.kwargs = kwargs
        super(VcdError, self).__init__(msg)


def vcd_argument_spec():
    return dict(
        username=dict(type='str', aliases=['user'], required=True),
        password=dict(type='str', aliases=['pass', 'passwd'], required=True, no_log=True),
        org=dict(),
        service_id=dict(),
        instance_id=dict(),
        host=dict(),
        api_version=dict(default=DEFAULT_VERSION),
        vdc_name=dict(),
        gateway_name=dict(default='gateway'),
        verify_certs=dict(type='bool', default=True)
    )

class VcdAnsibleModule(AnsibleModule):

    def __init__(self, *args, **kwargs):
        argument_spec = vcd_argument_spec()
        argument_spec.update(kwargs.get('argument_spec', dict()))
        kwargs['argument_spec'] = argument_spec

        super(VcdAnsibleModule, self).__init__(*args, **kwargs)

        if not HAS_PYVCLOUD:
            self.fail("python module pyvcloud >= 19 is required for this module")
        
        self._client = self.create_client_instance()

        self._gateway = None
        self._vdc = None
        self._org = None

    @property
    def client(self):
        return self._client

    @property
    def org(self):
        if self._org is not None:
            return self._org
        org_name = self.params['org']
        org_resource = self.client.get_org()
        _org = Org(client=self.client, resource=org_resource)
        if not _org:
            raise VcdError('vcd instance has no org named %s' % org_name)
        self._org = _org
        return _org

    @property
    def vdc(self):
        if self._vdc is not None:
            return self._vdc
        vdc_name = self.params['vdc_name']
        vdc_resource = self.org.get_vdc(vdc_name)
        _vdc = VDC(client=self.client, resource=vdc_resource)
        if not _vdc:
            raise VcdError('vcd instance has no vdc named %s' % vdc_name)
        self._vdc = _vdc
        return _vdc

    def get_vapp(self, vapp_name):
        try:
            vapp_resource = self.vdc.get_vapp(vapp_name)
        except Exception:
            return None
        vapp = VApp(client=self.client, resource=vapp_resource)
        if not vapp:
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        return vapp

    def get_vapp_dict(self, vapp_name):
        try:
            vapp_resource = self.vdc.get_vapp(vapp_name)
        except Exception:
            return None
        vapp = VApp(client=self.client, resource=vapp_resource)
        if not vapp:
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        md = vapp.get_metadata()
        access_control_settings = vapp.get_access_settings()
        return vapp_to_dict(vapp_resource, md, access_control_settings)

    def get_vm(self, vapp_name, vm_name):
        vapp = self.get_vapp(vapp_name)
        vm = vapp.get_vm(vm_name=vm_name)
        if not vm:
            raise VcdError('vapp has no vm named %s' % vm_name)
        return vm

    def create_client_instance(self):
        host = self.params['host']
        version = self.params.get('api_version')
        verify = self.params.get('verify_certs')
        password = self.params['password']
        username = self.params['username']
        org = self.params['org']
        
        if not org:
            raise VcdError('missing required org for service_type vcd')

        if not verify:
            requests.packages.urllib3.disable_warnings()

        client = Client(host, verify_ssl_certs=verify, api_version=version,
                log_file='/tmp/ansible_pyvcloud.log', log_requests=True, log_bodies=True, log_headers=True)
        try:
            client.set_credentials(BasicLoginCredentials(user=username, org=org, password=password))
        except VcdErrorResponseException as e:
            raise VcdError('Login to VCD failed', msg=e.vcd_error)
        return client

    def logout(self):
        self._client.logout()

    # def save_services_config(self, blocking=True):
    #     task = self.gateway.save_services_configuration()
    #     if not task:
    #         self.fail(msg='unable to save gateway services configuration')
    #     if blocking:
    #         self.vca.block_until_completed(task)

    def wait_for_task(self, task):
        self.client.get_task_monitor().wait_for_success(
            task=task,
            timeout=60,
            poll_frequency=5)

    def fail(self, msg, **kwargs):
        self.fail_json(msg=msg, **kwargs)

    def exit(self, **kwargs):
        self.exit_json(**kwargs)

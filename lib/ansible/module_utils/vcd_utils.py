#
# Copied and modified from ansible module_utils/vca.py
# Author: Fabian Landis (@fabland)

try:
    from pyvcloud.vcd.client import Client
    from pyvcloud.vcd.client import TaskStatus
    from pyvcloud.vcd.client import NSMAP
    from pyvcloud.vcd.client import E
    from pyvcloud.vcd.client import VcdErrorResponseException
    from pyvcloud.vcd.client import BasicLoginCredentials
    from pyvcloud.vcd.client import EntityType
    from pyvcloud.vcd.org import Org
    from pyvcloud.vcd.vdc import VDC
    from pyvcloud.vcd.vapp import VApp
    from pyvcloud.vcd.vm import VM
    from pyvcloud.vcd.utils import vapp_to_dict
    from pyvcloud.vcd.utils import to_dict
    from pyvcloud.vcd.client import QueryResultFormat
    from lxml.objectify import NoneElement
    from pyvcloud.vcd.client import RelationType
    import lxml.objectify
    import requests

    HAS_PYVCLOUD = True
except ImportError:
    HAS_PYVCLOUD = False

from ansible.module_utils.basic import AnsibleModule

DEFAULT_VERSION = '29.0'


class VcdError(Exception):

    def __init__(self, msg, **kwargs):
        self.kwargs = kwargs
        super(VcdError, self).__init__(msg)


def vcd_sub_argument_spec():
    return dict(
        username=dict(type='str', aliases=['user'], required=True),
        password=dict(type='str', aliases=['pass', 'passwd'], no_log=True, required=True),
        org=dict(type='str', required=True),
        host=dict(type='str', required=True),
        api_version=dict(default=DEFAULT_VERSION),
        vdc_name=dict(type='str', required=True),
        verify_certs=dict(type='bool', default=True)
    )


def vcd_argument_spec():
    return dict(
        vcd_connection=dict(type='dict', required=True, options=vcd_sub_argument_spec()),
        gateway_name=dict(default='gateway')
    )


class VcdAnsibleModule(AnsibleModule):

    def __init__(self, *args, **kwargs):
        argument_spec = vcd_argument_spec()
        required_common_parameters = list(argument_spec.keys())
        argument_spec.update(kwargs.get('argument_spec', dict()))
        kwargs['argument_spec'] = argument_spec

        super(VcdAnsibleModule, self).__init__(*args, **kwargs)

        if not HAS_PYVCLOUD:
            self.fail("python module pyvcloud >= 19 is required for this module")

        self._common = self.params['vcd_connection']
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
        org_name = self._common['org']
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
        vdc_name = self._common['vdc_name']
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
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        vapp = VApp(client=self.client, resource=vapp_resource)
        if vapp is None:
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        return vapp

    def get_vapp_dict(self, vapp_name):
        try:
            vapp_resource = self.vdc.get_vapp(vapp_name)
        except Exception:
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        vapp = VApp(client=self.client, resource=vapp_resource)
        if vapp is None:
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        md = vapp.get_metadata()
        access_control_settings = vapp.get_access_settings()
        return vapp_to_dict(vapp_resource, md, access_control_settings)

    def get_vm(self, vapp_name, vm_name):
        vapp = self.get_vapp(vapp_name)
        vm = VM(client=self.client, resource=vapp.get_vm(vm_name=vm_name))
        if vm is None:
            raise VcdError('vapp has no vm named %s' % vm_name)
        return vm

    def get_vm_dict(self, vapp_name, vm_name):
        q = self.client.get_typed_query('vm', QueryResultFormat.ID_RECORDS, qfilter='containerName==' + vapp_name)
        vms = list(q.execute())
        for vm in vms:
            vm_dict = to_dict(vm)
            if vm_dict['name'] == vm_name:
                second_dict = self.vm_to_dict(vapp_name, vm_name)
                return dict(vm_dict, **second_dict)
        return None

    def create_client_instance(self):
        host = self._common['host']
        version = self._common['api_version']
        verify = self._common['verify_certs']
        password = self._common['password']
        username = self._common['username']
        org = self._common['org']

        if not org:
            raise VcdError('missing required org for service_type vcd')

        if not verify:
            requests.packages.urllib3.disable_warnings()
        if self._debug:
            self.debug('Logging vcloud calls to /tmp/ansible_pyvcloud.log')
            client = Client(host, verify_ssl_certs=verify, api_version=version,
                            log_file='/tmp/ansible_pyvcloud.log', log_requests=True, log_bodies=True, log_headers=True)
        else:
            client = Client(host, verify_ssl_certs=verify, api_version=version)
        try:
            client.set_credentials(BasicLoginCredentials(user=username, org=org, password=password))
        except VcdErrorResponseException as e:
            raise VcdError('Login to VCD failed', msg=e.vcd_error)
        return client

    def vm_modify_cpu(self):
        return VM.modify_cpu

    def vm_modify_memory(self):
        return VM.modify_memory

    def vm_to_dict(self, vapp_name, vm_name):
        try:
            vapp_resource = self.vdc.get_vapp(vapp_name)
        except Exception:
            raise VcdError('vcd instance has no vapp named %s' % vapp_name)
        vm = None
        if hasattr(vapp_resource, 'Children') and hasattr(vapp_resource.Children, 'Vm'):
            for vmx in vapp_resource.Children.Vm:
                if vmx.get('name') == vm_name:
                    vm = vmx

        result = {}
        result_interfaces = []
        items = vm.xpath(
            'ovf:VirtualHardwareSection/ovf:Item', namespaces=NSMAP)
        for item in items:
            element_name = item.find('rasd:ElementName', NSMAP)
            connection = item.find('rasd:Connection', NSMAP)
            if connection is not None:
                result_interfaces.append({
                    'network': connection.text,
                    'index': item.find('rasd:AddressOnParent', NSMAP).text,
                    'addressing_type': connection.get('{' + NSMAP['vcloud'] + '}ipAddressingMode'),
                    'ip_address': connection.get('{' + NSMAP['vcloud'] + '}ipAddress'),
                    'primary': connection.get('{' + NSMAP['vcloud'] + '}primaryNetworkConnection'),
                    'mac': item.find('rasd:Address', NSMAP).text
                })
        if hasattr(vm, 'GuestCustomizationSection'):
            if hasattr(vm.GuestCustomizationSection, 'AdminPassword'):
                result['admin_password'] = vm.GuestCustomizationSection.AdminPassword.text
            if hasattr(vm.GuestCustomizationSection, 'ComputerName'):
                result['hostname'] = vm.GuestCustomizationSection.ComputerName.text
            if hasattr(vm.GuestCustomizationSection, 'CustomizationScript'):
                result['custom_script'] = vm.GuestCustomizationSection.CustomizationScript.text
        result['interfaces'] = result_interfaces

        metadata = self.client.get_linked_resource(vm, RelationType.DOWN, EntityType.METADATA.value)
        # for vapp metadata -> copy over to vapp part
        if metadata is not None and hasattr(metadata, 'MetadataEntry'):
            metadata_dict = {}
            for me in metadata.MetadataEntry:
                metadata_dict[me.Key.text] = me.TypedValue.Value.text
            result['metadata'] = metadata_dict
        # logging.debug("Second result " + json.dumps(result, indent=4))
        return result

    def vm_set_metadata(self,
                        vm,
                        metadata_dict,
                        domain='GENERAL',
                        visibility='READWRITE',
                        metadata_type='MetadataStringValue'):
        vm_resource = self.client.get_resource(vm.href)
        for key, value in metadata_dict.items():
            new_metadata = E.Metadata(
                E.MetadataEntry(
                    {'type': 'xs:string'}, E.Domain(domain, visibility=visibility), E.Key(key),
                    E.TypedValue({'{' + NSMAP['xsi'] + '}type': 'MetadataStringValue'}, E.Value(value))))
            metadata = self.client.get_linked_resource(
                vm_resource, RelationType.DOWN, EntityType.METADATA.value)
            self.wait_for_task(self.client.post_linked_resource(metadata, RelationType.ADD,
                                                                EntityType.METADATA.value,
                                                                new_metadata))
            vm.reload()

    def logout(self):
        self._client.logout()

    def wait_for_task(self, task):
        self.client.get_task_monitor().wait_for_success(task=task)

    def fail(self, msg, **kwargs):
        self.fail_json(msg=msg, **kwargs)

    def exit(self, **kwargs):
        self.exit_json(**kwargs)

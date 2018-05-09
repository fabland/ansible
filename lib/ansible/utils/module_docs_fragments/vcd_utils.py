# (c) 2016, Charles Paul <cpaul@ansible.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


class ModuleDocFragment(object):
    # Parameters for VCD modules
    DOCUMENTATION = """
options:
    vcd_connection:
      description:
        - "Dictionary of common connection details needed to connect to vcloud with the following entries:"
        - "-  username: The vcd username. aliases: ['user']"
        - "-  password: The vcd password. aliases: ['pass', 'passwd']"
        - "-  org: The org to login to for creating vapp"
        - "-  host:The authentication host to be used."
        - "-  api_version: The api version to be used with the vcd. default: '29.0'" 
        - "-  verify_certs: If the certificates of the authentication is to be verified. default: 'yes'"
        - "-  vdc_name: The name of the vdc."
    gateway_name:
      description:
        - The name of the gateway of the vdc where the rule should be added.
      default: gateway
"""

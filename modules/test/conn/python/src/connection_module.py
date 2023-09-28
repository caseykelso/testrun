# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Connection test module"""
import util
import sys
import time
from datetime import datetime
from scapy.all import rdpcap, DHCP, Ether, IPv6, ICMPv6ND_NS
from test_module import TestModule
from dhcp1.client import Client as DHCPClient1
from dhcp2.client import Client as DHCPClient2
from dhcp_util import DHCPUtil

LOG_NAME = 'test_connection'
LOGGER = None
OUI_FILE = '/usr/local/etc/oui.txt'
STARTUP_CAPTURE_FILE = '/runtime/device/startup.pcap'
MONITOR_CAPTURE_FILE = '/runtime/device/monitor.pcap'
SLAAC_PREFIX = 'fd10:77be:4186'
TR_CONTAINER_MAC_PREFIX = '9a:02:57:1e:8f:'


class ConnectionModule(TestModule):
  """Connection Test module"""

  def __init__(self, module):
    super().__init__(module_name=module, log_name=LOG_NAME)
    global LOGGER
    LOGGER = self._get_logger()
    self.dhcp1_client = DHCPClient1()
    self.dhcp2_client = DHCPClient2()
    self._dhcp_util = DHCPUtil(self.dhcp1_client, self.dhcp2_client, LOGGER)

    # ToDo: Move this into some level of testing, leave for
    # reference until tests are implemented with these calls
    # response = self.dhcp1_client.add_reserved_lease(
    # 'test','00:11:22:33:44:55','10.10.10.21')
    # print("AddLeaseResp: " + str(response))

    # response = self.dhcp1_client.delete_reserved_lease('00:11:22:33:44:55')
    # print("DelLeaseResp: " + str(response))

    # response = self.dhcp1_client.disable_failover()
    # print("FailoverDisabled: " + str(response))

    # response = self.dhcp1_client.enable_failover()
    # print("FailoverEnabled: " + str(response))

    # response = self.dhcp1_client.get_dhcp_range()
    # print("DHCP Range: " + str(response))

    # response = self.dhcp1_client.get_lease(self._device_mac)
    # print("Lease: " + str(response))

    # response = self.dhcp1_client.get_status()
    # print("Status: " + str(response))

    # response = self.dhcp1_client.set_dhcp_range('10.10.10.20','10.10.10.30')
    # print("Set Range: " + str(response))

  def _connection_private_address(self, config):
    LOGGER.info('Running connection.private_address')
    return self._run_subnet_test(config)

  def _connection_shared_address(self, config):
    LOGGER.info('Running connection.shared_address')
    return self._run_subnet_test(config)

  def _connection_dhcp_address(self):
    LOGGER.info('Running connection.dhcp_address')
    response = self.dhcp1_client.get_lease(self._device_mac)
    LOGGER.info('DHCP Lease resolved:\n' + str(response))
    if response.code == 200:
      lease = eval(response.message)  # pylint: disable=W0123
      if 'ip' in lease:
        ip_addr = lease['ip']
        LOGGER.info('IP Resolved: ' + ip_addr)
        LOGGER.info('Attempting to ping device...')
        ping_success = self._ping(self._device_ipv4_addr)
        LOGGER.info('Ping Success: ' + str(ping_success))
        if ping_success:
          return True, 'Device responded to leased ip address'
        else:
          return False, 'Device did not respond to leased ip address'
    else:
      LOGGER.info('No DHCP lease found for: ' + self._device_mac)
      return False, 'No DHCP lease found for: ' + self._device_mac

  def _connection_mac_address(self):
    LOGGER.info('Running connection.mac_address')
    if self._device_mac is not None:
      LOGGER.info('MAC address found: ' + self._device_mac)
      return True, 'MAC address found: ' + self._device_mac
    else:
      LOGGER.info('No MAC address found: ' + self._device_mac)
      return False, 'No MAC address found.'

  def _connection_mac_oui(self):
    LOGGER.info('Running connection.mac_oui')
    manufacturer = self._get_oui_manufacturer(self._device_mac)
    if manufacturer is not None:
      LOGGER.info('OUI Manufacturer found: ' + manufacturer)
      return True, 'OUI Manufacturer found: ' + manufacturer
    else:
      LOGGER.info('No OUI Manufacturer found for: ' + self._device_mac)
      return False, 'No OUI Manufacturer found for: ' + self._device_mac

  def _connection_single_ip(self):
    LOGGER.info('Running connection.single_ip')

    result = None
    if self._device_mac is None:
      LOGGER.info('No MAC address found: ')
      return result, 'No MAC address found.'

    # Read all the pcap files containing DHCP packet information
    packets = rdpcap(STARTUP_CAPTURE_FILE)
    packets.append(rdpcap(MONITOR_CAPTURE_FILE))

    # Extract MAC addresses from DHCP packets
    mac_addresses = set()
    LOGGER.info('Inspecting: ' + str(len(packets)) + ' packets')
    for packet in packets:
      if DHCP in packet:
        for option in packet[DHCP].options:
          # message-type, option 3 = DHCPREQUEST
          if 'message-type' in option and option[1] == 3: 
            mac_address = packet[Ether].src
            LOGGER.info('DHCPREQUEST detected MAC addres: ' + mac_address)
            if not mac_address.startswith(TR_CONTAINER_MAC_PREFIX):
              mac_addresses.add(mac_address.upper())

    # Check if the device mac address is in the list of DHCPREQUESTs
    result = self._device_mac.upper() in mac_addresses
    LOGGER.info('DHCPREQUEST detected from device: ' + str(result))

    # Check the unique MAC addresses to see if they match the device
    for mac_address in mac_addresses:
      result &= self._device_mac.upper() == mac_address

    if result:
      return result, 'Device is using a single IP address'
    else:
      return result, 'Device is using multiple IP addresses'

  def _connection_target_ping(self):
    LOGGER.info('Running connection.target_ping')

    # If the ipv4 address wasn't resolved yet, try again
    if self._device_ipv4_addr is None:
      self._device_ipv4_addr = self._get_device_ipv4()

    if self._device_ipv4_addr is None:
      LOGGER.error('No device IP could be resolved')
      return False, 'Could not resolve device IP'
    else:
      if self._ping(self._device_ipv4_addr):
        return True, 'Device responds to ping'
      else:
        return False, 'Device does not respond to ping'

  def _connection_ipaddr_ip_change(self):
    result = None
    LOGGER.info('Running connection.ipaddr.ip_change')
    if self._dhcp_util.setup_single_dhcp_server():
      lease = self._dhcp_util.get_cur_lease(self._device_mac)
      if lease is not None:
        LOGGER.info('Current device lease resolved')
        LOGGER.debug(str(lease))
        # Figure out how to calculate a valid IP address
        ip_address = '10.10.10.30'
        if self._dhcp_util.add_reserved_lease(lease['hostname'],
                                              lease['hw_addr'], ip_address):
          self._dhcp_util.wait_for_lease_expire(lease)
          LOGGER.info('Checking device accepted new ip')
          for _ in range(5):
            LOGGER.info('Pinging device at IP: ' + ip_address)
            if self._ping(ip_address):
              LOGGER.debug('Ping success')
              LOGGER.info('Reserved lease confirmed active in device')
              result = True, 'Device has accepted an IP address change'
              LOGGER.debug('Restoring DHCP failover configuration')
              break
            else:
              LOGGER.info('Device did not respond to ping')
              result = False, 'Device did not accept IP address change'
              time.sleep(5)  # Wait 5 seconds before trying again
          self._dhcp_util.delete_reserved_lease(lease['hw_addr'])
        else:
          result = None, 'Failed to create reserved lease for device'
      else:
        result = None, 'Device has no current DHCP lease'
      # Restore the network
      self._dhcp_util.restore_failover_dhcp_server()
      LOGGER.info('Waiting 30 seconds for reserved lease to expire')
      time.sleep(30)
      self._dhcp_util.get_new_lease(self._device_mac)
    else:
      result = None, 'Failed to configure network for test'
    return result

  def _connection_ipaddr_dhcp_failover(self):
    result = None
    # Confirm that both servers are online
    primary_status = self._dhcp_util.get_dhcp_server_status(
        dhcp_server_primary=True)
    secondary_status = self._dhcp_util.get_dhcp_server_status(
        dhcp_server_primary=False)
    if primary_status and secondary_status:
      lease = self._dhcp_util.get_cur_lease(self._device_mac)
      if lease is not None:
        LOGGER.info('Current device lease resolved')
        LOGGER.debug(str(lease))
        if self._dhcp_util.is_lease_active(lease):
          # Shutdown the primary server
          if self._dhcp_util.stop_dhcp_server(dhcp_server_primary=True):
            # Wait until the current lease is expired
            self._dhcp_util.wait_for_lease_expire(lease)
            # Make sure the device has received a new lease from the
            # secondary server
            if self._dhcp_util.get_new_lease(self._device_mac,
                                             dhcp_server_primary=False):
              if self._dhcp_util.is_lease_active(lease):
                result = True, ('Secondary DHCP server lease confirmed active '
                 'in device')
              else:
                result = False, 'Could not validate lease is active in device'
            else:
              result = False, ('Device did not recieve a new lease from '
                'secondary DHCP server')
            self._dhcp_util.start_dhcp_server(dhcp_server_primary=True)
          else:
            result = None, 'Failed to shutdown primary DHCP server'
        else:
          result = False, 'Device did not respond to ping'
      else:
        result = None, 'Device has no current DHCP lease'
    else:
      LOGGER.error('Network is not ready for this test. Skipping')
      result = None, 'Network is not ready for this test'
    return result

  def _get_oui_manufacturer(self, mac_address):
    # Do some quick fixes on the format of the mac_address
    # to match the oui file pattern
    mac_address = mac_address.replace(':', '-').upper()
    with open(OUI_FILE, 'r', encoding='UTF-8') as file:
      for line in file:
        if mac_address.startswith(line[:8]):
          start = line.index('(hex)') + len('(hex)')
          return line[start:].strip()  # Extract the company name
    return None

  def _connection_ipv6_slaac(self):
    LOGGER.info('Running connection.ipv6_slaac')
    result = None
    packet_capture = rdpcap(MONITOR_CAPTURE_FILE)

    sends_ipv6 = False

    for packet in packet_capture:
      if IPv6 in packet and packet.src == self._device_mac:
        sends_ipv6 = True
        if ICMPv6ND_NS in packet:
          ipv6_addr = str(packet[ICMPv6ND_NS].tgt)
          if ipv6_addr.startswith(SLAAC_PREFIX):
            self._device_ipv6_addr = ipv6_addr
            LOGGER.info(f'Device has formed SLAAC address {ipv6_addr}')
            result = True, f'Device has formed SLAAC address {ipv6_addr}'
    if result is None:
      if sends_ipv6:
        LOGGER.info('Device does not support IPv6 SLAAC')
        result = False, 'Device does not support IPv6 SLAAC'
      else:
        LOGGER.info('Device does not support IPv6')
        result = False, 'Device does not support IPv6'
    return result

  def _connection_ipv6_ping(self):
    LOGGER.info('Running connection.ipv6_ping')
    result = None
    if self._device_ipv6_addr is None:
      LOGGER.info('No IPv6 SLAAC address found. Cannot ping')
      result = False, 'No IPv6 SLAAC address found. Cannot ping'
    else:
      if self._ping(self._device_ipv6_addr):
        LOGGER.info(f'Device responds to IPv6 ping on {self._device_ipv6_addr}')
        result = True, f'Device responds to IPv6 ping on {self._device_ipv6_addr}'
      else:
        LOGGER.info('Device does not respond to IPv6 ping')
        result = False, 'Device does not respond to IPv6 ping'
    return result

  def _ping(self, host):
    cmd = 'ping -c 1 ' + str(host)
    success = util.run_command(cmd, output=False)
    return success

  def restore_failover_dhcp_server(self, subnet):
    # Configure the subnet range
    if self._change_subnet(subnet):
      if self.enable_failover():
        response = self.dhcp2_client.start_dhcp_server()
        if response.code == 200:
          LOGGER.info('DHCP server configuration restored')
          return True
        else:
          LOGGER.error('Failed to start secondary DHCP server')
          return False
      else:
        LOGGER.error('Failed to enabled failover in primary DHCP server')
        return False
    else:
      LOGGER.error('Failed to restore original subnet')
      return False

  def setup_single_dhcp_server(self):
    # Shutdown the secondary DHCP Server
    LOGGER.info('Stopping secondary DHCP server')
    response = self.dhcp2_client.stop_dhcp_server()
    if response.code == 200:
      LOGGER.info('Secondary DHCP server stop command success')
      time.sleep(3)  # Give some time for the server to stop
      LOGGER.info('Checking secondary DHCP server status')
      response = self.dhcp2_client.get_status()
      if response.code == 200:
        LOGGER.info('Secondary DHCP server stopped')
        return True, 'Single DHCP server configured'
      else:
        return False, 'DHCP server still running'
    else:
      return False, 'DHCP server stop command failed'


    # TODO: This code is unreachable.
    # Move primary DHCP server from failover into a single DHCP server config
    LOGGER.info('Configuring primary DHCP server')
    response = self.dhcp1_client.disable_failover()
    if response.code == 200:
      LOGGER.info('Primary DHCP server failover disabled')
    else:
      return False, 'Failed to disable primary DHCP server failover'

  def enable_failover(self):
    # Move primary DHCP server to primary failover
    LOGGER.info('Configuring primary failover DHCP server')
    response = self.dhcp1_client.enable_failover()
    if response.code == 200:
      LOGGER.info('Primary DHCP server enabled')
      return True
    else:
      LOGGER.error('Failed to disable primary DHCP server failover')
      return False

  def is_ip_in_range(self, ip, start_ip, end_ip):
    ip_int = int(''.join(format(int(octet), '08b') for octet in ip.split('.')),
                 2)
    start_int = int(
        ''.join(format(int(octet), '08b') for octet in start_ip.split('.')), 2)
    end_int = int(
        ''.join(format(int(octet), '08b') for octet in end_ip.split('.')), 2)

    return start_int <= ip_int <= end_int

  def _run_subnet_test(self, config):
    # Resolve the configured dhcp subnet ranges
    ranges = None
    if 'ranges' in config:
      ranges = config['ranges']
    else:
      LOGGER.error('No subnet ranges configured for test. Skipping')
      return None, 'No subnet ranges configured for test'

    response = self.dhcp1_client.get_dhcp_range()
    cur_range = {}
    if response.code == 200:
      cur_range['start'] = response.start
      cur_range['end'] = response.end
      LOGGER.info('Current DHCP subnet range: ' + str(cur_range))
    else:
      LOGGER.error('Failed to resolve current subnet range required '
                   'for restoring network')
      return None, ('Failed to resolve current subnet range required '
                    'for restoring network')

    results = []
    dhcp_setup = self.setup_single_dhcp_server()
    if dhcp_setup[0]:
      LOGGER.info(dhcp_setup[1])
      lease = self._get_cur_lease()
      if lease is not None:
        if self._is_lease_active(lease):
          results = self.test_subnets(ranges)
      else:
        return None, 'Failed to confirm a valid active lease for the device'
    else:
      LOGGER.error(dhcp_setup[1])
      return None, 'Failed to setup DHCP server for test'

    # Process and return final results
    final_result = None
    final_result_details = ''
    for result in results:
      if final_result is None:
        final_result = result['result']
      else:
        final_result &= result['result']
        if result['result']:
          final_result_details += result['details'] + '\n'

    if final_result:
      final_result_details = 'All subnets are supported'

    try:
      # Restore failover configuration of DHCP servers
      self.restore_failover_dhcp_server(cur_range)

      # Wait for the current lease to expire
      self._wait_for_lease_expire(self._get_cur_lease())

      # Wait for a new lease to be provided before exiting test
      # to prevent other test modules from failing
      for _ in range(5):
        LOGGER.info('Checking for new lease')
        lease = self._get_cur_lease()
        if lease is not None:
          LOGGER.info('New lease found')
          LOGGER.debug(str(lease))
          LOGGER.info('Validating subnet for new lease...')
          in_range = self.is_ip_in_range(lease['ip'], cur_range['start'],
                                         cur_range['end'])
          LOGGER.debug('Lease within subnet: ' + str(in_range))
          break
        else:
          LOGGER.info('New lease not found. Waiting to check again')
        time.sleep(5)

    except Exception as e:  # pylint: disable=W0718
      LOGGER.error('Failed to restore DHCP server configuration: ' + str(e))

    return final_result, final_result_details

  def _test_subnet(self, subnet, lease):
    if self._change_subnet(subnet):
      expiration = datetime.strptime(lease['expires'], '%Y-%m-%d %H:%M:%S')
      time_to_expire = expiration - datetime.now()
      LOGGER.debug('Time until lease expiration: ' + str(time_to_expire))
      LOGGER.info('Waiting for current lease to expire: ' + str(expiration))
      if time_to_expire.total_seconds() > 0:
        time.sleep(time_to_expire.total_seconds() +
                   5)  # Wait until the expiration time and padd 5 seconds
        LOGGER.info('Current lease expired. Checking for new lease')
        for _ in range(5):
          LOGGER.info('Checking for new lease')
          lease = self._get_cur_lease()
          if lease is not None:
            LOGGER.info('New lease found: ' + str(lease))
            LOGGER.info('Validating subnet for new lease...')
            in_range = self.is_ip_in_range(lease['ip'], subnet['start'],
                                           subnet['end'])
            LOGGER.info('Lease within subnet: ' + str(in_range))
            return in_range
          else:
            LOGGER.info('New lease not found. Waiting to check again')
          time.sleep(5)
    else:
      LOGGER.error('Failed to change subnet')

  def _wait_for_lease_expire(self, lease):
    expiration = datetime.strptime(lease['expires'], '%Y-%m-%d %H:%M:%S')
    time_to_expire = expiration - datetime.now()
    LOGGER.info('Time until lease expiration: ' + str(time_to_expire))
    LOGGER.info('Waiting for current lease to expire: ' + str(expiration))
    if time_to_expire.total_seconds() > 0:
      time.sleep(time_to_expire.total_seconds() +
                 5)  # Wait until the expiration time and padd 5 seconds
      LOGGER.info('Current lease expired.')

  def _change_subnet(self, subnet):
    LOGGER.info('Changing subnet to: ' + str(subnet))
    response = self.dhcp1_client.set_dhcp_range(subnet['start'], subnet['end'])
    if response.code == 200:
      LOGGER.debug('Subnet change request accepted. Confirming change...')
      response = self.dhcp1_client.get_dhcp_range()
      if response.code == 200:
        if response.start == subnet['start'] and response.end == subnet['end']:
          LOGGER.debug('Subnet change confirmed')
          return True
      LOGGER.debug('Failed to confirm subnet change')
    else:
      LOGGER.debug('Subnet change request failed.')
    return False

  def _get_cur_lease(self):
    LOGGER.info('Checking current device lease')
    response = self.dhcp1_client.get_lease(self._device_mac)
    if response.code == 200:
      lease = eval(response.message)  # pylint: disable=W0123
      if lease:  # Check if non-empty lease
        return lease
    else:
      return None

  def _is_lease_active(self, lease):
    if 'ip' in lease:
      ip_addr = lease['ip']
      LOGGER.info('Lease IP Resolved: ' + ip_addr)
      LOGGER.info('Attempting to ping device...')
      ping_success = self._ping(self._device_ipv4_addr)
      LOGGER.info('Ping Success: ' + str(ping_success))
      LOGGER.info('Current lease confirmed active in device')
      return ping_success

  def test_subnets(self, subnets):
    results = []
    for subnet in subnets:
      result = {}
      try:
        lease = self._get_cur_lease()
        if lease is not None:
          result = self._test_subnet(subnet, lease)
          if result:
            result = {
                'result':
                True,
                'details':
                'Subnet ' + subnet['start'] + '-' + subnet['end'] + ' passed'
            }
          else:
            result = {
                'result':
                False,
                'details':
                'Subnet ' + subnet['start'] + '-' + subnet['end'] + ' failed'
            }
      except Exception as e:  # pylint: disable=W0718
        result = {'result': False, 'details': 'Subnet test failed: ' + str(e)}
      results.append(result)
    return results
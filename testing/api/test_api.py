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

"""Test assertions for CI network baseline test"""
# pylint: disable=redefined-outer-name

from collections.abc import Callable
import copy
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from typing import Iterator
import pytest
import requests

ALL_DEVICES = "*"
API = "http://127.0.0.1:8000"
LOG_PATH = "/tmp/testrun.log"
TEST_SITE_DIR = ".."

DEVICES_DIRECTORY = "local/devices"
TESTING_DEVICES = "../device_configs"
SYSTEM_CONFIG_PATH = "local/system.json"

BASELINE_MAC_ADDR = "02:42:aa:00:01:01"
ALL_MAC_ADDR = "02:42:aa:00:00:01"

def pretty_print(dictionary: dict):
  """ Pretty print dictionary """
  print(json.dumps(dictionary, indent=4))


def query_system_status() -> str:
  """Query system status from API and returns this"""
  r = requests.get(f"{API}/system/status", timeout=5)
  response = json.loads(r.text)
  return response["status"]


def query_test_count() -> int:
  """Queries status and returns number of test results"""
  r = requests.get(f"{API}/system/status", timeout=5)
  response = json.loads(r.text)
  return len(response["tests"]["results"])


def start_test_device(
    device_name, mac_address, image_name="test-run/ci_device_1", args=""
):
  """ Start test device container with given name """
  cmd = subprocess.run(
      f"docker run -d --network=endev0 --mac-address={mac_address}"
      f" --cap-add=NET_ADMIN -v /tmp:/out --privileged --name={device_name}"
      f" {image_name} {args}",
      shell=True,
      check=True,
      capture_output=True,
  )
  print(cmd.stdout)


def stop_test_device(device_name):
  """ Stop docker container with given name """
  cmd = subprocess.run(
      f"docker stop {device_name}", shell=True, capture_output=True,
      check=False
  )
  print(cmd.stdout)
  cmd = subprocess.run(
      f"docker rm {device_name}", shell=True, capture_output=True,
      check=False
  )
  print(cmd.stdout)


def docker_logs(device_name):
  """ Print docker logs from given docker container name """
  cmd = subprocess.run(
      f"docker logs {device_name}", shell=True, capture_output=True,
      check=False
  )
  print(cmd.stdout)


@pytest.fixture
def empty_devices_dir():
  """ Use e,pty devices directory """
  local_delete_devices(ALL_DEVICES)


@pytest.fixture
def testing_devices():
  """ Use devices from the testing/device_configs directory """
  local_delete_devices(ALL_DEVICES)
  shutil.copytree(
      os.path.join(os.path.dirname(__file__), TESTING_DEVICES),
      os.path.join(DEVICES_DIRECTORY),
      dirs_exist_ok=True,
  )
  return local_get_devices()


@pytest.fixture
def testrun(request): # pylint: disable=W0613
  """ Start intstance of testrun """
  with subprocess.Popen(
      "bin/testrun",
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      encoding="utf-8",
      preexec_fn=os.setsid
  ) as proc:

    while True:
      try:
        outs = proc.communicate(timeout=1)[0]
      except subprocess.TimeoutExpired as e:
        if e.output is not None:
          output = e.output.decode("utf-8")
          if re.search("API waiting for requests", output):
            break
      except Exception:
        pytest.fail("testrun terminated")

    time.sleep(2)

    yield

    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
      outs = proc.communicate(timeout=60)[0]
    except subprocess.TimeoutExpired as e:
      print(e.output)
      os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
      pytest.exit(
          "waited 60s but Testrun did not cleanly exit .. terminating all tests"
      )

  print(outs)

  cmd = subprocess.run(
      "docker stop $(docker ps -a -q)", shell=True,
      capture_output=True, check=False
  )
  print(cmd.stdout)
  cmd = subprocess.run(
      "docker rm  $(docker ps -a -q)", shell=True,
      capture_output=True, check=False
  )
  print(cmd.stdout)


def until_true(func: Callable, message: str, timeout: int):
  """ Blocks until given func returns True

  Raises:
    Exception if timeout has elapsed
  """
  expiry_time = time.time() + timeout
  while time.time() < expiry_time:
    if func():
      return True
    time.sleep(1)
  raise TimeoutError(f"Timed out waiting {timeout}s for {message}")


def dict_paths(thing: dict, stem: str = "") -> Iterator[str]:
  """Returns json paths (in dot notation) from a given dictionary"""
  for k, v in thing.items():
    path = f"{stem}.{k}" if stem else k
    if isinstance(v, dict):
      yield from dict_paths(v, path)
    else:
      yield path


def get_network_interfaces():
  """return list of network interfaces on machine

  uses /sys/class/net rather than inetfaces as test-run uses the latter
  """
  ifaces = []
  path = Path("/sys/class/net")
  for i in path.iterdir():
    if not i.is_dir():
      continue
    if i.stem.startswith("en") or i.stem.startswith("eth"):
      ifaces.append(i.stem)
  return ifaces


def local_delete_devices(path):
  """ Deletes all local devices 
  """
  for thing in Path(DEVICES_DIRECTORY).glob(path):
    if thing.is_file():
      thing.unlink()
    else:
      shutil.rmtree(thing)


def local_get_devices():
  """ Returns path to device configs of devices in local/devices directory"""
  return sorted(
      Path(DEVICES_DIRECTORY).glob(
          "*/device_config.json"
      )
  )


def test_get_system_interfaces(testrun): # pylint: disable=W0613
  """Tests API system interfaces against actual local interfaces"""
  r = requests.get(f"{API}/system/interfaces", timeout=5)
  response = json.loads(r.text)
  local_interfaces = get_network_interfaces()
  assert set(response.keys()) == set(local_interfaces)

  # schema expects a flat list
  assert all(isinstance(x, str) for x in response)


def test_status_idle(testrun): # pylint: disable=W0613
  until_true(
      lambda: query_system_status().lower() == "idle",
      "system status is `idle`",
      30,
  )

# Currently not working due to blocking during monitoring period
@pytest.mark.skip()
def test_status_in_progress(testing_devices, testrun):  # pylint: disable=W0613

  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload), timeout=10)
  assert r.status_code == 200

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", BASELINE_MAC_ADDR)

  until_true(
      lambda: query_system_status().lower() == "in progress",
      "system status is `in progress`",
      600,
  )


@pytest.mark.skip()
def test_status_non_compliant(testing_devices, testrun): # pylint: disable=W0613

  r = requests.get(f"{API}/devices", timeout=5)
  all_devices = json.loads(r.text)
  payload = {
    "device": {
      "mac_addr": all_devices[0]["mac_addr"],
      "firmware": "asd"
    }
  }
  r = requests.post(f"{API}/system/start", data=json.dumps(payload),
                    timeout=10)
  assert r.status_code == 200
  print(r.text)

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", all_devices[0]["mac_addr"])

  until_true(
      lambda: query_system_status().lower() == "non-compliant",
      "system status is `complete",
      600,
  )

  stop_test_device("x123")

def test_create_get_devices(empty_devices_dir, testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  r = requests.post(f"{API}/device", data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  device_2 = {
      "manufacturer": "Google",
      "model": "Second",
      "mac_addr": "00:1e:42:35:73:c6",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }
  r = requests.post(f"{API}/device", data=json.dumps(device_2),
                    timeout=5)
  assert r.status_code == 201
  assert len(local_get_devices()) == 2

  # Test that returned devices API endpoint matches expected structure
  r = requests.get(f"{API}/devices", timeout=5)
  all_devices = json.loads(r.text)
  pretty_print(all_devices)

  with open(
      os.path.join(os.path.dirname(__file__), "mockito/get_devices.json"),
      encoding="utf-8"
  ) as f:
    mockito = json.load(f)

  print(mockito)

  # Validate structure
  assert all(isinstance(x, dict) for x in all_devices)

  # TOOO uncomment when is done
  # assert set(dict_paths(mockito[0])) == set(dict_paths(all_devices[0]))

  # Validate contents of given keys matches
  for key in ["mac_addr", "manufacturer", "model"]:
    assert set([all_devices[0][key], all_devices[1][key]]) == set(
        [device_1[key], device_2[key]]
    )


def test_delete_device_success(empty_devices_dir, testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  # Send create device request
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)

  # Check device has been created
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  device_2 = {
      "manufacturer": "Google",
      "model": "Second",
      "mac_addr": "00:1e:42:35:73:c6",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_2),
                    timeout=5)
  assert r.status_code == 201
  assert len(local_get_devices()) == 2


  # Test that device_1 deletes
  r = requests.delete(f"{API}/device/",
                      data=json.dumps(device_1),
                      timeout=5)
  assert r.status_code == 200
  assert len(local_get_devices()) == 1


  # Test that returned devices API endpoint matches expected structure
  r = requests.get(f"{API}/devices", timeout=5)
  all_devices = json.loads(r.text)
  pretty_print(all_devices)

  with open(
      os.path.join(os.path.dirname(__file__),
                   "mockito/get_devices.json"),
                   encoding="utf-8"
  ) as f:
    mockito = json.load(f)

  print(mockito)

  # Validate structure
  assert all(isinstance(x, dict) for x in all_devices)

  # TOOO uncomment when is done
  # assert set(dict_paths(mockito[0])) == set(dict_paths(all_devices[0]))

  # Validate contents of given keys matches
  for key in ["mac_addr", "manufacturer", "model"]:
    assert set([all_devices[0][key]]) == set(
        [device_2[key]]
    )


def test_delete_device_not_found(empty_devices_dir, testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  # Send create device request
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)

  # Check device has been created
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  # Test that device_1 deletes
  r = requests.delete(f"{API}/device/",
                      data=json.dumps(device_1),
                      timeout=5)
  assert r.status_code == 200
  assert len(local_get_devices()) == 0

  # Test that device_1 is not found
  r = requests.delete(f"{API}/device/",
                      data=json.dumps(device_1),
                      timeout=5)
  assert r.status_code == 404
  assert len(local_get_devices()) == 0


def test_delete_device_no_mac(empty_devices_dir, testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  # Send create device request
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)

  # Check device has been created
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  device_1.pop("mac_addr")

  # Test that device_1 can't delete with no mac address
  r = requests.delete(f"{API}/device/",
                      data=json.dumps(device_1),
                      timeout=5)
  assert r.status_code == 400
  assert len(local_get_devices()) == 1


# Currently not working due to blocking during monitoring period
@pytest.mark.skip()
def test_delete_device_testrun_running(testing_devices, testrun): # pylint: disable=W0613

  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload), timeout=10)
  assert r.status_code == 200

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", BASELINE_MAC_ADDR)

  until_true(
      lambda: query_system_status().lower() == "in progress",
      "system status is `in progress`",
      600,
  )

  device_1 = {
        "manufacturer": "Google",
        "model": "First",
        "mac_addr": BASELINE_MAC_ADDR,
        "test_modules": {
            "dns": {"enabled": True},
            "connection": {"enabled": True},
            "ntp": {"enabled": True},
            "baseline": {"enabled": True},
            "nmap": {"enabled": True},
        },
    }
  r = requests.delete(f"{API}/device/",
                      data=json.dumps(device_1),
                      timeout=5)
  assert r.status_code == 403


def test_start_testrun_started_successfully(
    testing_devices, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload), timeout=10)
  assert r.status_code == 200


# Currently not working due to blocking during monitoring period
@pytest.mark.skip()
def test_start_testrun_already_in_progress(
  testing_devices, # pylint: disable=W0613
  testrun): # pylint: disable=W0613
  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload), timeout=10)

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", BASELINE_MAC_ADDR)

  until_true(
      lambda: query_system_status().lower() == "in progress",
      "system status is `in progress`",
      600,
  )
  r = requests.post(f"{API}/system/start", data=json.dumps(payload), timeout=10)
  assert r.status_code == 409

def test_start_system_not_configured_correctly(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  # Send create device request
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)

  payload = {"device": {"mac_addr": None, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start",
                    data=json.dumps(payload),
                    timeout=10)
  assert r.status_code == 500


def test_start_device_not_found(empty_devices_dir, # pylint: disable=W0613
                                testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  # Send create device request
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)

  r = requests.delete(f"{API}/device/",
                      data=json.dumps(device_1),
                      timeout=5)
  assert r.status_code == 200

  payload = {"device": {"mac_addr": device_1["mac_addr"], "firmware": "asd"}}
  r = requests.post(f"{API}/system/start",
                    data=json.dumps(payload),
                    timeout=10)
  assert r.status_code == 404


def test_start_missing_device_information(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  # Send create device request
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)

  payload = {}
  r = requests.post(f"{API}/system/start",
                    data=json.dumps(payload),
                    timeout=10)
  assert r.status_code == 400


def test_create_device_already_exists(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 409


def test_create_device_invalid_json(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
  }

  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 400


def test_create_device_invalid_request(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613

  r = requests.post(f"{API}/device",
                    data=None,
                    timeout=5)
  print(r.text)
  assert r.status_code == 400


def test_device_edit_device(
    testing_devices, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  with open(
      testing_devices[1], encoding="utf-8"
  ) as f:
    local_device = json.load(f)

  mac_addr = local_device["mac_addr"]
  new_model = "Alphabet"

  r = requests.get(f"{API}/devices", timeout=5)
  all_devices = json.loads(r.text)

  api_device = next(x for x in all_devices if x["mac_addr"] == mac_addr)

  updated_device = copy.deepcopy(api_device)
  updated_device["model"] = new_model

  new_test_modules = {
      k: {"enabled": not v["enabled"]}
      for k, v in updated_device["test_modules"].items()
  }
  updated_device["test_modules"] = new_test_modules

  updated_device_payload = {}
  updated_device_payload["device"] = updated_device
  updated_device_payload["mac_addr"] = mac_addr

  print("updated_device")
  pretty_print(updated_device)
  print("api_device")
  pretty_print(api_device)

  # update device
  r = requests.post(f"{API}/device/edit",
                    data=json.dumps(updated_device_payload),
                    timeout=5)

  assert r.status_code == 200

  r = requests.get(f"{API}/devices", timeout=5)
  all_devices = json.loads(r.text)
  updated_device_api = next(x for x in all_devices if x["mac_addr"] == mac_addr)

  assert updated_device_api["model"] == new_model
  assert updated_device_api["test_modules"] == new_test_modules


def test_device_edit_device_not_found(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  updated_device = copy.deepcopy(device_1)

  updated_device_payload = {}
  updated_device_payload["device"] = updated_device
  updated_device_payload["mac_addr"] = "00:1e:42:35:73:c6"
  updated_device_payload["model"] = "Alphabet"


  r = requests.post(f"{API}/device/edit",
                      data=json.dumps(updated_device_payload),
                      timeout=5)

  assert r.status_code == 404


def test_device_edit_device_incorrect_json_format(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  updated_device_payload = {}


  r = requests.post(f"{API}/device/edit",
                      data=json.dumps(updated_device_payload),
                      timeout=5)

  assert r.status_code == 400


def test_device_edit_device_with_mac_already_exists(
    empty_devices_dir, # pylint: disable=W0613
    testrun): # pylint: disable=W0613
  device_1 = {
      "manufacturer": "Google",
      "model": "First",
      "mac_addr": "00:1e:42:35:73:c4",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  r = requests.post(f"{API}/device",
                    data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  assert r.status_code == 201
  assert len(local_get_devices()) == 1

  device_2 = {
      "manufacturer": "Google",
      "model": "Second",
      "mac_addr": "00:1e:42:35:73:c6",
      "test_modules": {
          "dns": {"enabled": True},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }
  r = requests.post(f"{API}/device",
                    data=json.dumps(device_2),
                    timeout=5)
  assert r.status_code == 201
  assert len(local_get_devices()) == 2

  updated_device = copy.deepcopy(device_1)

  updated_device_payload = {}
  updated_device_payload = {}
  updated_device_payload["device"] = updated_device
  updated_device_payload["mac_addr"] = "00:1e:42:35:73:c6"
  updated_device_payload["model"] = "Alphabet"


  r = requests.post(f"{API}/device/edit",
                      data=json.dumps(updated_device_payload),
                      timeout=5)

  assert r.status_code == 409


def test_system_latest_version(testrun): # pylint: disable=W0613
  r = requests.get(f"{API}/system/version", timeout=5)
  assert r.status_code == 200
  updated_system_version = json.loads(r.text)["update_available"]
  assert updated_system_version is False

def test_get_system_config(testrun): # pylint: disable=W0613
  r = requests.get(f"{API}/system/config", timeout=5)

  with open(
    SYSTEM_CONFIG_PATH,
    encoding="utf-8"
  ) as f:
    local_config = json.load(f)

  api_config = json.loads(r.text)

  # validate structure
  assert set(dict_paths(api_config)) | set(dict_paths(local_config)) == set(
      dict_paths(api_config)
  )

  assert (
      local_config["network"]["device_intf"]
      == api_config["network"]["device_intf"]
  )
  assert (
      local_config["network"]["internet_intf"]
      == api_config["network"]["internet_intf"]
  )


def test_invalid_path_get(testrun): # pylint: disable=W0613
  r = requests.get(f"{API}/blah/blah", timeout=5)
  response = json.loads(r.text)
  assert r.status_code == 404
  with open(
      os.path.join(os.path.dirname(__file__), "mockito/invalid_request.json"),
      encoding="utf-8"
  ) as f:
    mockito = json.load(f)

  # validate structure
  assert set(dict_paths(mockito)) == set(dict_paths(response))


@pytest.mark.skip()
def test_trigger_run(testing_devices, testrun): # pylint: disable=W0613
  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload), timeout=10)
  assert r.status_code == 200

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", BASELINE_MAC_ADDR)

  until_true(
      lambda: query_system_status().lower() == "compliant",
      "system status is `complete`",
      600,
  )

  stop_test_device("x123")

  # Validate response
  r = requests.get(f"{API}/system/status", timeout=5)
  response = json.loads(r.text)
  pretty_print(response)

  # Validate results
  results = {x["name"]: x for x in response["tests"]["results"]}
  print(results)
  # there are only 3 baseline tests
  assert len(results) == 3

  # Validate structure
  with open(
      os.path.join(
          os.path.dirname(__file__), "mockito/running_system_status.json"
      ), encoding="utf-8"
  ) as f:
    mockito = json.load(f)

  # validate structure
  assert set(dict_paths(mockito)).issubset(set(dict_paths(response)))

  # Validate results structure
  assert set(dict_paths(mockito["tests"]["results"][0])).issubset(
      set(dict_paths(response["tests"]["results"][0]))
  )

  # Validate a result
  assert results["baseline.compliant"]["result"] == "Compliant"


@pytest.mark.skip()
def test_stop_running_test(testing_devices, testrun): # pylint: disable=W0613
  payload = {"device": {"mac_addr": ALL_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload),
                    timeout=10)
  assert r.status_code == 200

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x12345", ALL_MAC_ADDR)

  until_true(
      lambda: query_test_count() > 1,
      "system status is `complete`",
      1000,
  )

  stop_test_device("x12345")

  # Validate response
  r = requests.post(f"{API}/system/stop", timeout=5)
  response = json.loads(r.text)
  pretty_print(response)
  assert response == {"success": "Testrun stopped"}
  time.sleep(1)

  # Validate response
  r = requests.get(f"{API}/system/status", timeout=5)
  response = json.loads(r.text)
  pretty_print(response)

  assert response["status"] == "Cancelled"


def test_stop_running_not_running(testrun): # pylint: disable=W0613
  # Validate response
  r = requests.post(f"{API}/system/stop",
                    timeout=10)
  response = json.loads(r.text)
  pretty_print(response)

  assert r.status_code == 404
  assert response["error"] == "Testrun is not currently running"

@pytest.mark.skip()
def test_multiple_runs(testing_devices, testrun): # pylint: disable=W0613
  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload),
                    timeout=10)
  assert r.status_code == 200
  print(r.text)

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", BASELINE_MAC_ADDR)

  until_true(
      lambda: query_system_status().lower() == "compliant",
      "system status is `complete`",
      900,
  )

  stop_test_device("x123")

  # Validate response
  r = requests.get(f"{API}/system/status", timeout=5)
  response = json.loads(r.text)
  pretty_print(response)

  # Validate results
  results = {x["name"]: x for x in response["tests"]["results"]}
  print(results)
  # there are only 3 baseline tests
  assert len(results) == 3

  payload = {"device": {"mac_addr": BASELINE_MAC_ADDR, "firmware": "asd"}}
  r = requests.post(f"{API}/system/start", data=json.dumps(payload),
                    timeout=10)
  # assert r.status_code == 200
  # returns 409
  print(r.text)

  until_true(
      lambda: query_system_status().lower() == "waiting for device",
      "system status is `waiting for device`",
      30,
  )

  start_test_device("x123", BASELINE_MAC_ADDR)

  until_true(
      lambda: query_system_status().lower() == "compliant",
      "system status is `complete`",
      900,
  )

  stop_test_device("x123")


def test_create_invalid_chars(empty_devices_dir, testrun): # pylint: disable=W0613
  # local_delete_devices(ALL_DEVICES)
  # We must start test run with no devices in local/devices for this test
  # to function as expected
  assert len(local_get_devices()) == 0

  # Test adding device
  device_1 = {
      "manufacturer": "/'disallowed characters///",
      "model": "First",
      "mac_addr": BASELINE_MAC_ADDR,
      "test_modules": {
          "dns": {"enabled": False},
          "connection": {"enabled": True},
          "ntp": {"enabled": True},
          "baseline": {"enabled": True},
          "nmap": {"enabled": True},
      },
  }

  r = requests.post(f"{API}/device", data=json.dumps(device_1),
                    timeout=5)
  print(r.text)
  print(r.status_code)

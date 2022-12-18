from __future__ import annotations

import time
import unittest

from device_for_tests import TestableDeviceService, TestableDeviceProxy, MyDivZeroError
from hdcproto.exception import HdcCmdException
from hdcproto.host.proxy import DeviceProxyBase
from hdcproto.transport.tunnel import TunnelTransport

TRANSPORT_URL = "socket://localhost:55555"


class TestBasicScenario(unittest.TestCase):

    def test_hardcoded_proxy(self):
        with TestableDeviceService(transport=TRANSPORT_URL) as device_service:
            with TestableDeviceProxy(transport=TRANSPORT_URL) as device_proxy:
                result = device_proxy.core.prop_device_name.get()
                self.assertEqual(result, device_service.device_name)

                device_proxy.core.prop_heartbeat_counter.set(new_value=1234)
                result = device_proxy.core.prop_heartbeat_counter.get()
                self.assertEqual(result, 1234)

                device_service.core.evt_heartbeat.emit(counter=42)
                time.sleep(0.2)
                evt = device_proxy.core.evt_heartbeat.most_recently_received_event_payloads.popleft()
                self.assertEqual(evt, 42)

                result = device_proxy.core.cmd_division(numerator=10.0, denominator=2.0)
                self.assertEqual(result, 5.0)

                with self.assertRaises(MyDivZeroError):
                    device_proxy.core.cmd_division(numerator=10.0, denominator=0.0)

    # noinspection PyUnresolvedReferences
    def test_dynamic_proxy(self):
        with TestableDeviceService(transport=TRANSPORT_URL) as device_service:
            dynamic_proxy = DeviceProxyBase.connect_and_build(transport=TRANSPORT_URL)
            self.assertTrue(hasattr(dynamic_proxy, "core"))
            self.assertTrue(hasattr(dynamic_proxy.core, "prop_device_name"))
            self.assertTrue(hasattr(dynamic_proxy.core, "prop_heartbeat_counter"))
            self.assertTrue(hasattr(dynamic_proxy.core, "evt_heartbeat"))
            self.assertTrue(hasattr(dynamic_proxy.core, "cmd_division"))

            result = dynamic_proxy.core.prop_device_name.get()
            self.assertEqual(result, device_service.device_name)

            dynamic_proxy.core.prop_heartbeat_counter.set(new_value=1234)
            result = dynamic_proxy.core.prop_heartbeat_counter.get()
            self.assertEqual(result, 1234)

            device_service.core.evt_heartbeat.emit(counter=42)
            time.sleep(0.2)
            evt = dynamic_proxy.core.evt_heartbeat.most_recently_received_event_payloads.popleft()
            self.assertEqual(evt, 42)

            result = dynamic_proxy.core.cmd_division(numerator=10.0, denominator=2.0)
            self.assertEqual(result, 5.0)

            # Can deal with unknown custom exception
            with self.assertRaises(HdcCmdException):
                dynamic_proxy.core.cmd_division(numerator=10.0, denominator=0.0)

            # Can deal with dynamically registered custom exception
            custom_exception = MyDivZeroError()  # Exception objects also serve as descriptors
            dynamic_proxy.core.cmd_division. \
                command_descriptor.raises[custom_exception.exception_id] = custom_exception
            with self.assertRaises(MyDivZeroError):
                dynamic_proxy.core.cmd_division(numerator=10.0, denominator=0.0)

            dynamic_proxy.close()


TUNNEL_ID = 0x42


class TestTunneling(unittest.TestCase):

    def test_hardcoded_proxy_through_tunnel(self):
        with TestableDeviceService(transport=TRANSPORT_URL) as device_service:
            with TestableDeviceService().connect_as_subdevice_of(parent_device=device_service,
                                                                 tunnel_id=TUNNEL_ID) as subdevice_service:
                self.assertTrue(TUNNEL_ID in device_service.device_descriptor.tunnels.keys())

                with TestableDeviceProxy(transport=TRANSPORT_URL) as device_proxy:
                    with TestableDeviceProxy(
                            transport=TunnelTransport(tunnel_id=TUNNEL_ID,
                                                      tunnel_through_router=device_proxy.router)) as subdevice_proxy:
                        result = subdevice_proxy.core.prop_device_name.get()
                        self.assertEqual(result, subdevice_service.device_name)

                        subdevice_proxy.core.prop_heartbeat_counter.set(new_value=1234)
                        result = subdevice_proxy.core.prop_heartbeat_counter.get()
                        self.assertEqual(result, 1234)

                        subdevice_service.core.evt_heartbeat.emit(counter=42)
                        time.sleep(0.2)
                        evt = subdevice_proxy.core.evt_heartbeat.most_recently_received_event_payloads.popleft()
                        self.assertEqual(evt, 42)

                        result = subdevice_proxy.core.cmd_division(numerator=10.0, denominator=2.0)
                        self.assertEqual(result, 5.0)

                        with self.assertRaises(MyDivZeroError):
                            subdevice_proxy.core.cmd_division(numerator=10.0, denominator=0.0)

    # noinspection PyUnresolvedReferences
    def test_dynamic_proxy_through_tunnel(self):
        with TestableDeviceService(transport=TRANSPORT_URL) as device_service:
            with TestableDeviceService().connect_as_subdevice_of(parent_device=device_service,
                                                                 tunnel_id=TUNNEL_ID) as subdevice_service:
                self.assertTrue(TUNNEL_ID in device_service.device_descriptor.tunnels.keys())

                device_proxy = DeviceProxyBase.connect_and_build(transport=TRANSPORT_URL)
                self.assertTrue(hasattr(device_proxy, "core"))
                self.assertTrue(hasattr(device_proxy.core, "prop_device_name"))
                self.assertTrue(hasattr(device_proxy.core, "prop_heartbeat_counter"))
                self.assertTrue(hasattr(device_proxy.core, "evt_heartbeat"))
                self.assertTrue(hasattr(device_proxy.core, "cmd_division"))

                # Note how also a proxy for the subdevice was dynamically generated
                self.assertTrue(hasattr(device_proxy, "subdevice_testable_device"))
                subdevice_proxy = device_proxy.subdevice_testable_device  # Just for readability
                self.assertTrue(hasattr(subdevice_proxy, "core"))
                self.assertTrue(hasattr(subdevice_proxy.core, "prop_device_name"))
                self.assertTrue(hasattr(subdevice_proxy.core, "prop_heartbeat_counter"))
                self.assertTrue(hasattr(subdevice_proxy.core, "evt_heartbeat"))
                self.assertTrue(hasattr(subdevice_proxy.core, "cmd_division"))

                result = subdevice_proxy.core.prop_device_name.get()
                self.assertEqual(result, subdevice_service.device_name)

                subdevice_proxy.core.prop_heartbeat_counter.set(new_value=1234)
                result = subdevice_proxy.core.prop_heartbeat_counter.get()
                self.assertEqual(result, 1234)

                subdevice_service.core.evt_heartbeat.emit(counter=42)
                time.sleep(0.2)
                evt = subdevice_proxy.core.evt_heartbeat.most_recently_received_event_payloads.popleft()
                self.assertEqual(evt, 42)

                result = subdevice_proxy.core.cmd_division(numerator=10.0, denominator=2.0)
                self.assertEqual(result, 5.0)

                # Can deal with unknown custom exception
                with self.assertRaises(HdcCmdException):
                    subdevice_proxy.core.cmd_division(numerator=10.0, denominator=0.0)

                # Can deal with dynamically registered custom exception
                custom_exception = MyDivZeroError()  # Exception objects also serve as descriptors
                subdevice_proxy.core.cmd_division. \
                    command_descriptor.raises[custom_exception.exception_id] = custom_exception
                with self.assertRaises(MyDivZeroError):
                    subdevice_proxy.core.cmd_division(numerator=10.0, denominator=0.0)

                subdevice_proxy.close()
                device_proxy.close()

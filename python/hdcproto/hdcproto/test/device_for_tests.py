from __future__ import annotations

from hdcproto.descriptor import CommandDescriptor, EventDescriptor, PropertyDescriptor, ArgD, RetD, FeatureDescriptor
from hdcproto.device.service import (DeviceService, CoreFeatureService, CommandService, EventService,
                                     PropertyService)
from hdcproto.exception import HdcCmdException
from hdcproto.host.proxy import FeatureProxyBase, DeviceProxyBase, PropertyProxy_RO_UTF8, EventProxyBase, \
    PropertyProxy_RW_UINT32, CommandProxyBase
from hdcproto.spec import DTypeID, FeatureID
from hdcproto.transport.base import TransportBase


class MyDivZeroError(HdcCmdException):
    def __init__(self,
                 exception_message: str | None = None):
        super().__init__(id=0x01,
                         name="MyDivZero",
                         exception_message=exception_message)


division_cmd_descriptor = CommandDescriptor(
    id=0x01,
    name="division",
    args=[ArgD(DTypeID.FLOAT, "numerator"),
          ArgD(DTypeID.FLOAT, "denominator", "Beware of the zero!")],
    returns=RetD(DTypeID.DOUBLE, doc="Quotient of numerator/denominator"),  # May omit name
    raises=[MyDivZeroError()],
    doc="Divides numerator by denominator.")

heartbeat_event_descriptor = EventDescriptor(
    id=0x01,
    name="heartbeat",
    args=[ArgD(DTypeID.UINT32, 'counter')],
    doc="")

device_name_prop_descriptor = PropertyDescriptor(
    id=0x01,
    name="device_name",
    dtype=DTypeID.UTF8,
    is_readonly=True,
    doc="Name of this device.")

heartbeat_counter_prop_descriptor = PropertyDescriptor(
    id=0x02,
    name="heartbeat_counter",
    dtype=DTypeID.UINT32,
    is_readonly=False,
    doc="Incremented on every heartbeat.")


class TestableCoreService(CoreFeatureService):
    def __init__(self, device_service: DeviceService):
        super().__init__(device_service=device_service)

        self.heartbeat_counter = 0

        # Commands
        self.cmd_division = CommandService(
            command_descriptor=division_cmd_descriptor,
            feature_service=self,
            command_implementation=self.division,
        )

        # Events
        self.evt_heartbeat = EventService(
            event_descriptor=heartbeat_event_descriptor,
            feature_service=self)

        #############
        # Properties
        self.prop_device_name = PropertyService(
            property_descriptor=device_name_prop_descriptor,
            feature_service=self,
            property_getter=lambda: self.device_service.device_name,
            property_setter=None
        )

        def heartbeat_counter_setter(new_value: int) -> int:
            self.heartbeat_counter = new_value
            return self.heartbeat_counter

        self.prop_heartbeat_counter = PropertyService(
            property_descriptor=heartbeat_counter_prop_descriptor,
            feature_service=self,
            property_getter=lambda: self.heartbeat_counter,
            property_setter=heartbeat_counter_setter
        )

    def division(self, numerator: float, denominator: float) -> float:
        """Actual implementation of the HDC-command"""
        if denominator == 0:
            raise MyDivZeroError()
        self.hdc_logger.debug(f"Dividing {numerator} by {denominator}.")
        return numerator / denominator


class TestableDeviceService(DeviceService):
    def __init__(self, transport: TransportBase | str | None = None):
        super().__init__(device_name="testable_device",
                         device_version="0.0.1",  # Mocking a SemVer for this implementation
                         device_doc="Python implementation of the 'Minimal' HDC-device demonstration",
                         max_req=128,
                         transport=transport)

        self.core = TestableCoreService(self)


class TestableCoreProxy(FeatureProxyBase):

    def __init__(self, device_proxy: DeviceProxyBase):
        super().__init__(
            feature_descriptor=FeatureDescriptor(
                id=FeatureID.CORE,
                name="core",
                cls="DontCare",  # ToDo: Attribute optionality. #25
            ),
            device_proxy=device_proxy)

        ###########
        # Commands
        self.cmd_division = CommandProxyBase(
            command_descriptor=division_cmd_descriptor,
            feature_proxy=self)

        #########
        # Events
        self.evt_heartbeat = EventProxyBase(
            event_descriptor=heartbeat_event_descriptor,
            feature_proxy=self)

        # Properties
        self.prop_device_name = PropertyProxy_RO_UTF8(
            property_descriptor=device_name_prop_descriptor,
            feature_proxy=self)

        self.prop_heartbeat_counter = PropertyProxy_RW_UINT32(
            property_descriptor=heartbeat_counter_prop_descriptor,
            feature_proxy=self)


class TestableDeviceProxy(DeviceProxyBase):
    core: TestableCoreProxy

    def __init__(self, transport: TransportBase | str | None = None):
        super().__init__(transport=transport)
        self.core = TestableCoreProxy(self)

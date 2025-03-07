# Copyright (c) 2023-2025 Arista Networks, Inc.
# Use of this source code is governed by the Apache License 2.0
# that can be found in the LICENSE file.
"""Module related to the device interfaces tests."""

# Mypy does not understand AntaTest.Input typing
# mypy: disable-error-code=attr-defined
from __future__ import annotations

import re
from typing import ClassVar, TypeVar

from pydantic import BaseModel, Field, field_validator
from pydantic_extra_types.mac_address import MacAddress

from anta.custom_types import EthernetInterface, Interface, Percent, PositiveInteger
from anta.decorators import skip_on_platforms
from anta.input_models.interfaces import InterfaceDetail, InterfaceState
from anta.models import AntaCommand, AntaTemplate, AntaTest
from anta.tools import custom_division, format_data, get_failed_logs, get_item, get_value

BPS_GBPS_CONVERSIONS = 1000000000

# Using a TypeVar for the InterfaceState model since mypy thinks it's a ClassVar and not a valid type when used in field validators
T = TypeVar("T", bound=InterfaceState)


class VerifyInterfaceUtilization(AntaTest):
    """Verifies that the utilization of interfaces is below a certain threshold.

    Load interval (default to 5 minutes) is defined in device configuration.
    This test has been implemented for full-duplex interfaces only.

    Expected Results
    ----------------
    * Success: The test will pass if all interfaces have a usage below the threshold.
    * Failure: The test will fail if one or more interfaces have a usage above the threshold.
    * Error: The test will error out if the device has at least one non full-duplex interface.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfaceUtilization:
          threshold: 70.0
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [
        AntaCommand(command="show interfaces counters rates", revision=1),
        AntaCommand(command="show interfaces", revision=1),
    ]

    class Input(AntaTest.Input):
        """Input model for the VerifyInterfaceUtilization test."""

        threshold: Percent = 75.0
        """Interface utilization threshold above which the test will fail. Defaults to 75%."""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfaceUtilization."""
        self.result.is_success()
        duplex_full = "duplexFull"
        rates = self.instance_commands[0].json_output
        interfaces = self.instance_commands[1].json_output

        for intf, rate in rates["interfaces"].items():
            # The utilization logic has been implemented for full-duplex interfaces only
            if ((duplex := (interface := interfaces["interfaces"][intf]).get("duplex", None)) is not None and duplex != duplex_full) or (
                (members := interface.get("memberInterfaces", None)) is not None and any(stats["duplex"] != duplex_full for stats in members.values())
            ):
                self.result.is_failure(f"Interface {intf} or one of its member interfaces is not Full-Duplex. VerifyInterfaceUtilization has not been implemented.")
                return

            if (bandwidth := interfaces["interfaces"][intf]["bandwidth"]) == 0:
                self.logger.debug("Interface %s has been ignored due to null bandwidth value", intf)
                continue

            # If one or more interfaces have a usage above the threshold, test fails.
            for bps_rate in ("inBpsRate", "outBpsRate"):
                usage = rate[bps_rate] / bandwidth * 100
                if usage > self.inputs.threshold:
                    self.result.is_failure(
                        f"Interface: {intf} BPS Rate: {bps_rate} - Usage exceeds the threshold - Expected: < {self.inputs.threshold}% Actual: {usage}%"
                    )


class VerifyInterfaceErrors(AntaTest):
    """Verifies that the interfaces error counters are equal to zero.

    Expected Results
    ----------------
    * Success: The test will pass if all interfaces have error counters equal to zero.
    * Failure: The test will fail if one or more interfaces have non-zero error counters.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfaceErrors:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces counters errors", revision=1)]

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfaceErrors."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        for interface, counters in command_output["interfaceErrorCounters"].items():
            counters_data = [f"{counter}: {value}" for counter, value in counters.items() if value > 0]
            if counters_data:
                self.result.is_failure(f"Interface: {interface} - Non-zero error counter(s) - {', '.join(counters_data)}")


class VerifyInterfaceDiscards(AntaTest):
    """Verifies that the interfaces packet discard counters are equal to zero.

    Expected Results
    ----------------
    * Success: The test will pass if all interfaces have discard counters equal to zero.
    * Failure: The test will fail if one or more interfaces have non-zero discard counters.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfaceDiscards:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces counters discards", revision=1)]

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfaceDiscards."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        for interface, interface_data in command_output["interfaces"].items():
            counters_data = [f"{counter}: {value}" for counter, value in interface_data.items() if value > 0]
            if counters_data:
                self.result.is_failure(f"Interface: {interface} - Non-zero discard counter(s): {', '.join(counters_data)}")


class VerifyInterfaceErrDisabled(AntaTest):
    """Verifies there are no interfaces in the errdisabled state.

    Expected Results
    ----------------
    * Success: The test will pass if there are no interfaces in the errdisabled state.
    * Failure: The test will fail if there is at least one interface in the errdisabled state.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfaceErrDisabled:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces status", revision=1)]

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfaceErrDisabled."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        for interface, value in command_output["interfaceStatuses"].items():
            if value["linkStatus"] == "errdisabled":
                self.result.is_failure(f"Interface: {interface} - Link status Error disabled")


class VerifyInterfacesStatus(AntaTest):
    """Verifies the operational states of specified interfaces to ensure they match expected configurations.

    This test performs the following checks for each specified interface:

      1. If `line_protocol_status` is defined, both `status` and `line_protocol_status` are verified for the specified interface.
      2. If `line_protocol_status` is not provided but the `status` is "up", it is assumed that both the status and line protocol should be "up".
      3. If the interface `status` is not "up", only the interface's status is validated, with no line protocol check performed.

    Expected Results
    ----------------
    * Success: If the interface status and line protocol status matches the expected operational state for all specified interfaces.
    * Failure: If any of the following occur:
        - The specified interface is not configured.
        - The specified interface status and line protocol status does not match the expected operational state for any interface.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfacesStatus:
          interfaces:
            - name: Ethernet1
              status: up
            - name: Port-Channel100
              status: down
              line_protocol_status: lowerLayerDown
            - name: Ethernet49/1
              status: adminDown
              line_protocol_status: notPresent
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces description", revision=1)]

    class Input(AntaTest.Input):
        """Input model for the VerifyInterfacesStatus test."""

        interfaces: list[InterfaceState]
        """List of interfaces with their expected state."""
        InterfaceState: ClassVar[type[InterfaceState]] = InterfaceState

        @field_validator("interfaces")
        @classmethod
        def validate_interfaces(cls, interfaces: list[T]) -> list[T]:
            """Validate that 'status' field is provided in each interface."""
            for interface in interfaces:
                if interface.status is None:
                    msg = f"{interface} 'status' field missing in the input"
                    raise ValueError(msg)
            return interfaces

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfacesStatus."""
        self.result.is_success()

        command_output = self.instance_commands[0].json_output
        for interface in self.inputs.interfaces:
            if (intf_status := get_value(command_output["interfaceDescriptions"], interface.name, separator="..")) is None:
                self.result.is_failure(f"{interface.name} - Not configured")
                continue

            status = "up" if intf_status["interfaceStatus"] in {"up", "connected"} else intf_status["interfaceStatus"]
            proto = "up" if intf_status["lineProtocolStatus"] in {"up", "connected"} else intf_status["lineProtocolStatus"]

            # If line protocol status is provided, prioritize checking against both status and line protocol status
            if interface.line_protocol_status:
                if any([interface.status != status, interface.line_protocol_status != proto]):
                    actual_state = f"Expected: {interface.status}/{interface.line_protocol_status}, Actual: {status}/{proto}"
                    self.result.is_failure(f"{interface.name} - Status mismatch - {actual_state}")

            # If line protocol status is not provided and interface status is "up", expect both status and proto to be "up"
            # If interface status is not "up", check only the interface status without considering line protocol status
            elif all([interface.status == "up", status != "up" or proto != "up"]):
                self.result.is_failure(f"{interface.name} - Status mismatch - Expected: up/up, Actual: {status}/{proto}")
            elif interface.status != status:
                self.result.is_failure(f"{interface.name} - Status mismatch - Expected: {interface.status}, Actual: {status}")


class VerifyStormControlDrops(AntaTest):
    """Verifies there are no interface storm-control drop counters.

    Expected Results
    ----------------
    * Success: The test will pass if there are no storm-control drop counters.
    * Failure: The test will fail if there is at least one storm-control drop counter.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyStormControlDrops:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show storm-control", revision=1)]

    @skip_on_platforms(["cEOSLab", "vEOS-lab", "cEOSCloudLab"])
    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyStormControlDrops."""
        command_output = self.instance_commands[0].json_output
        storm_controlled_interfaces = []
        self.result.is_success()

        for interface, interface_dict in command_output["interfaces"].items():
            for traffic_type, traffic_type_dict in interface_dict["trafficTypes"].items():
                if "drop" in traffic_type_dict and traffic_type_dict["drop"] != 0:
                    storm_controlled_interfaces.append(f"{traffic_type}: {traffic_type_dict['drop']}")
            if storm_controlled_interfaces:
                self.result.is_failure(f"Interface: {interface} - Non-zero storm-control drop counter(s) - {', '.join(storm_controlled_interfaces)}")


class VerifyPortChannels(AntaTest):
    """Verifies there are no inactive ports in all port channels.

    Expected Results
    ----------------
    * Success: The test will pass if there are no inactive ports in all port channels.
    * Failure: The test will fail if there is at least one inactive port in a port channel.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyPortChannels:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show port-channel", revision=1)]

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyPortChannels."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        for port_channel, port_channel_details in command_output["portChannels"].items():
            # Verify that the no inactive ports in all port channels.
            if inactive_ports := port_channel_details["inactivePorts"]:
                self.result.is_failure(f"{port_channel} - Inactive port(s) - {', '.join(inactive_ports.keys())}")


class VerifyIllegalLACP(AntaTest):
    """Verifies there are no illegal LACP packets in all port channels.

    Expected Results
    ----------------
    * Success: The test will pass if there are no illegal LACP packets received.
    * Failure: The test will fail if there is at least one illegal LACP packet received.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyIllegalLACP:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show lacp counters all-ports", revision=1)]

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyIllegalLACP."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        for port_channel, port_channel_dict in command_output["portChannels"].items():
            for interface, interface_details in port_channel_dict["interfaces"].items():
                # Verify that the no illegal LACP packets in all port channels.
                if interface_details["illegalRxCount"] != 0:
                    self.result.is_failure(f"{port_channel} Interface: {interface} - Illegal LACP packets found")


class VerifyLoopbackCount(AntaTest):
    """Verifies that the device has the expected number of loopback interfaces and all are operational.

    Expected Results
    ----------------
    * Success: The test will pass if the device has the correct number of loopback interfaces and none are down.
    * Failure: The test will fail if the loopback interface count is incorrect or any are non-operational.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyLoopbackCount:
          number: 3
    ```
    """

    description = "Verifies the number of loopback interfaces and their status."
    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show ip interface brief", revision=1)]

    class Input(AntaTest.Input):
        """Input model for the VerifyLoopbackCount test."""

        number: PositiveInteger
        """Number of loopback interfaces expected to be present."""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyLoopbackCount."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        loopback_count = 0
        for interface, interface_details in command_output["interfaces"].items():
            if "Loopback" in interface:
                loopback_count += 1
                if (status := interface_details["lineProtocolStatus"]) != "up":
                    self.result.is_failure(f"Interface: {interface} - Invalid line protocol status - Expected: up Actual: {status}")

                if (status := interface_details["interfaceStatus"]) != "connected":
                    self.result.is_failure(f"Interface: {interface} - Invalid interface status - Expected: connected Actual: {status}")

        if loopback_count != self.inputs.number:
            self.result.is_failure(f"Loopback interface(s) count mismatch: Expected {self.inputs.number} Actual: {loopback_count}")


class VerifySVI(AntaTest):
    """Verifies the status of all SVIs.

    Expected Results
    ----------------
    * Success: The test will pass if all SVIs are up.
    * Failure: The test will fail if one or many SVIs are not up.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifySVI:
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show ip interface brief", revision=1)]

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifySVI."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        for interface, int_data in command_output["interfaces"].items():
            if "Vlan" in interface and (status := int_data["lineProtocolStatus"]) != "up":
                self.result.is_failure(f"SVI: {interface} - Invalid line protocol status - Expected: up Actual: {status}")
            if "Vlan" in interface and int_data["interfaceStatus"] != "connected":
                self.result.is_failure(f"SVI: {interface} - Invalid interface status - Expected: connected Actual: {int_data['interfaceStatus']}")


class VerifyL3MTU(AntaTest):
    """Verifies the global layer 3 Maximum Transfer Unit (MTU) for all L3 interfaces.

    Test that L3 interfaces are configured with the correct MTU. It supports Ethernet, Port Channel and VLAN interfaces.

    You can define a global MTU to check, or an MTU per interface and you can also ignored some interfaces.

    Expected Results
    ----------------
    * Success: The test will pass if all layer 3 interfaces have the proper MTU configured.
    * Failure: The test will fail if one or many layer 3 interfaces have the wrong MTU configured.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyL3MTU:
          mtu: 1500
          ignored_interfaces:
              - Vxlan1
          specific_mtu:
              - Ethernet1: 2500
    ```
    """

    description = "Verifies the global L3 MTU of all L3 interfaces."
    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces", revision=1)]

    class Input(AntaTest.Input):
        """Input model for the VerifyL3MTU test."""

        mtu: int = 1500
        """Default MTU we should have configured on all non-excluded interfaces. Defaults to 1500."""
        ignored_interfaces: list[str] = Field(default=["Management", "Loopback", "Vxlan", "Tunnel"])
        """A list of L3 interfaces to ignore"""
        specific_mtu: list[dict[str, int]] = Field(default=[])
        """A list of dictionary of L3 interfaces with their specific MTU configured"""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyL3MTU."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output
        # Set list of interfaces with specific settings
        specific_interfaces: list[str] = []
        if self.inputs.specific_mtu:
            for d in self.inputs.specific_mtu:
                specific_interfaces.extend(d)
        for interface, values in command_output["interfaces"].items():
            if re.findall(r"[a-z]+", interface, re.IGNORECASE)[0] not in self.inputs.ignored_interfaces and values["forwardingModel"] == "routed":
                if interface in specific_interfaces:
                    invalid_mtu = next(
                        (values["mtu"] for custom_data in self.inputs.specific_mtu if values["mtu"] != (expected_mtu := custom_data[interface])), None
                    )
                    if invalid_mtu:
                        self.result.is_failure(f"Interface: {interface} - Incorrect MTU - Expected: {expected_mtu} Actual: {invalid_mtu}")
                # Comparison with generic setting
                elif values["mtu"] != self.inputs.mtu:
                    self.result.is_failure(f"Interface: {interface} - Incorrect MTU - Expected: {self.inputs.mtu} Actual: {values['mtu']}")


class VerifyIPProxyARP(AntaTest):
    """Verifies if Proxy ARP is enabled.

    Expected Results
    ----------------
    * Success: The test will pass if Proxy-ARP is enabled on the specified interface(s).
    * Failure: The test will fail if Proxy-ARP is disabled on the specified interface(s).

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyIPProxyARP:
          interfaces:
            - Ethernet1
            - Ethernet2
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show ip interface", revision=2)]

    class Input(AntaTest.Input):
        """Input model for the VerifyIPProxyARP test."""

        interfaces: list[Interface]
        """List of interfaces to be tested."""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyIPProxyARP."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output

        for interface in self.inputs.interfaces:
            if (interface_detail := get_value(command_output["interfaces"], f"{interface}", separator="..")) is None:
                self.result.is_failure(f"Interface: {interface} - Not found")
                continue

            if not interface_detail["proxyArp"]:
                self.result.is_failure(f"Interface: {interface} - Proxy-ARP disabled")


class VerifyL2MTU(AntaTest):
    """Verifies the global layer 2 Maximum Transfer Unit (MTU) for all L2 interfaces.

    Test that L2 interfaces are configured with the correct MTU. It supports Ethernet, Port Channel and VLAN interfaces.
    You can define a global MTU to check and also an MTU per interface and also ignored some interfaces.

    Expected Results
    ----------------
    * Success: The test will pass if all layer 2 interfaces have the proper MTU configured.
    * Failure: The test will fail if one or many layer 2 interfaces have the wrong MTU configured.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyL2MTU:
          mtu: 1500
          ignored_interfaces:
            - Management1
            - Vxlan1
          specific_mtu:
            - Ethernet1/1: 1500
    ```
    """

    description = "Verifies the global L2 MTU of all L2 interfaces."
    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces", revision=1)]

    class Input(AntaTest.Input):
        """Input model for the VerifyL2MTU test."""

        mtu: int = 9214
        """Default MTU we should have configured on all non-excluded interfaces. Defaults to 9214."""
        ignored_interfaces: list[str] = Field(default=["Management", "Loopback", "Vxlan", "Tunnel"])
        """A list of L2 interfaces to ignore. Defaults to ["Management", "Loopback", "Vxlan", "Tunnel"]"""
        specific_mtu: list[dict[str, int]] = Field(default=[])
        """A list of dictionary of L2 interfaces with their specific MTU configured"""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyL2MTU."""
        # Parameter to save incorrect interface settings
        wrong_l2mtu_intf: list[dict[str, int]] = []
        command_output = self.instance_commands[0].json_output
        # Set list of interfaces with specific settings
        specific_interfaces: list[str] = []
        if self.inputs.specific_mtu:
            for d in self.inputs.specific_mtu:
                specific_interfaces.extend(d)
        for interface, values in command_output["interfaces"].items():
            catch_interface = re.findall(r"^[e,p][a-zA-Z]+[-,a-zA-Z]*\d+\/*\d*", interface, re.IGNORECASE)
            if len(catch_interface) and catch_interface[0] not in self.inputs.ignored_interfaces and values["forwardingModel"] == "bridged":
                if interface in specific_interfaces:
                    wrong_l2mtu_intf.extend({interface: values["mtu"]} for custom_data in self.inputs.specific_mtu if values["mtu"] != custom_data[interface])
                # Comparison with generic setting
                elif values["mtu"] != self.inputs.mtu:
                    wrong_l2mtu_intf.append({interface: values["mtu"]})
        if wrong_l2mtu_intf:
            self.result.is_failure(f"Some L2 interfaces do not have correct MTU configured:\n{wrong_l2mtu_intf}")
        else:
            self.result.is_success()


class VerifyInterfaceIPv4(AntaTest):
    """Verifies the interface IPv4 addresses.

    Expected Results
    ----------------
    * Success: The test will pass if an interface is configured with a correct primary and secondary IPv4 address.
    * Failure: The test will fail if an interface is not found or the primary and secondary IPv4 addresses do not match with the input.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfaceIPv4:
          interfaces:
            - name: Ethernet2
              primary_ip: 172.30.11.1/31
              secondary_ips:
                - 10.10.10.1/31
                - 10.10.10.10/31
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show ip interface", revision=2)]

    class Input(AntaTest.Input):
        """Input model for the VerifyInterfaceIPv4 test."""

        interfaces: list[InterfaceState]
        """List of interfaces with their details."""
        InterfaceDetail: ClassVar[type[InterfaceDetail]] = InterfaceDetail

        @field_validator("interfaces")
        @classmethod
        def validate_interfaces(cls, interfaces: list[T]) -> list[T]:
            """Validate that 'primary_ip' field is provided in each interface."""
            for interface in interfaces:
                if interface.primary_ip is None:
                    msg = f"{interface} 'primary_ip' field missing in the input"
                    raise ValueError(msg)
            return interfaces

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfaceIPv4."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output

        for interface in self.inputs.interfaces:
            if (interface_detail := get_value(command_output["interfaces"], f"{interface.name}", separator="..")) is None:
                self.result.is_failure(f"{interface} - Not found")
                continue

            if (ip_address := get_value(interface_detail, "interfaceAddress.primaryIp")) is None:
                self.result.is_failure(f"{interface} - IP address is not configured")
                continue

            # Combine IP address and subnet for primary IP
            actual_primary_ip = f"{ip_address['address']}/{ip_address['maskLen']}"

            # Check if the primary IP address matches the input
            if actual_primary_ip != str(interface.primary_ip):
                self.result.is_failure(f"{interface} - IP address mismatch - Expected: {interface.primary_ip} Actual: {actual_primary_ip}")

            if interface.secondary_ips:
                if not (secondary_ips := get_value(interface_detail, "interfaceAddress.secondaryIpsOrderedList")):
                    self.result.is_failure(f"{interface} - Secondary IP address is not configured")
                    continue

                actual_secondary_ips = sorted([f"{secondary_ip['address']}/{secondary_ip['maskLen']}" for secondary_ip in secondary_ips])
                input_secondary_ips = sorted([str(ip) for ip in interface.secondary_ips])

                if actual_secondary_ips != input_secondary_ips:
                    self.result.is_failure(
                        f"{interface} - Secondary IP address mismatch - Expected: {', '.join(input_secondary_ips)} Actual: {', '.join(actual_secondary_ips)}"
                    )


class VerifyIpVirtualRouterMac(AntaTest):
    """Verifies the IP virtual router MAC address.

    Expected Results
    ----------------
    * Success: The test will pass if the IP virtual router MAC address matches the input.
    * Failure: The test will fail if the IP virtual router MAC address does not match the input.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyIpVirtualRouterMac:
          mac_address: 00:1c:73:00:dc:01
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show ip virtual-router", revision=2)]

    class Input(AntaTest.Input):
        """Input model for the VerifyIpVirtualRouterMac test."""

        mac_address: MacAddress
        """IP virtual router MAC address."""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyIpVirtualRouterMac."""
        command_output = self.instance_commands[0].json_output["virtualMacs"]
        mac_address_found = get_item(command_output, "macAddress", self.inputs.mac_address)

        if mac_address_found is None:
            self.result.is_failure(f"IP virtual router MAC address `{self.inputs.mac_address}` is not configured.")
        else:
            self.result.is_success()


class VerifyInterfacesSpeed(AntaTest):
    """Verifies the speed, lanes, auto-negotiation status, and mode as full duplex for interfaces.

    - If the auto-negotiation status is set to True, verifies that auto-negotiation is successful, the mode is full duplex and the speed/lanes match the input.
    - If the auto-negotiation status is set to False, verifies that the mode is full duplex and the speed/lanes match the input.

    Expected Results
    ----------------
    * Success: The test will pass if an interface is configured correctly with the specified speed, lanes, auto-negotiation status, and mode as full duplex.
    * Failure: The test will fail if an interface is not found, if the speed, lanes, and auto-negotiation status do not match the input, or mode is not full duplex.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyInterfacesSpeed:
          interfaces:
            - name: Ethernet2
              auto: False
              speed: 10
            - name: Eth3
              auto: True
              speed: 100
              lanes: 1
            - name: Eth2
              auto: False
              speed: 2.5
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show interfaces")]

    class Input(AntaTest.Input):
        """Inputs for the VerifyInterfacesSpeed test."""

        interfaces: list[InterfaceDetail]
        """List of interfaces to be tested"""

        class InterfaceDetail(BaseModel):
            """Detail of an interface."""

            name: EthernetInterface
            """The name of the interface."""
            auto: bool
            """The auto-negotiation status of the interface."""
            speed: float = Field(ge=1, le=1000)
            """The speed of the interface in Gigabits per second. Valid range is 1 to 1000."""
            lanes: None | int = Field(None, ge=1, le=8)
            """The number of lanes in the interface. Valid range is 1 to 8. This field is optional."""

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyInterfacesSpeed."""
        self.result.is_success()
        command_output = self.instance_commands[0].json_output

        # Iterate over all the interfaces
        for interface in self.inputs.interfaces:
            intf = interface.name

            # Check if interface exists
            if not (interface_output := get_value(command_output, f"interfaces.{intf}")):
                self.result.is_failure(f"Interface `{intf}` is not found.")
                continue

            auto_negotiation = interface_output.get("autoNegotiate")
            actual_lanes = interface_output.get("lanes")

            # Collecting actual interface details
            actual_interface_output = {
                "auto negotiation": auto_negotiation if interface.auto is True else None,
                "duplex mode": interface_output.get("duplex"),
                "speed": interface_output.get("bandwidth"),
                "lanes": actual_lanes if interface.lanes is not None else None,
            }

            # Forming expected interface details
            expected_interface_output = {
                "auto negotiation": "success" if interface.auto is True else None,
                "duplex mode": "duplexFull",
                "speed": interface.speed * BPS_GBPS_CONVERSIONS,
                "lanes": interface.lanes,
            }

            # Forming failure message
            if actual_interface_output != expected_interface_output:
                for output in [actual_interface_output, expected_interface_output]:
                    # Convert speed to Gbps for readability
                    if output["speed"] is not None:
                        output["speed"] = f"{custom_division(output['speed'], BPS_GBPS_CONVERSIONS)}Gbps"
                failed_log = get_failed_logs(expected_interface_output, actual_interface_output)
                self.result.is_failure(f"For interface {intf}:{failed_log}\n")


class VerifyLACPInterfacesStatus(AntaTest):
    """Verifies the Link Aggregation Control Protocol (LACP) status of the interface.

    This test performs the following checks for each specified interface:

      1. Verifies that the interface is a member of the LACP port channel.
      2. Verifies LACP port states and operational status:
        - Activity: Active LACP mode (initiates)
        - Timeout: Short (Fast Mode), Long (Slow Mode - default)
        - Aggregation: Port aggregable
        - Synchronization: Port in sync with partner
        - Collecting: Incoming frames aggregating
        - Distributing: Outgoing frames aggregating

    Expected Results
    ----------------
    * Success: Interface is bundled and all LACP states match expected values for both actor and partner
    * Failure: If any of the following occur:
        - Interface or port channel is not configured.
        - Interface is not bundled in port channel.
        - Actor or partner port LACP states don't match expected configuration.
        - LACP rate (timeout) mismatch when fast mode is configured.

    Examples
    --------
    ```yaml
    anta.tests.interfaces:
      - VerifyLACPInterfacesStatus:
          interfaces:
            - name: Ethernet1
              portchannel: Port-Channel100
    ```
    """

    categories: ClassVar[list[str]] = ["interfaces"]
    commands: ClassVar[list[AntaCommand | AntaTemplate]] = [AntaCommand(command="show lacp interface", revision=1)]

    class Input(AntaTest.Input):
        """Input model for the VerifyLACPInterfacesStatus test."""

        interfaces: list[InterfaceState]
        """List of interfaces with their expected state."""
        InterfaceState: ClassVar[type[InterfaceState]] = InterfaceState

        @field_validator("interfaces")
        @classmethod
        def validate_interfaces(cls, interfaces: list[T]) -> list[T]:
            """Validate that 'portchannel' field is provided in each interface."""
            for interface in interfaces:
                if interface.portchannel is None:
                    msg = f"{interface} 'portchannel' field missing in the input"
                    raise ValueError(msg)
            return interfaces

    @AntaTest.anta_test
    def test(self) -> None:
        """Main test function for VerifyLACPInterfacesStatus."""
        self.result.is_success()

        # Member port verification parameters.
        member_port_details = ["activity", "aggregation", "synchronization", "collecting", "distributing", "timeout"]

        command_output = self.instance_commands[0].json_output
        for interface in self.inputs.interfaces:
            # Verify if a PortChannel is configured with the provided interface
            if not (interface_details := get_value(command_output, f"portChannels..{interface.portchannel}..interfaces..{interface.name}", separator="..")):
                self.result.is_failure(f"{interface} - Not configured")
                continue

            # Verify the interface is bundled in port channel.
            actor_port_status = interface_details.get("actorPortStatus")
            if actor_port_status != "bundled":
                self.result.is_failure(f"{interface} - Not bundled - Port Status: {actor_port_status}")
                continue

            # Collecting actor and partner port details
            actor_port_details = interface_details.get("actorPortState", {})
            partner_port_details = interface_details.get("partnerPortState", {})

            # Collecting actual interface details
            actual_interface_output = {
                "actor_port_details": {param: actor_port_details.get(param, "NotFound") for param in member_port_details},
                "partner_port_details": {param: partner_port_details.get(param, "NotFound") for param in member_port_details},
            }

            # Forming expected interface details
            expected_details = {param: param != "timeout" for param in member_port_details}
            # Updating the short LACP timeout, if expected.
            if interface.lacp_rate_fast:
                expected_details["timeout"] = True

            if (act_port_details := actual_interface_output["actor_port_details"]) != expected_details:
                self.result.is_failure(f"{interface} - Actor port details mismatch - {format_data(act_port_details)}")

            if (part_port_details := actual_interface_output["partner_port_details"]) != expected_details:
                self.result.is_failure(f"{interface} - Partner port details mismatch - {format_data(part_port_details)}")

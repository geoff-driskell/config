"""
Auto fan speed controller app

Args:
auto_fan_speed_master:
    module: auto_fan_speed
    class: AutoFanSpeed
    temp_sensor: sensor.master_bedroom_temperature
    thermostat: climate.master_bedroom
    fan: fan.master_bedroom_fan
"""
from typing import Any, cast
import appdaemon.plugins.hass.hassapi as hass

DEFAULT_MIN_TEMP = 65
DEFAULT_MAX_TEMP = 75


class AutoFanSpeed(hass.Hass):
    """Fan speed controller class."""

    def initialize(self):
        """Initialize the fan speed class."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        self.temp_sensor: str = self.args.get("temp_sensor", None)
        self.fan: str = self.args.get("fan", None)
        self.thermostat = self.args.get("thermostat", "climate.master")
        self.max_temp = DEFAULT_MAX_TEMP
        self.min_temp = DEFAULT_MIN_TEMP
        self.update_config("", "", "", "", "")

        self.listen_state(self.temperature_change, entity_id=self.temp_sensor)
        self.listen_state(self.update_config, entity_id=self.thermostat)

    def update_config(self, entity, attribute, old, new, kwargs) -> None:
        """Update HVAC config"""
        # pylint: disable=attribute-defined-outside-init
        self.hvac_mode = cast(str, self.get_state(entity_id=self.thermostat))
        self.log(f"HVAC mode is currently set to {self.hvac_mode}")
        if self.hvac_mode == "off":
            self.min_temp = DEFAULT_MIN_TEMP
            self.max_temp = DEFAULT_MAX_TEMP
        elif self.hvac_mode == "heat":
            self.min_temp = cast(
                int, self.get_state(entity_id=self.thermostat, attribute="temperature")
            )
            self.max_temp = self.min_temp + 4
        elif self.hvac_mode == "cool":
            self.max_temp = cast(
                int, self.get_state(entity_id=self.thermostat, attribute="temperature")
            )
            self.min_temp = self.max_temp - 4
        elif self.hvac_mode == "heat_cool":
            self.min_temp = cast(
                int,
                self.get_state(entity_id=self.thermostat, attribute="target_temp_low"),
            )
            self.max_temp = cast(
                int,
                self.get_state(entity_id=self.thermostat, attribute="target_temp_high"),
            )
        else:
            pass
        self.log(
            f"Config updated: Min temp is {self.min_temp} and Max temp is {self.max_temp}"
        )

    def is_fan_on(self) -> bool:
        """Check if the fan is on."""
        if self.get_state(self.fan) == "on":
            self.log("Fan is on.")
            return True
        else:
            self.log("Fan is off.")
            return False

    def temperature_change(self, entity, attribute, old, new, kwargs):
        """Handle temperature changes."""
        if self.is_fan_on():
            room_temperature = float(new)
            self.log(f"Temperature has changed from {old} to {new}")
            fan_speed_percentage = self.get_target_fan_speed(
                room_temperature=room_temperature
            )
            self.log(f"Fan speed should be {fan_speed_percentage}")
            self.call_service(
                "fan/set_percentage",
                entity_id=self.fan,
                percentage=fan_speed_percentage,
            )

    def get_target_fan_speed(self, room_temperature: float) -> int:
        """Set the fan speed based on temperature."""

        if room_temperature < self.min_temp:
            room_temperature = self.min_temp
        elif room_temperature > self.max_temp:
            room_temperature = self.max_temp
        fan_percentage = 100* ((room_temperature - self.min_temp) / (
            self.max_temp - self.min_temp
        ))
        if fan_percentage < 25:
            fan_percentage = 25

        return int(fan_percentage)

"Class to handle the home being empty or not."

import attr
from enum import Enum
from typing import Any, cast

import appdaemon.plugins.hass.hassapi as hass
import appdaemon.adbase as ad

__version__ = "0.0.1"


class State(Enum):
    """States for the home."""
    HOME = "home"
    AWAY = "away"
    EXTENDED_AWAY = "extended_away"

    @staticmethod
    def from_string(label):
        """Convert string to enum."""
        if not isinstance(label, str):
            raise TypeError("Argument label needs to be a string.")
        if label.casefold() in ("home"):
            return State.HOME
        elif label.casefold() in ("away", "not_home", "not home"):
            return State.AWAY
        elif label.casefold() in ("extended away", "extended_away", "vacation"):
            return State.EXTENDED_AWAY
        else:
            raise ValueError(f"Argument label '{label}' is not a valid state.")


class TrackerState(Enum):
    """Tracker state for people."""
    HOME = "home"
    NOT_HOME = "not_home"

    @staticmethod
    def from_string(label):
        """Convert string to enum"""
        if not isinstance(label, str):
            raise TypeError("Argument label needs to be a string.")
        if label.casefold() == "home":
            return TrackerState.HOME
        else:
            return TrackerState.NOT_HOME


class HVACMode(Enum):
    """HVAC mode for climate devices."""

    # All activity disabled / Device is off/standby
    OFF = "off"

    # Heating
    HEAT = "heat"

    # Cooling
    COOL = "cool"

    # The device supports heating and cooling to a range
    HEAT_COOL = "heat_cool"


@attr.s
class Thermostat:
    """Class to hold thermostat data."""

    entity_id = attr.ib(type=str)
    hassio = attr.ib(type=hass.Hass)
    curr_state = attr.ib(type=str, init=False)
    curr_temperature = attr.ib(type=int, init=False)
    curr_target_temp_high = attr.ib(type=int, init=False)
    curr_target_temp_low = attr.ib(type=int, init=False)
    prev_state = attr.ib(type=str, init=False)
    prev_temperature = attr.ib(type=int, init=False)
    prev_target_temp_high = attr.ib(type=int, init=False)
    prev_target_temp_low = attr.ib(type=int, init=False)

    def __attrs_post_init__(self):
        self.curr_state = self.hassio.get_state(entity_id=self.entity_id)
        self.curr_temperature = self.hassio.get_state(
            entity_id=self.entity_id, attribute="temperature"
        )
        self.curr_target_temp_high = self.hassio.get_state(
            entity_id=self.entity_id, attribute="target_temp_high"
        )
        self.curr_target_temp_low = self.hassio.get_state(
            entity_id=self.entity_id, attribute="target_temp_low"
        )

    @classmethod
    def from_config(cls, config, hassio):
        """Create thermostat from config."""
        return [cls(entity_id=item, hassio=hassio) for item in config["thermostats"]]

    def _save_curr_state_to_prev(self):
        """Save the current state for later."""
        self.prev_state = self.hassio.get_state(entity_id=self.entity_id)
        self.prev_temperature = self.hassio.get_state(
            entity_id=self.entity_id, attribute="temperature"
        )
        self.prev_target_temp_high = self.hassio.get_state(
            entity_id=self.entity_id, attribute="target_temp_high"
        )
        self.prev_target_temp_low = self.hassio.get_state(
            entity_id=self.entity_id, attribute="target_temp_low"
        )

    def set_away(self, offset):
        """Offset the temperature for low duration away."""
        self.hassio.log(f"Setting {self.entity_id} to away.")
        self._save_curr_state_to_prev()
        self.curr_state = self.prev_state
        if self.curr_state == "heat":
            self.curr_temperature = self.prev_temperature - offset
            self.hassio.call_service(
                "climate/set_temperature",
                entity_id=self.entity_id,
                temperature=self.curr_temperature,
            )
        elif self.curr_state == "cool":
            self.curr_temperature = self.prev_temperature + offset
            self.hassio.call_service(
                "climate/set_temperature",
                entity_id=self.entity_id,
                temperature=self.curr_temperature,
            )
        elif self.curr_state == "heat_cool":
            self.curr_target_temp_high = self.prev_target_temp_high + offset
            self.curr_target_temp_low = self.prev_target_temp_low - offset
            self.hassio.call_service(
                "climate/set_temperature",
                entity_id=self.entity_id,
                target_temp_high=self.curr_target_temp_high,
                target_temp_low=self.curr_target_temp_low,
            )

    def set_home(self):
        """Return the thermostat to previous settings when home."""
        self.hassio.log(f"Setting {self.entity_id} to home.")
        self.curr_state = self.prev_state
        self.curr_temperature = self.prev_temperature
        self.curr_target_temp_high = self.prev_target_temp_high
        self.curr_target_temp_low = self.prev_target_temp_low
        self._save_curr_state_to_prev()
        if self.curr_state == "heat":
            self.hassio.call_service(
                "climate/set_temperature",
                entity_id=self.entity_id,
                temperature=self.curr_temperature,
            )
        elif self.curr_state == "cool":
            self.hassio.call_service(
                "climate/set_temperature",
                entity_id=self.entity_id,
                temperature=self.curr_temperature,
            )
        elif self.curr_state == "heat_cool":
            self.hassio.call_service(
                "climate/set_temperature",
                entity_id=self.entity_id,
                target_temp_high=self.curr_target_temp_high,
                target_temp_low=self.curr_target_temp_low,
            )

    def set_extended_away(self):
        """Set to eco mode for vacation."""
        self.hassio.log(f"Setting {self.entity_id} to extended away.")
        self._save_curr_state_to_prev()
        self.hassio.call_service(
            "climate/set_preset_mode", entity_id=self.entity_id, preset_mode="eco"
        )

    def undo_extended_away(self):
        """Return the house to normal mode after vacation."""
        self.hassio.log(f"Setting {self.entity_id} to home from extended away.")
        self._save_curr_state_to_prev()
        self.hassio.call_service(
            "climate/set_preset_mode", entity_id=self.entity_id, preset_mode="none"
        )


class App(ad.ADBase):
    """The base app class"""

    def initialize(self):
        """Initializer"""
        # pylint: disable=attribute-defined-outside-init
        Thermostat("climate.downstairs")
        self.hass = cast(hass.Hass, self.get_plugin_api("HASS"))
        self.ad_api = self.get_ad_api()

        self.args: dict[str, Any] = dict(self.args)
        self.house_state = State.HOME

        self.home_state: str = self.args.get("home_state", "home")
        self.hass.log(f"Configured home state is {self.home_state}.")
        self.away_state: str = self.args.get("away_state", "away")
        self.hass.log(f"Configured away state is {self.away_state}.")
        self.motion_blocker: str = self.args.get(
            "motion_blocker", "input_boolean.dummy"
        )
        self.hass.log(f"Configured motion blocker is {self.motion_blocker}.")

        self.trackers: dict[str, Any] = {}
        for name in self.args["trackers"]:
            state = self.hass.get_state(name)
            self.hass.log(f"Tracking: {name}. Current state is {state}")
            self.trackers[name] = state
            self.hass.listen_state(self.tracker_changed, name)

        self.timer = None
        self.current_state = None

        # Store the names of all the lights to change.
        self.lights: set(str) = self.args.pop("lights", set())
    
    def house_state_changed(self) -> dict[str, Any]:
        """Check if house is empty."""
        # pylint: disable=attribute-defined-outside-init
        # Loop over all the device trackers and get their states.  If any of
        # them are away, our state is away.  Also see if our state changes
        # because that will cause the lights to be turned on or off.
        prev = self.home_state

        _home_state = State.AWAY
        for name, state in self.trackers.items():
            self.hass.log(f"Tracker {name} = {state}.")
            if state == self.home_state:
                self.away = False
                break

        house = {"old": prev, "new": self.away}
        return house

    def tracker_changed(self, entity, attribute, old, new, kwargs):
        self.hass.log(f"Tracker change: {old} -> {new}")
        old_state = TrackerState.from_string(old)
        new_state = TrackerState.from_string(new)



        if old_state == TrackerState.NOT_HOME and new_state == TrackerState.HOME:
            
        if old_state == TrackerState.HOME and new_state == TrackerState.NOT_HOME:
            self._set_person_state(entity=entity, state=State.JustLeft)

    def _on_scheduled_state_change(self, kwargs):
        new_state = kwargs.pop("new_state")
        self._set_person_state(new_state)

    def _schedule_state_change(self, delay, new_state):
        self.timer = self.run_in(
            self._on_scheduled_state_change, delay=delay, new_state=new_state
        )

    def _set_person_state(self, entity, state):
        self._current_state = state
        self.ad_api.set_state(
            entity_id=entity, state=self._current_state, namespace="presence"
        )
        if self.timer:
            self.cancel_timer(self.timer)
        if state == State.JustArrived:
            self._schedule_state_change(self._just_arrived_delay, State.Home)
        elif state == State.JustLeft:
            self._schedule_state_change(self._just_left_delay, State.Away)
        elif state == State.Away:
            self._schedule_state_change(self._extended_away_delay, State.ExtendedAway)

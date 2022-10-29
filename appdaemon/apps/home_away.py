"""
Handle home and away at Geoff and Victoria's house
"""
from typing import Any
import appdaemon.plugins.hass.hassapi as hass


class HomeAway(hass.Hass):
    """Class to handle home and away."""

    def initialize(self):
        """Initialize the class."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)
        self.away = False

        self.home_state: str = self.args.get("home_state", "home")
        self.away_state: str = self.args.get("away_state", "away")
        self.motion_blocker: str = self.args.get(
            "motion_blocker", "input_boolean.dummy"
        )

        # Initialize Thermostat settings
        self.thermostats: set[str] = self.args.get("thermostats", "climate.dummy")
        self.away_offset: int = self.args.get("away_offset", 0)
        self.prev_thermostat_settings: dict[str, dict[str, Any]]

        # Map tracker name to state.
        self.trackers: dict[str, Any] = {}
        for name in self.args["trackers"]:
            state = self.get_state(name)
            self.log(f"Tracking: {name}. Current state is {state}")
            self.trackers[name] = state
            self.listen_state(self.tracker_changed, name)

        # Store the names of all the lights to change.
        self.lights: set(str) = self.args.pop("lights", set())

    def turn_off_lights(self, kwargs):
        """Turn off the lights."""
        # pylint: disable=attribute-defined-outside-init
        self.log("Turning off the lights.")

        self.log("Turning off lights...")
        for light in self.lights:
            self.turn_off(light)

    def house_state_changed(self) -> bool:
        """Check if house is empty."""
        # pylint: disable=attribute-defined-outside-init
        # Loop over all the device trackers and get their states.  If any of
        # them are away, our state is away.  Also see if our state changes
        # because that will cause the lights to be turned on or off.
        prev = self.away
        self.log(f"Current state: {self.state()}.")

        self.away = True
        for name, state in self.trackers.items():
            self.log(f"Tracker {name} = {state}.")
            if state == self.home_state:
                self.away = False
                break

        changed: bool = self.away != prev
        if changed:
            self.log(f"State has changed to {self.state()}.")
        else:
            self.log(f"State is unchanged from {self.state()}.")
        return changed

    def tracker_changed(self, entity, attribute, old, new, kwargs):
        """Handle updates in house trackers."""
        # pylint: disable=attribute-defined-outside-init
        # The actual input state is ignored.  We need to loop over each tracker
        # to see if any of them are away so it's easier to just do that for
        # all of them rather than track those states ourselves.
        self.log(f"Tracker {entity} changed to {new}.")
        self.trackers[entity] = new

        # See if the state has been changed.  If it hasn't or the sun is up,
        # don't do anything.  This also updates self.away.
        if not self.house_state_changed():
            self.log("Ignoring tracker update - no change in state")
            return

        # State has changed to away.  Turn off the lights, block motion.
        if self.away:
            self.log("State changed to away - turning off the lights.")
            if self.motion_blocker is not None:
                self.turn_on(self.motion_blocker)
            self.turn_off_lights(kwargs=kwargs)
            for thermostat in self.thermostats:
                self.set_thermostat_away(thermostat_entity=thermostat, temp_offset=self.away_offset)


        # State has changed to home.  Unblock motion.
        else:
            self.log("State changed to home - unblocking motion lights.")
            if self.motion_blocker is not None:
                self.turn_off(self.motion_blocker)
            for thermostat in self.thermostats:
                self.set_thermostat_home(thermostat_entity=thermostat)

    def state(self):
        """Return the current state of the house."""
        # pylint: disable=attribute-defined-outside-init
        if self.away:
            return "away"
        else:
            return "home"

    def get_thermostat_state(self, thermostat_entity) -> dict[str, Any]:
        """Retrieve the current state of the thermostat"""
        therm_settings: dict[str, Any] = {}
        therm_settings["state"] = self.get_state(entity_id=thermostat_entity)
        therm_settings["temperature"] = self.get_state(
            entity_id=thermostat_entity, attribute="temperature"
        )
        therm_settings["target_temp_high"] = self.get_state(
            entity_id=thermostat_entity, attribute="target_temp_high"
        )
        therm_settings["target_temp_low"] = self.get_state(
            entity_id=thermostat_entity, attribute="target_temp_low"
        )

        return therm_settings

    def set_thermostat_away(self, thermostat_entity, temp_offset):
        """Change the thermostat to away settings"""
        current_settings: dict[str, Any] = self.get_thermostat_state(
            thermostat_entity=thermostat_entity
        )
        curr_state = current_settings.get("state")
        curr_temperature = current_settings.get("temperature")
        curr_target_temp_high = current_settings.get("target_temp_high")
        curr_target_temp_low = current_settings.get("target_temp_low")
        self.prev_thermostat_settings[thermostat_entity] = current_settings
        if curr_state == "heat_cool":
            self.log(
                f"Thermostat is in heat/cool mode, " \
                f"raising the target high temp by {temp_offset} degrees."
            )
            self.log(
                f"Thermostat is in heat/cool mode, " \
                f"lowering the target low temp by {temp_offset} degrees."
            )
            target_temp_high = curr_target_temp_high - temp_offset
            target_temp_low = curr_target_temp_low + temp_offset
            self.call_service(
                "climate/set_temperature",
                entity_id=thermostat_entity,
                target_temp_high=target_temp_high,
                target_temp_low=target_temp_low,
            )
        elif curr_state == "heat":
            self.log(
                f"Thermostat is in heat mode, lowering the temp by {temp_offset} degrees."
            )
            temperature = curr_temperature - temp_offset
            self.call_service(
                "climate/set_temperature",
                entity_id=thermostat_entity,
                temperature=temperature,
            )
        elif curr_state == "cool":
            self.log(
                f"Thermostat is in cool mode, raising the temp by {temp_offset} degrees."
            )
            temperature = curr_temperature + temp_offset
            self.call_service(
                "climate/set_temperature",
                entity_id=thermostat_entity,
                temperature=temperature,
            )
        else:
            self.log("Thermostat is off, going to leave it that way.")

    def set_thermostat_home(self, thermostat_entity):
        """Change the thermostat to home settings"""
        prev_state = self.prev_thermostat_settings.get(thermostat_entity).get("state")
        prev_temperature = self.prev_thermostat_settings.get(thermostat_entity).get(
            "state"
        )
        prev_target_temp_high = self.prev_thermostat_settings.get(
            thermostat_entity
        ).get("state")
        prev_target_temp_low = self.prev_thermostat_settings.get(thermostat_entity).get(
            "state"
        )

        if prev_state == "heat_cool":
            self.log(f"Restoring {thermostat_entity} to heat/cool mode.")
            self.log(
                f"Restoring {thermostat_entity} target high temperature to {prev_target_temp_high}."
            )
            self.log(
                f"Restoring {thermostat_entity} target low temperature to {prev_target_temp_low}."
            )
            self.call_service(
                "climate/set_temperature",
                entity_id=thermostat_entity,
                target_temp_high=prev_target_temp_high,
                target_temp_low=prev_target_temp_low,
            )
        elif prev_state == "heat":
            self.log(f"Restoring {thermostat_entity} to heat mode.")
            self.call_service(
                "climate/set_temperature",
                entity_id=thermostat_entity,
                temperature=prev_temperature,
            )
        elif prev_state == "cool":
            self.log(f"Restoring {thermostat_entity} to cool mode.")
            self.call_service(
                "climate/set_temperature",
                entity_id=thermostat_entity,
                temperature=prev_temperature,
            )


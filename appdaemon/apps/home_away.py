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

        self.home_state = self.args.get('home_state', 'home')
        self.away_state = self.args.get('away_state', 'away')
        self.motion_blocker = self.args.get("motion_blocker", None)

        # Map tracker name to state.
        self.trackers: dict[str, Any] = {}
        for name in self.args['trackers']:
            state = self.get_state(name)
            self.log(f"Tracking: {name}. Current state is {state}")
            self.trackers[name] = state
            self.listen_state(self.tracker_changed, name)

        # Store the names of all the lights to change.
        self.lights: set(str) = self.args.pop('lights', set())

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

        # State has changed to home.  Unblock motion.
        else:
            self.log("State changed to home - unblocking motion lights.")
            if self.motion_blocker is not None:
                self.turn_off(self.motion_blocker)

    def state(self):
        """Return the current state of the house."""
        # pylint: disable=attribute-defined-outside-init
        if self.away:
            return "away"
        else:
            return "home"

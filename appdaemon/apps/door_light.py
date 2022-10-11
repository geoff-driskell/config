"""
Control room light with door position.
"""
from typing import Any
import appdaemon.plugins.hass.hassapi as hass

class DoorLight(hass.Hass):
    """Main class."""
    def initialize(self):
        """Initialize the class."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        self.door: str = self.args.get("door", None)
        # define light entities switched by automotionlight
        self.lights: set[str] = self.args.pop("lights", set())


        self.listen_state(self.door_opened, entity_id=self.door, new="on")
        self.listen_state(self.door_closed, entity_id=self.door, new="off")
    
    def door_opened(self, entity, attribute, old, new, kwargs):
        """Turn on the lights."""
        for light in self.lights:
            self.turn_on(light)
    
    def door_closed(self, entity, attribute, old, new, kwargs):
        """Turn off the lights."""
        for light in self.lights:
            self.turn_off(light)
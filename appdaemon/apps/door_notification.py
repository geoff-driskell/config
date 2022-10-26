"""Notify when exterior doors are opened."""
from typing import Any
import appdaemon.plugins.hass.hassapi as hass

class DoorNotification(hass.Hass):
    """Class for door monitoring."""
    def initialize(self):
        """Initialize door monitoring."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        self.doors: set[str] = self.args.get("doors", set())

        for door in self.doors:
            self.listen_state(self.state_change, door)
    
    def state_change(self, entity, attribute, old, new, kwargs):
        """Handle state changes of the door."""
        if new == "on" or new == "open":
            state = "open"
        else:
            state = "closed"
        message = f"{self.friendly_name(entity)} is {state}"
        self.log(message)
        kitchen = self.get_app("kitchen_sound")
        kitchen.tts(message, 0.5, 3)


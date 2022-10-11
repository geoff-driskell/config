"""
Handle the master bathroom shower light.
"""
from typing import Any
import appdaemon.plugins.hass.hassapi as hass

DEFAULT_TIMEOUT = 2700

class ShowerLight(hass.Hass):
    """Main class."""
    def initialize(self):
        """Initialize the class."""
        # pylint: disable=attribute-defined-outside-init
        self.shower_occupied: bool = False
        self.listen_state(self.door_opened, entity_id="binary_sensor.master_bathroom_shower_door", new="on")
        self.listen_state(self.motion_cleared, entity_id="binary_sensor.master_bathroom_occupancy", new="off")
    

    def door_opened(self, entity: str, attribute: str, old: str, new: str, _: dict[str, Any]
    ) -> None:
        """Turn on the shower light."""
        self.shower_occupied = True
        self.turn_on("switch.master_bathroom_shower_lights")

    def motion_cleared(self, entity: str, attribute: str, old: str, new: str, _: dict[str, Any]
    ) -> None:
        """Turn off the shower light."""
        self.shower_occupied = False
        self.turn_off("switch.master_bathroom_shower_lights")
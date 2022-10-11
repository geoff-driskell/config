"""
Outside Lights

Module to turn on lights at sunset and off at sunrise.
"""

from typing import Any
import appdaemon.plugins.hass.hassapi as hass

class OutsideLights(hass.Hass):
    """Class to handle outside overnight lights."""
    def initialize(self):
        """Initialize the outdoor lighting app."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        # Run at Sunrise
        self.run_at_sunrise(self.sunrise_gd)

        # Run at Sunset
        self.run_at_sunset(self.sunset_gd)
        self.lights: set[str] = self.args.pop("lights", set())

    def sunrise_gd(self, kwargs):
        """Turn off the lights at sunrise."""
        self.log("Sunrise triggered.")
        for light in self.lights:
            self.turn_off(light)

    def sunset_gd(self, kwargs):
        """Turn off the lights at sunrise."""
        self.log("Sunset triggered")
        for light in self.lights:
            self.turn_on(light)

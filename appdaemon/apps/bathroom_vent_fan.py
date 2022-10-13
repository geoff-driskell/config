"""
App to turn on the fan when it's humid.
"""
from typing import Any
import appdaemon.plugins.hass.hassapi as hass

class BathroomVentFan(hass.Hass):
    """Automatically turn on bathroom fan when humidity rises."""

    def initialize(self):
        """Start up the vent fan app."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        self.fan: str = self.args.get("fan", None)
        self.max_humidity: float = float(self.args.get("max_humidity", None))
        self.humidity_sensor: str = self.args.get("humidity_sensor", None)

        self.max_timer_handle = None
        self.min_timer_handle = None
        self.on_min_time = False
        self.fan_running = False

        self.listen_state(self.manual_on, entity_id=self.fan, new="on")
        self.listen_state(self.manual_off, entity_id=self.fan, new="off")

        self.listen_state(self.humidity_change, entity_id=self.humidity_sensor)

    @property
    def target_humidity(self):
        """Set the target humidity."""
        # pylint: disable=attribute-defined-outside-init
        return self.max_humidity * 0.95

    def reset_app(self):
        """Cancel timers and set variables to initial settings."""
        # pylint: disable=attribute-defined-outside-init
        if self.timer_running(self.min_timer_handle):
            self.cancel_timer(self.min_timer_handle)
        if self.timer_running(self.max_timer_handle):
            self.cancel_timer(self.max_timer_handle)
        self.max_timer_handle = None
        self.min_timer_handle = None
        self.on_min_time = False
        self.fan_running = False

    def manual_on(self, entity, attribute, old, new, kwargs):
        """Handle fan being manually turned on."""
        # pylint: disable=attribute-defined-outside-init
        if not self.fan_running:
            self.log(f"{self.fan} was turned on by someone else.")
            self.fan_running = True
            # Save the current humidity reading so we can run the
            # fan until we get close.
            self.humidity: float = float(self.get_state(self.humidity_sensor))

            # Set a timer to not let the fan run more than an hour
            self.max_timer_handle = self.run_in(self.fan_off, 60 * 60)

            # Set a timer to run for the minimum time
            self.on_min_time = False
            self.min_timer_handle = self.run_in(self.hit_min_time, 10 * 60)

    def manual_off(self, entity, attribute, old, new, kwargs):
        """Handle fan being manually turned off."""
        # pylint: disable=attribute-defined-outside-init
        if self.fan_running:
            self.log(f"{self.fan} was turned off by someone else.")
            self.reset_app()

    def humidity_triggered(self, entity, attribute, old, new, kwargs):
        """Turn on the fan when humidity is triggered."""
        # pylint: disable=attribute-defined-outside-init
        if not self.fan_running:
            self.log(f"Turning on {self.fan}.")
            self.turn_on(self.fan)
            self.fan_running = True

            # Save the current humidity reading so we can run the
            # fan until we get close.
            self.humidity: float = float(self.get_state(self.humidity_sensor))

            # Set a timer to not let the fan run more than an hour
            self.max_timer_handle = self.run_in(self.fan_off, 60 * 60)

            # Set a timer to run for the minimum time
            self.on_min_time = False
            self.min_timer_handle = self.run_in(self.hit_min_time, 10 * 60)

    def fan_off(self, kwargs):
        """Turn the fan off."""
        # pylint: disable=attribute-defined-outside-init
        if  self.on_min_time and self.fan_running:
            self.reset_app()
            self.turn_off(self.fan)

    def hit_min_time(self, kwargs):
        """Record hitting the minimum timer."""
        # pylint: disable=attribute-defined-outside-init
        self.on_min_time = True
        self.min_timer_handle = None

    def humidity_change(self, entity, attribute, old, new, kwargs):
        """Handle humidity changes in the bathroom."""
        # pylint: disable=attribute-defined-outside-init
        if float(self.get_state(self.humidity_sensor)) > self.max_humidity:
            self.humidity_triggered(entity=entity, attribute=attribute, old=old, new=new, kwargs=kwargs)
        if float(self.get_state(self.humidity_sensor)) <= self.target_humidity:
            self.fan_off(kwargs=kwargs)

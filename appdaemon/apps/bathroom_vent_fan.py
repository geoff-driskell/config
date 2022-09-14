import appdaemon.plugins.hass.hassapi as hass

class BathroomVentFan(hass.Hass):
    """Automatically turn on bathroom vent fan when humidity rises"""

    def initialize(self):
        self.fan = self.args["fan"]
        self.trend_sensor = self.args["trend_sensor"]
        self.humidity_sensor = self.args["humidity_sensor"]

        self.max_timer_handle = None
        self.min_timer_handle = None
        self.on_min_time = False
        self.humidity = None
        self.fan_running = False

        # If the fan is turned on manually or the trend sensor goes on, start
        # the fan
        self.listen_state(self.start_fan, entity=self.fan, new="on")
        self.listen_state(self.start_fan, entity=self.trend_sensor, new="on")

        self.listen_state(self.humidity_change, entity=self.humidity_sensor)

    @property
    def humidity_max(self):
        return self.humidity * 1.05

    def start_fan(self, entity, attribute, old, new, kwargs):
        if not self.fan_running:
            self.log("Turning on {0}.".format(self.fan))
            self.turn_on(self.args["fan"])
            self.fan_running = True

            # Save the current humidity reading so we can run the fan until we are
            # close to this again.
            self.humidity = float(self.get_state(self.humidity_sensor))

            # Set a timer to not run the fan for more than an hour
            self.max_timer_handle = self.run_in(self.turn_off, 60 * 60)
            # Set a timer to always run at least 10 minutes. Don't want the fan
            # going on and off constantly.
            self.on_min_time = False
            self.min_timer_handle = self.run_in(self.hit_min_time, 60 * 10)

    def stop_fan(self, kwargs):
        if self.on_min_time and self.fan_running:
            self.call_service("fan/turn_off", entity_id=self.fan)

            # If we were turned off before the timer expired, cancel it
            self.cancel_timer(self.max_timer_handle)

            # Reset variables
            self.max_timer_handle = None
            self.humidity = None
            self.fan_running = False

    def hit_min_time(self, kwargs):
        self.on_min_time = True
        self.min_timer_handle = None

    def humidity_change(self, entity, attribute, old, new, kwargs):
        """When the humidity changes, check if it is within the threshold to
        turn off."""
        self.log("The current humidity is {0}, the target humidity is {1}.".format(self.get_state(self.humidity_sensor), self.humidity_max), level="INFO")
        if float(self.get_state(self.humidity_sensor)) < self.humidity_max:
            self.stop_fan(kwargs)
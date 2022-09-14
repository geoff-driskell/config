import appdaemon.plugins.hass.hassapi as hass

#
# App to turn lights on when motion detected then off again after a delay
#
# Use with constraints to activate only for the hours of darkness
#
# Args:
#
# sensor: binary sensor to use as trigger
# entity_on : entity to turn on when detecting motion, can be a light, script, scene or anything else that can be turned on
# entity_off : entity to turn off when detecting motion, can be a light, script or anything else that can be turned off. Can also be a scene which will be turned on
# delay: amount of time after turning on to turn off again. If not specified defaults to 60 seconds.
#
# Release Notes
#
# Version 1.1:
#   Add ability for other apps to cancel the timer
#
# Version 1.0:
#   Initial Version

class OccupancyLights(hass.Hass):
    def initialize(self):
        self.blocker = self.get_entity(self.args["blocker"])
        self.sensor = self.args["sensor"]
        self.light = self.args["light"]
        self.start_morning = self.args["start_morning"]
        self.start_day = self.args["start_day"]
        self.start_evening = self.args["start_evening"]
        self.start_night = self.args["start_night"]
        self.brightness_morning = self.args["brightness_morning"]
        self.brightness_day = self.args["brightness_day"]
        self.brightness_evening = self.args["brightness_evening"]
        self.brightness_night = self.args["brightness_night"]
        # Check some Params

        # Subscribe to sensors
        self.listen_state(self.motion, self.args["sensor"])
        self.log("App completed initialization.", level="INFO")

    def motion(self, entity, attribute, old, new, kwargs):
        if new == "on":
            self.log("Sensor Detected occupancy at {0}.".format(self.time()), level="INFO")
            if self.blocker.is_state("off"):
                self.log("Allowed to continue by state of {0}, searching for a timeslot.".format(self.blocker), level="INFO")
                if self.now_is_between(self.start_morning, self.start_day):
                    self.log("Turning on {0} to morning brightness of {1}".format(self.light, self.brightness_morning), level="INFO")
                    self.turn_on(self.light, brightness_pct=self.brightness_morning)
                if self.now_is_between(self.start_day, self.start_evening):
                    self.log("Turning on {0} to day brightness of {1}".format(self.light, self.brightness_day), level="INFO")
                    self.turn_on(self.light, brightness_pct=self.brightness_day)
                if self.now_is_between(self.start_evening, self.start_night):
                    self.log("Turning on {0} to evening brightness of {1}".format(self.light, self.brightness_evening), level="INFO")
                    self.turn_on(self.light, brightness_pct=self.brightness_day)
                if self.now_is_between(self.start_night, self.start_morning):
                    self.log("Turning on {0} to night brightness of {1}".format(self.light, self.brightness_night), level="INFO")
                    self.turn_on(self.light, brightness_pct=self.brightness_night)
                else:
                    self.log("Did not find a specified time window that {0} fits into, doing nothing.".format(self.time()))
            else:
                self.log("Turning on {0} is currently blocked by {1}, doing nothing.".format(self.light, self.blocker))
        elif new == "off":
            self.log("{0} no longer detects occupancy, turning off {1}.".format(self.sensor, self.light))

            self.turn_off(self.light)
        else:
            self.log("Received an invalid state for new ({0}). Logging and exiting.".format(new), level="ERROR")


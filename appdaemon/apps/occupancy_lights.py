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
        # Check some Params
        self.mode_entity = self.get_entity("input_select.house_mode")
        self.mode = self.get_state("input_select.house_modee")
        self.sensor = self.args["sensor"]
        self.light = self.args["light"]
        self.brightness_morning = self.args["brightness_morning"]
        self.brightness_day = self.args["brightness_day"]
        self.brightness_evening = self.args["brightness_evening"]
        self.brightness_night = self.args["brightness_night"]

        # Subscribe to sensors
        self.listen_state(self.motion, self.args["sensor"])
        self.log("App completed initialization.", level="INFO")

    def motion(self, entity, attribute, old, new, kwargs):
        self.mode = self.get_state("input_select.house_mode")
        if new == "on":
            self.log("{0} detected occupancy at {1}.".format(self.sensor, self.time()), level="INFO")
            if self.mode == "Morning" or self.mode == "Morning Quiet":
                self.log("Turning on {0} to morning brightness of {1}".format(self.light, self.brightness_morning), level="INFO")
                self.turn_on(self.light, brightness_pct=self.brightness_morning)
            if self.mode == "Day":
                self.log("Turning on {0} to day brightness of {1}".format(self.light, self.brightness_day), level="INFO")
                self.turn_on(self.light, brightness_pct=self.brightness_day)
            if self.mode == "Evening":
                self.log("Turning on {0} to evening brightness of {1}".format(self.light, self.brightness_evening), level="INFO")
                self.turn_on(self.light, brightness_pct=self.brightness_day)
            if self.mode == "Night" or self.mode == "Night Quiet":
                self.log("Turning on {0} to night brightness of {1}".format(self.light, self.brightness_night), level="INFO")
                self.turn_on(self.light, brightness_pct=self.brightness_night)
            else:
                self.log("The current house mode ({0}) is invalid, doing nothing.".format(self.mode))
            
        elif new == "off":
            self.log("{0} no longer detects occupancy, turning off {1}.".format(self.sensor, self.light))
            self.turn_off(self.light)
        else:
            self.log("Received an invalid state for new ({0}). Logging and exiting.".format(new), level="ERROR")


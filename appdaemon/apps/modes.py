import appdaemon.plugins.hass.hassapi as hass
#
# App to manage house modes
#
# I manage my automations around the concept of a house mode. Using an automation to set a mode can then be used by other
# Apps to simplify state checking. For instance, if I set the mode to Evening at a certain light level, there is
# no easy way for another app to be sure if that event has occurred in another app. To handle this
# I have defined an input_select called "house_mode". This app sets it to various values depending on the appropriate criteria.
# Other apps can read it to figure out what they should do.
#
# Args:
#
# Since this code is very specific to my setup I haven't bothered with parameters.
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class Modes(hass.Hass):
    def initialize(self):

        # get current mode
        self.mode = self.get_entity("input_select.house_mode")
        # Create some callbacks
        self.listen_state(self.someone_awake, ["input_boolean.geoff_sleeping", "input_boolean.victoria_sleeping"], new = "off", constrain_input_select='input_select.house_mode,Night Quiet')
        self.listen_state(self.parents_awake, "group.parents_sleeping", old = "on", new = "off")
        self.listen_state(self.everyone_awake, "group.sleep_tracker", old = "on", new = "off")
        self.listen_state(self.bathtime, "binary_sensor.kid_bathroom_motion", new="on", constrain_start_time="17:45:00", constrain_input_select="input_select.house_mode,Day")
        self.listen_state(self.kids_sleeping, "binary_sensor.twins_bed", new = "on")
        self.listen_state(self.parents_sleeping, "group.parents_sleeping", old = "off", new = "on")
        self.log("Completed initialization.")

    def someone_awake(self, entity, attribute, old, new, kwargs):
        self.log("{} is awake, start the morning.".format(self.friendly_name(entity)))
        self.morning_quiet()

    def parents_awake(self, entity, attribute, old, new, kwargs):
        self.log("Geoff and Victoria are both awake. We can ditch quiet mode now.")
        self.morning()

    def everyone_awake(self, entity, attribute, old, new, kwargs):
        self.log("Everyone is awake, time to start the day.")
        self.day()
    
    def bathtime(self, entity, attribute, old, new, kwargs):
        self.log("The kids are taking their baths, time to start evening mode.")
        self.evening()

    def kids_sleeping(self, entity, attribute, old, new, kwargs):
        self.log("The kids have gone to bed, start night mode.")
        self.night()

    def parents_sleeping(self, entity, attribute, old, new, kwargs):
        self.log("{} has gone to sleep, start quiet mode.".format(self.friendly_name(entity)))
        self.night_quiet()

    # Main mode functions - set the house up appropriately for the mode in question as well as set the house_mode flag correctly

    def morning_quiet(self):
        # Set the house up for morning in quiet mode
        self.log("Switching mode to Morning - Quiet Mode")
        self.select_option("input_select.house_mode", "Morning Quiet")
        self.fire_event("mode_change", mode = "Morning Quiet")
    
    def morning(self):
        # Set the house up for morning
        self.log("Switching mode to Morning")
        self.select_option("input_select.house_mode", "Morning")
        self.fire_event("mode_change", mode = "Morning")
        self.call_service('notify/notify', title="Mode Change", message="Switching mode to Morning")

    def day(self):
        # Set the house up for daytime
        self.log("Switching mode to Day")
        self.select_option("input_select.house_mode", "Day")
        self.fire_event("mode_change", mode = "Day")
        self.call_service('notify/notify', title="Mode Change", message="Switching mode to Day")

    def evening(self):
        # Set the house up for evening
        self.log("Switching mode to Evening")
        self.select_option("input_select.house_mode", "Evening")
        self.fire_event("mode_change", mode = "Evening")
        self.call_service('notify/notify', title="Mode Change", message="Switching mode to Evening")

    def night(self):
        # set the house up for night mode
        self.log("Switching mode to Night")
        self.select_option("input_select.house_mode", "Night")
        self.fire_event("mode_change", mode = "Night")
        self.call_service('notify/notify', title="Mode Change", message="Switching mode to Night")
    
    def night_quiet(self, quiet=False):
        # Set the house up for night in quiet mode
        self.log("Switching mode to Night - Quiet")
        self.select_option("input_select.house_mode", "Night Quiet")
        self.fire_event("mode_change", mode = "Night Quiet")
from lzma import is_check_supported
import appdaemon.plugins.hass.hassapi as hass
from datetime import timedelta

class Naptime(hass.Hass):
    def initialize(self):
        self.avery_asleep = self.get_entity("input_boolean.avery_naptime")
        self.avery_asleep_timer = None
        self.avery_asleep_datetime = self.get_entity("input_datetime.avery_asleep_since")
        self.avery_sleep_duration = None
        self.benjamin_asleep = self.get_entity("input_boolean.benjamin_naptime")
        self.benjamin_asleep_timer = None
        self.benjamin_asleep_datetime = self.get_entity("input_datetime.benjamin_asleep_since")
        self.benjamin_sleep_duration = None

        self.naptime = self.get_entity("binary_sensor.twins_sleeping")

        self.max_nap_seconds = 10800
        self.max_nap_string = str(timedelta(seconds=self.max_nap_seconds)).split(":")
        self.max_bedtime_seconds = 43200

        self.avery_asleep.listen_state(self.naptime_started, new = "on")
        self.avery_asleep.listen_state(self.avery_awake, new = "off")
        self.benjamin_asleep.listen_state(self.benjamin_awake, new = "off")

    def naptime_started(self, entity, attribute, old, new, kwargs):
        self.log("The twins bedtime automation started.", level = "INFO")
        self.turn_on("input_boolean.twins_asleep")
        # Record Benjamin is napping
        self.turn_on("input_boolean.benjamin_naptime")

        # Set the helpers
        if self.now_is_between("08:00:00", "17:00:00"):
            # this is a nap, set the helper for a nap
            self.turn_on("input_boolean.twins_taking_a_nap")
        else:
            # This is bedtime, set the helper for bedtime
            self.turn_on("input_boolean.twins_down_for_the_night")

        # Record Starting Sleep Time
        self.avery_asleep_datetime.call_service("set_datetime", timestamp=self.get_now_ts())
        self.benjamin_asleep_datetime.call_service("set_datetime", timestamp=self.get_now_ts())

        # Kill the lights
        self.turn_off("light.nursery_ceiling_fan_light")
        self.turn_off("light.averys_bedroom_ceiling_fan_light")
        self.turn_off("switch.averys_bedroom_lamp")
        self.turn_off("switch.attic_main_lights")
        self.turn_off("switch.stairs_lights")
        self.turn_off("light.upstairs_hallway_lights")

        # Start the fans
        self.turn_on("fan.nursery_ceiling_fan", percentage = "75")
        self.turn_on("fan.averys_bedroom_ceiling_fan", percentage = "75")

        # Turn on Benjamin's sound machine
        self.turn_on("switch.twins_sound_machine")
        
    
    def avery_awake(self, entity, attribute, old, new, kwargs):
        #TODO: Calculate the time that Avery slept

        # Log Avery is awake
        if self.now_is_between("00:00:00", "10:00:00"):
            self.log("Avery woke up from bedtime.", level="INFO")
            if self.benjamin_asleep.is_state("on"):
                self.log("Benjamin is still asleep, when he wakes up we will turn off the bedtime helper.", level="INFO")
            else:
                self.log("Benjamin is already awake. Turning off the bedtime helper.", level="INFO")
                self.turn_off("input_boolean.twins_down_for_the_night")
                self.turn_off("input_boolean.twins_asleep")
        else:
            self.log("Avery woke up from her nap.", level="INFO")
            if self.benjamin_asleep.is_state("on"):
                self.log("Benjamin is still asleep, when he wakes up we will turn off the naptime helper.", level="INFO")
            else:
                self.log("Benjamin is already awake. Turning off the naptime helper.", level="INFO")
                self.turn_off("input_boolean.twins_taking_a_nap")
                self.turn_off("input_boolean.twins_asleep")
        
        # Turn off her fan
        self.turn_off("fan.averys_bedroom_ceiling_fan")

        # Turn on her light
        self.turn_on("light.averys_bedroom_ceiling_fan_light", brightness_pct = "15")

    def benjamin_awake(self, entity, attribute, old, new, kwargs):
        #TODO: Calculate the time that Benjamin slept
        
        # Log Benjamin is awake
        if self.now_is_between("00:00:00", "10:00:00"):
            self.log("Benjamin woke up from bedtime.", level="INFO")
            if self.avery_asleep.is_state("on"):
                self.log("Avery is still asleep, when she wakes up we will turn off the bedtime helper.", level="INFO")
            else:
                self.log("Avery is already awake. Turning off the bedtime helper.", level="INFO")
                self.turn_off("input_boolean.twins_down_for_the_night")
                self.turn_off("input_boolean.twins_asleep")
        else:
            self.log("Benjamin woke up from his nap.", level="INFO")
            if self.avery_asleep.is_state("on"):
                self.log("Avery is still asleep, when she wakes up we will turn off the naptime helper.", level="INFO")
            else:
                self.log("Avery is already awake. Turning off the naptime helper.", level="INFO")
                self.turn_off("input_boolean.twins_taking_a_nap")
                self.turn_off("input_boolean.twins_asleep")

        # Turn off his fan
        self.turn_off("fan.nursery_ceiling_fan")

        # Turn off his sound machine
        self.turn_off("switch.twins_sound_machine")

        # Turn on his light
        self.turn_on("light.nursery_ceiling_fan_light", brightness_pct = "15")
    
    def avery_notifier(self, kwargs):
        title = "Avery Naptime"
        message = "Avery has been asleep for {0} Hours {1} Minutes {2} Seconds. She may need to be woken up.".format(self.max_nap_string[0], self.max_nap_string[1], self.max_nap_string[2])
        self.notifier(title, message)

    def benjamin_notifier(self, kwargs):
        title = "Benjamin Naptime"
        message = "Benjamin has been asleep for {0} Hours {1} Minutes {2} Seconds. He may need to be woken up.".format(self.max_nap_string[0], self.max_nap_string[1], self.max_nap_string[2])
        self.notifier(title, message)

    def notifier(self, title, message):
        self.call_service('notify/notify', title=title, message=message)
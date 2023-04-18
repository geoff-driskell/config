"""
Twins Naptime Library
"""
from datetime import timedelta
import appdaemon.plugins.hass.hassapi as hass

class Naptime(hass.Hass):
    """The naptime class."""
    def initialize(self):
        """Initialize naptime."""
        # pylint: disable=attribute-defined-outside-init
        self.avery_asleep = self.get_entity("input_boolean.avery_naptime")
        self.benjamin_asleep = self.get_entity("input_boolean.benjamin_naptime")

        self.naptime = self.get_entity("binary_sensor.twins_sleeping")

        self.max_nap_seconds = 10800
        self.max_nap_string = str(timedelta(seconds=self.max_nap_seconds)).split(":")
        self.max_bedtime_seconds = 43200

        self.avery_asleep.listen_state(self.naptime_started, new = "on")
        self.avery_asleep.listen_state(self.avery_awake, new = "off")
        self.benjamin_asleep.listen_state(self.benjamin_awake, new = "off")
        self.listen_state(self.song_stopped, "media_player.averys_room")

    def naptime_started(self, entity, attribute, old, new, kwargs):
        """Start the twins naptime routine."""
        self.log("The twins bedtime automation started.", level = "INFO")
        self.turn_on("input_boolean.twins_asleep")
        # Record Benjamin is napping
        self.turn_on("input_boolean.benjamin_naptime")

        # Set the helpers
        if self.now_is_between("08:00:00", "17:00:00"):
            # this is a nap, set the helper for a nap
            self.turn_on("input_boolean.twins_taking_a_nap")
            self.set_state("sensor.avery_last_nap_start", state=self.get_now(), attributes={"icon":"mdi:clock", "friendly_name":"Avery Last Nap", "device_class":"timestamp", "unique_id":"cbc0ec4f-652e-47f0-a698-670d6111d8cd"})
            self.set_state("sensor.benjamin_last_nap_start", state=self.get_now(), attributes={"icon":"mdi:clock", "friendly_name":"Benjamin Last Nap", "device_class":"timestamp", "unique_id":"2fa44660-c261-4d73-a0c2-f4868c8885fc"})
        else:
            # This is bedtime, set the helper for bedtime
            self.turn_on("input_boolean.twins_down_for_the_night")
            self.set_state("sensor.avery_last_bed_start", state=self.get_now(), attributes={"icon":"mdi:clock", "friendly_name":"Avery Last Bed", "device_class":"timestamp", "unique_id":"944b332b-7bc4-40ad-815b-675dd1ad8ba6"})
            self.set_state("sensor.benjamin_last_bed_start", state=self.get_now(), attributes={"icon":"mdi:clock", "friendly_name":"Benjamin Last Bed", "device_class":"timestamp", "unique_id":"3e32011b-bca5-408e-b767-9b1a9d67813a"})

        # Kill the lights
        self.turn_off("light.nursery_ceiling_fan_light")
        self.turn_off("light.averys_bedroom_ceiling_fan_light")
        self.turn_off("switch.averys_bedroom_lamp")
        self.turn_off("switch.attic_main_lights")
        self.turn_off("switch.stairs_lights")
        self.turn_off("light.upstairs_hallway_lights")
        self.turn_off("light.loft_lamp")
        self.turn_off("light.loft_lights")

        # Start the fans
        self.turn_on("fan.nursery_ceiling_fan", percentage = "75")
        self.turn_on("fan.averys_bedroom_ceiling_fan", percentage = "75")

        # Turn on Benjamin's sound machine
        self.turn_on("switch.twins_sound_machine")
        
        self.set_state("binary_sensor.play_against_the_wind", state="on", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})
    
    def avery_awake(self, entity, attribute, old, new, kwargs):
        """Handle Avery waking up."""
        # Log Avery is awake
        if self.now_is_between("00:00:00", "10:00:00"):
            self.log("Avery woke up from bedtime.", level="INFO")
            if self.get_state("input_boolean.benjamin_naptime") == "on":
                self.log("Benjamin is still asleep, when he wakes up we will turn off the bedtime helper.", level="INFO")
            else:
                self.log("Benjamin is already awake. Turning off the bedtime helper.", level="INFO")
                self.turn_off("input_boolean.twins_down_for_the_night")
                self.turn_off("input_boolean.twins_asleep")
                self.set_state("binary_sensor.play_against_the_wind", state="off", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})
        else:
            self.log("Avery woke up from her nap.", level="INFO")
            if self.get_state("input_boolean.benjamin_naptime") == "on":
                self.log("Benjamin is still asleep, when he wakes up we will turn off the naptime helper.", level="INFO")
            else:
                self.log("Benjamin is already awake. Turning off the naptime helper.", level="INFO")
                self.turn_off("input_boolean.twins_taking_a_nap")
                self.turn_off("input_boolean.twins_asleep")
                self.set_state("binary_sensor.play_against_the_wind", state="off", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})
        
        # Turn off her fan
        self.turn_off("fan.averys_bedroom_ceiling_fan")

        # Turn on her light
        if self.get_state("light.averys_bedroom_ceiling_fan_light") == "on":
            self.log("Avery's light is already on, I'm not going to change it.")
        else:
            self.log("Turning on Avery's light.")
            self.turn_on("light.averys_bedroom_ceiling_fan_light", brightness_pct = "15")

    def benjamin_awake(self, entity, attribute, old, new, kwargs):
        """Handle Benjamin waking up."""
        # Log Benjamin is awake
        if self.now_is_between("00:00:00", "10:00:00"):
            self.log("Benjamin woke up from bedtime.", level="INFO")
            if self.get_state("input_boolean.avery_naptime") == "on":
                self.log("Avery is still asleep, when she wakes up we will turn off the bedtime helper.", level="INFO")
            else:
                self.log("Avery is already awake. Turning off the bedtime helper.", level="INFO")
                self.turn_off("input_boolean.twins_down_for_the_night")
                self.turn_off("input_boolean.twins_asleep")
                self.set_state("binary_sensor.play_against_the_wind", state="off", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})
        else:
            self.log("Benjamin woke up from his nap.", level="INFO")
            if self.get_state("input_boolean.avery_naptime") == "on":
                self.log("Avery is still asleep, when she wakes up we will turn off the naptime helper.", level="INFO")
            else:
                self.log("Avery is already awake. Turning off the naptime helper.", level="INFO")
                self.turn_off("input_boolean.twins_taking_a_nap")
                self.turn_off("input_boolean.twins_asleep")
                self.set_state("binary_sensor.play_against_the_wind", state="off", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})

        # Turn off his fan
        self.turn_off("fan.nursery_ceiling_fan")

        # Turn off his sound machine
        self.turn_off("switch.twins_sound_machine")

        # Turn on his light
        if self.get_state("light.nursery_ceiling_fan_light") == "on":
            self.log("Benjamin's light is already on, I'm not going to change it.")
        else:
            self.log("Turning benjamin's light on.")
            self.turn_on("light.nursery_ceiling_fan_light", brightness_pct = "15")

    def song_stopped(self, entity, attribute, old, new, kwargs):
        if self.get_state("media_player.averys_room") == "paused" or self.get_state("media_player.averys_room") == "idle":
            if self.get_state("binary_sensor.twins_sleeping") == "on":
                self.set_state("binary_sensor.play_against_the_wind", state="off", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})
                self.run_in(self.restart_song, 1)

    def restart_song(self, kwargs):
        self.set_state("binary_sensor.play_against_the_wind", state="on", attributes={"icon":"mdi:music", "friendly_name":"Play Against The Wind", "unique_id":"f6f40b67-264f-48e9-ad79-d42035761b23"})
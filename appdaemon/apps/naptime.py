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
        # Record Benjamin is napping
        self.turn_on("input_boolean.benjamin_naptime")

        # Start the timers
        if self.now_is_between("08:00:00", "17:00:00"):
            # this is a nap, set a timer for a nap
            self.avery_asleep_timer = self.run_in(self.avery_notifier, self.max_nap_seconds)
            self.benjamin_asleep_timer = self.run_in(self.benjamin_notifier, self.max_nap_seconds)
        # else:
        #     # This is bedtime, set a bedtime timer
        #     self.benjamin_asleep_timer = self.run_in(self.benjamin_notifier, self.max_bedtime_seconds)
        #     self.avery_asleep_timer = self.run_in(self.avery_notifier, self.max_bedtime_seconds)

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
        # Log Avery is awake
        self.log("Avery is awake.", level="INFO")

        # Cancel running sleep timer
        if self.timer_running(self.avery_asleep_timer):
            self.cancel_timer(self.avery_asleep_timer)
        
        # Turn off her fan
        self.turn_off("fan.averys_bedroom_ceiling_fan")

        # Turn on her light
        self.turn_on("light.averys_bedroom_ceiling_fan_light", brightness_pct = "15")

        
        self.log("Avery asleep since {0}.".format(self.parse_time(self.avery_asleep_datetime.get_state())), level="INFO")

    def benjamin_awake(self, entity, attribute, old, new, kwargs):
        self.log("Benjamin is awake.", level="INFO")
        if self.timer_running(self.benjamin_asleep_timer):
            self.cancel_timer(self.benjamin_asleep_timer)
        self.turn_off("fan.nursery_ceiling_fan")
        self.turn_off("switch.twins_sound_machine")
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
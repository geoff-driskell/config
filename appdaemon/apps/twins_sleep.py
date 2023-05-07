"""
Twins Naptime Library
"""

import time
import threading
import appdaemon.plugins.hass.hassapi as hass

class Naptime(hass.Hass):
    """The nap time class."""
    def initialize(self):
        """Initialize nap time."""
        # pylint: disable=attribute-defined-outside-init

        # get a real dict for the configuration
        self.args = dict(self.args)

        self.action_lock = threading.RLock()
        for entity in self.list_entities():
            self.listen_state(self.state_event, entity, immediate=True, constrain_input_boolean="input_boolean.grace_period,off")
        
        self.listen_state(self.start_sleep, "input_boolean.start_twins_sleeping", new = "on")
        self.listen_state(self.end_sleep, "input_boolean.wake_up_both_kids", new = "on")
        self.listen_state(self.wake_avery, "input_boolean.wake_up_avery", new = "on")
        self.listen_state(self.wake_benjamin, "input_boolean.wake_up_benjamin", new = "on")
        self.listen_state(self.stop_song, "sensor.twins_sleep_state", new="awake")

        self.twins_sleep_state = self.get_entity("sensor.twins_sleep_state")
        self.song_monitor = self.listen_state(self.media_player_paused, ["media_player.averys_room", "media_player.benjamins_room"], new = "paused", constrain_input_boolean="input_boolean.avery_naptime,on")
        self.song_monitor = self.listen_state(self.media_player_idle, ["media_player.averys_room", "media_player.benjamins_room"], new = "idle", constrain_input_boolean="input_boolean.avery_naptime,on")

    def state_event(self, entity, attribute, old, new, kwargs):
        """Handles entities changing state"""
        ha_entity = self.get_entity(entity)
        sleeping = False
        zone_list = []

        if "sleep_entity" in self.args:
            state = self.get_state(self.args["sleep_entity"])

            if state != "awake":
                if self.get_state("input_boolean.avery_naptime") == "on":
                    zone_list.append("Avery Room")
                if self.get_state("input_boolean.benjamin_naptime"):
                    zone_list.append("Benjamin Room")
                sleeping = True

        if sleeping:
            entities = {key: value for (key, value) in self.filter_entities(zone_list)}
            if entity in entities and old in entities[entity][state]["desired_state"]:
                self.log(f"Alert - {ha_entity.friendly_name} has changed to {new}, it should be {old} while the kids are sleeping.")
                # if "service" in entities[entity][state]:
                #     service = entities[entity][state]["service"]
                #     self.log(f"Alert - attempting to fix the issue by calling {service} on {ha_entity.friendly_name}.")
                #     self.call_service(service, entity_id=entity, **entities[entity][state]["parameters"])
                

                # if "critical" in "entity":
                # self.call_service('notify/notify', title="Twins Sleep Issue", message=f"{ha_entity.friendly_name} has changed to {new}, it should be {old}.")


    def start_sleep(self, entity, attribute, old, new, kwargs):
        """Start the sleep routine"""
        self.call_service("input_boolean/turn_on", entity_id="input_boolean.grace_period")
        self.run_in(self.end_grace_period, 30)
        if self.now_is_between("09:00:00", "17:00:00"):
            if "sleep_entity" in self.args:
                self.set_state(self.args["sleep_entity"], state="nap")
            self.handle_sleep("nap")
        else:
            if "sleep_entity" in self.args:
                self.set_state(self.args["sleep_entity"], state="bed")
            self.handle_sleep("bed")

    def end_grace_period(self, kwargs):
        self.call_service("input_boolean/turn_off", entity_id="input_boolean.grace_period")

    def handle_sleep(self, action):
        """Get the items in the correct state"""
        # pylint: disable=attribute-defined-outside-init
        self.timeout = 0
        compliant_items = []
        non_compliant_items = []
        self.compliant_items = []
        self.non_compliant_items = []
        self.attempted_items = []

        self.action = action

        zone_list = []
        if action == "nap":
            zone_list = self.args["nap_zones"]
            mode = "nap"
        elif action == "bed":
            zone_list = self.args["bed_zones"]
            mode = "bed"
        elif action == "awake":
            zone_list = self.args["awake_zones"]
            mode = "awake"
        elif action == "avery_awake":
            zone_list = self.args["avery_zones"]
            mode = "awake"
        elif action == "ben_awake":
            zone_list = self.args["ben_zones"]
            mode = "awake"

        # Figure out what items are compliant vs non-compliant
        for id, values in self.filter_entities(zone_list):
            desired_state = values[mode]["desired_state"]
            state = self.get_state(id)
            if state != desired_state:
                non_compliant_items.append(id)
            else:
                compliant_items.append(id)
        if not non_compliant_items:
            # All items in desired state, notify the user
            self.log("All items were in desired state, suspect duplicate call.", level="INFO")
        else:
            self.log("Checking items ...")
            for id in non_compliant_items:
                entity = self.find_entity(id)
                self.log(f"{id}")
                if "timeout" in entity and entity["timeout"] > self.timeout:
                    self.timeout = entity["timeout"]
                
                desired_state = entity[mode]["desired_state"]
                if "service" in entity[mode]:
                    service = entity[mode]["service"]
                    self.log(f"Calling {service} on {id}.")
                    self.attempted_items.append(id)
                    self.listen_state(self.state_change, id, new=desired_state)
                    self.call_service(service, entity_id=id, **entity[mode]["parameters"])
                    self.compliant_items.append(id)
                else:
                    self.non_compliant_items.append(id)

        self.retry = 0

        complete = False
        while self.retry < self.timeout and not complete:
            time.sleep(1)
            with self.action_lock:
                if not self.attempted_items:
                    complete = True
            self.retry += 1

        return len(self.non_compliant_items) != 0
    
    def state_change(self, entity, attribute, old, new, kwargs):
        """Handle state changes of entities"""
        with self.action_lock:
            if entity in self.attempted_items:
                self.attempted_items.remove(entity)

    def end_sleep(self, entity, attribute, old, new, kwargs):
        """End the sleep routine"""
        self.handle_sleep("awake")

    def wake_avery(self, entity, attribute, old, new, kwargs):
        """Wake just Avery"""
        self.handle_sleep("avery_awake")

    def wake_benjamin(self, entity, attribute, old, new, kwargs):
        """Wake just Benjamin"""
        self.handle_sleep("ben_awake")

    def media_player_paused(self, entity, attribute, old, new, kwargs):
        """Resume the song"""
        self.call_service("media_player/media_play", entity_id=entity)

    def media_player_idle(self, entity, attribute, old, new, kwargs):
        """Resume the song"""
        self.call_service("input_boolean/turn_off", entity_id="input_boolean.play_sleep_song")
        time.sleep(0.5)

    def stop_song(self, entity, attribute, old, new, kwargs):
        """Stop the song if both are awake individually."""
        self.call_service("input_boolean/turn_off", entity_id="input_boolean.play_sleep_song")
        self.call_service("input_boolean/turn_off", entity_id="input_boolean.twins_down_for_the_night")
        

    def filter_entities(self, zone_list):
        """Filter entities to the desired zone_list"""
        for zone in self.args["zones"]:
            if zone in zone_list:
                for entity in self.args["zones"][zone]:
                    yield entity, self.args["zones"][zone][entity]

    def find_entity(self, id):
        """Find a particular entity"""
        for zone in self.args["zones"]:
            for entity in self.args["zones"][zone]:
                if entity == id:
                    return self.args["zones"][zone][entity]
        return None

    def list_entities(self):
        """List all entities."""
        entities = []
        for zone in self.args["zones"]:
            for entity in self.args["zones"][zone]:
                entities.append(entity)
        return entities

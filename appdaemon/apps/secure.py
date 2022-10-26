"""
App to manage check and action security
"""
import threading
import time
import random
import re
import appdaemon.plugins.hass.hassapi as hass

class Secure(hass.Hass):
    """Secure class."""
    def initialize(self):
        """Initialize the class."""
        # pylint: disable=attribute-defined-outside-init
        self.action_lock = threading.RLock()

    def filter_entities(self, zonelist):
        """Filter entities."""
        # pylint: disable=attribute-defined-outside-init
        for zone in self.args["zones"]:
            if zone in zonelist:
                for entity in self.args["zones"][zone]:
                    yield entity, self.args["zones"][zone][entity]

    def find_entity(self, item_id):
        """Find entity."""
        # pylint: disable=attribute-defined-outside-init
        for zone in self.args["zones"]:
            for entity in self.args["zones"][zone]:
                if entity == item_id:
                    return self.args["zones"][zone][entity]
        return None

    def list_entities(self):
        """List entities."""
        # pylint: disable=attribute-defined-outside-init
        entities = []
        for zone in self.args["zones"]:
            for entity in self.args["zones"][zone]:
                entities.append(entity)
        return entities

    def query_house(self, data):  # noqa: C901
        """Query the house."""
        # pylint: disable=attribute-defined-outside-init
        self.timeout = 0
        secure_items = []
        insecure_items = []
        self.secured_items = []
        self.unsecured_items = []
        self.attempted_items = []

        self.data = data

        zone_list: list = self.args["query_zones"]

        # Figure out which items are secure vs insecure
        for item_id, values in self.filter_entities(zone_list):
            desired_state = values["desired_state"]
            state = self.get_state(item_id)
            if state != desired_state:
                insecure_items.append(item_id)
            else:
                secure_items.append(item_id)
        if not insecure_items:
            # All secure, tell the user
            message = self.report(False)

            if "caller" not in data:
                self.tts_log(message, self.args["announcement_volume"], 10)

            return False, message
        else:

            self.log("Checking items ...")
            for item_id in insecure_items:

                entity = self.find_entity(item_id)
                if "timeout" in entity and entity["timeout"] > self.timeout:
                    self.timeout = entity["timeout"]

                desired_state = entity["desired_state"]
                if "service" in entity and data["type"] == "secure":
                    service = entity["service"]
                    self.log(f"Calling {service} -> {desired_state} on {item_id}.")
                    self.attempted_items.append(item_id)
                    self.listen_state(self.state_change, item_id, new=desired_state)
                    self.call_service(service, entity_id=item_id)
                    self.secured_items.append(item_id)
                else:
                    self.unsecured_items.append(item_id)

            self.retry = 0
            # self.handle = self.run_every(self.check_actions, self.datetime(), 1)

            #
            # Wait until all actions complete or timeout occurs
            #
            complete = False
            while self.retry < self.timeout and not complete:
                time.sleep(1)
                with self.action_lock:
                    if not self.attempted_items:
                        complete = True
                self.retry += 1

            message = self.report()

            if "caller" not in data:
                self.tts_log(message, self.args["announcement_volume"], 10)

            return len(self.unsecured_items) != 0, message

    def state_change(self, entity, attribute, old, new, kwargs):
        """State changed."""
        # pylint: disable=attribute-defined-outside-init
        with self.action_lock:
            if entity in self.attempted_items:
                self.attempted_items.remove(entity)

    def get_message(self, message_type):
        """Get the message."""
        # pylint: disable=attribute-defined-outside-init
        if message_type in self.data:
            messages = self.data[message_type]
        elif message_type in self.args:
            messages = self.args[message_type]
        else:
            messages = "Unknown message"

        if isinstance(messages, list):
            return random.choice(messages)
        else:
            return messages

    def report(self, all_secure=False):
        """Report to user."""
        # pylint: disable=attribute-defined-outside-init
        if all_secure:

            return self.get_message("secure_message")

        secured_items = self.secured_items
        unsecured_items = self.unsecured_items

        # Lets work out what to say
        secured_items_list = ""
        for item in secured_items:
            if item not in self.attempted_items:
                entity = self.find_entity(item)
                if "state_map" in entity:
                    state = entity["state_map"][self.get_state(item)]
                else:
                    state = self.get_state(item)
                name = self.friendly_name(item)
                secured_items_list += f" {name} is {state}, "

        unsecured_items_list = ""
        for item in unsecured_items:
            entity = self.find_entity(item)
            if "state_map" in entity:
                state = entity["state_map"][self.get_state(item)]
            else:
                state = self.get_state(item)
            name = self.friendly_name(item)
            unsecured_items_list += f" {name} is {state}, "

        failed_items_list = ""
        for item in self.attempted_items:
            entity = self.find_entity(item)
            if "state_map" in entity:
                state = entity["state_map"][self.get_state(item)]
            else:
                state = self.get_state(item)
            name = self.friendly_name(item)
            failed_items_list += f" {name} is {state}, "

        message = ""
        if unsecured_items_list != "":
            message += self.get_message("insecure_message")
            message += unsecured_items_list

        if secured_items_list != "":
            message += self.get_message("securing_message")
            message += " " + secured_items_list

        if failed_items_list != "":
            message += self.get_message("failed_message")
            message += " " + failed_items_list

        if unsecured_items_list == "" and failed_items_list == "":
            message += self.get_message("secure_message")
            if self.data["type"] in ["alarm_arm_home", "alarm_arm_away"]:
                message += ". " + self.get_message("alarm_arm_message")
        else:
            message += self.get_message("not_secure_message")
            if self.data["type"] in ["alarm_arm_home", "alarm_arm_away"]:
                message += ". " + self.get_message("alarm_cancel_message")

        # Clean up the message
        message = re.sub(r"^\s+", "", message)
        message = re.sub(r"\s+$", "", message)
        message = re.sub(r"\s+", " ", message)

        return message

    def tts_log(self, message, volume, duration):
        """Log and speak."""
        # pylint: disable=attribute-defined-outside-init
        self.log(message)
        sound = self.get_app("kitchen_sound")
        sound.tts(message, volume, duration)

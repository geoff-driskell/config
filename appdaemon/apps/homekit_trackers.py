"""
App to create device tracker from HomeKit home/away
"""
from typing import Any, Coroutine
import appdaemon.plugins.hass.hassapi as hass

class HomeKitTracker(hass.Hass):
    """Class to create tracker"""
    def initialize(self):
        """The constructor"""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)
        self.trackers = self.args.get("trackers", None)

        listener: set[Coroutine[Any, Any, Any]] = set()
        for tracker in self.trackers:
            listener.add(
                self.listen_state(
                self.homekit_update,
                entity_id=tracker
                )
            )

    def homekit_update(self, entity, attribute, old, new, kwargs):
        """Handle updates from homekit presence automation"""
        self.log(f"Entity:{entity} Attribute:{attribute} Old:{old} New:{new} kwargs:{kwargs}")
        tracker_name = entity.split('.')[1].split('_')[0]
        device_id = f"homekit_{tracker_name}"
        if new == "on":
            location_name = 'home'
        else:
            location_name = 'not_home'
        self.log(f"Device id: {device_id}, Location Name: {location_name}")
        self.call_service("device_tracker/see", dev_id=device_id, location_name=location_name)

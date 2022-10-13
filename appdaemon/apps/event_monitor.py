"""

Monitor events and output changes to verbose_log. Nice for debugging purposes.

Arguments:
 - events: List of events to monitor

"""

from typing import Any
import appdaemon.plugins.hass.hassapi as hass

class Monitor(hass.Hass):
    """Class to monitor event types."""
    def initialize(self):
        """Setup the app."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        events = self.args.get("events", None)

        for event in events:
            self.changed(event, None, None, None, None)
            self.log(f"Watching event {event} for state changes.")
            self.listen_state(self.changed, event)

    def changed(self, entity, attribute, old, new, kwargs):
        """Log the event changes."""
        value = self.get_state(entity, "all")
        self.log(entity + ": " + str(value))

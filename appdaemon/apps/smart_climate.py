"""
App to manage heating and cooling.
- Turn on only if someone is present
- Stay on all day as long as someone is present
- Turn off if everyone leaves
"""
from typing import Any, cast
from datetime import datetime, time, date, timedelta
import appdaemon.plugins.hass.hassapi as hass

class SmartClimate(hass.Hass):
    """Smart climate control class"""
    def initialize(self):
        """Initialize the class"""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)
        self.thermostats: set[str] = self.args.get("thermostats", "ERROR")
        evening: time = cast(time, self.parse_time(self.args.get('evening_on', "14:30:00")))
        self.run_every_weekday(self.evening, evening)

    def run_every_weekday(self, callback, start, **kwargs):
        WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        handle = []
        upcoming_weekdays = []

        today = cast(date, self.date())
        todays_event = datetime.combine(today, start)

        if todays_event > cast(datetime, self.datetime()):
            if today.strftime('%A') in WEEKDAYS:
                upcoming_weekdays.append(today)

        for day_number in range(1, 8):
            day = today + timedelta(days=day_number)
            if day.strftime('%A') in WEEKDAYS:
                if len(upcoming_weekdays) < 5:
                    upcoming_weekdays.append(day)

        for day in upcoming_weekdays:
            event = datetime.combine(day, start)
            handle.append(self.run_every(callback, event, 604800, **kwargs))

        return handle
    
    def evening(self, kwargs):
        """If noone is home in the evening turn climate on in preparation."""
        self.log("Evening climate check")
        if self.noone_home(person=True):
            self.climate_on()
    
    def climate_on(self):
        if self.state == "off":
            self.state = "on"
            self.log("Turning climate on.")
            for thermostat in self.thermostats:
                self.call_service("climate/set_temperature", entity_id=thermostat, temer)

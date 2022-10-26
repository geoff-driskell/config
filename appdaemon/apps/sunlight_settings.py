"""Track the state of the sun and associated light settings."""
from __future__ import annotations
from bisect import bisect
import datetime
from datetime import timedelta
import logging
from collections.abc import Callable
from typing import Any, cast
from astral import sun
from astral.location import Elevation, Location, LocationInfo
import appdaemon.plugins.hass.hassapi as hass


_ORDER = ("sunrise", "noon", "sunset", "midnight")
_ALLOWED_ORDERS = {_ORDER[i:] + _ORDER[:i] for i in range(len(_ORDER))}

_AstralSunEventCallable = Callable[..., datetime.datetime]

STATE_ABOVE_HORIZON = "above_horizon"
STATE_BELOW_HORIZON = "below_horizon"

STATE_ATTR_AZIMUTH = "azimuth"
STATE_ATTR_ELEVATION = "elevation"
STATE_ATTR_RISING = "rising"
STATE_ATTR_NEXT_DAWN = "next_dawn"
STATE_ATTR_NEXT_DUSK = "next_dusk"
STATE_ATTR_NEXT_MIDNIGHT = "next_midnight"
STATE_ATTR_NEXT_NOON = "next_noon"
STATE_ATTR_NEXT_RISING = "next_rising"
STATE_ATTR_NEXT_SETTING = "next_setting"

# The algorithm used here is somewhat complicated. It aims to cut down
# the number of sensor updates over the day. It's documented best in
# the PR for the change, see the Discussion section of:
# https://github.com/home-assistant/core/pull/23832


# As documented in wikipedia: https://en.wikipedia.org/wiki/Twilight
# sun is:
# < -18° of horizon - all stars visible
PHASE_NIGHT = "night"
# 18°-12° - some stars not visible
PHASE_ASTRONOMICAL_TWILIGHT = "astronomical_twilight"
# 12°-6° - horizon visible
PHASE_NAUTICAL_TWILIGHT = "nautical_twilight"
# 6°-0° - objects visible
PHASE_TWILIGHT = "twilight"
# 0°-10° above horizon, sun low on horizon
PHASE_SMALL_DAY = "small_day"
# > 10° above horizon
PHASE_DAY = "day"

# 4 mins is one degree of arc change of the sun on its circle.
# During the night and the middle of the day we don't update
# that much since it's not important.
_PHASE_UPDATES = {
    PHASE_NIGHT: timedelta(minutes=4 * 5),
    PHASE_ASTRONOMICAL_TWILIGHT: timedelta(minutes=4 * 2),
    PHASE_NAUTICAL_TWILIGHT: timedelta(minutes=4 * 2),
    PHASE_TWILIGHT: timedelta(minutes=4),
    PHASE_SMALL_DAY: timedelta(minutes=2),
    PHASE_DAY: timedelta(minutes=4),
}


class CircadianBrightness(hass.Hass):
    """Support for functionality to keep track of the sun."""

    location: Location = Location(
        LocationInfo(*("", "", "America/New_York", 37.65525, -77.41344))
    )
    elevation: Elevation = 170

    def initialize(self):
        """Initialize the sun."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.phase: str
        self.args: dict[str, Any] = dict(self.args)
        self.max_brightness_pct: int = self.args.get("max_brightness_pct", 255)
        self.min_brightness_pct: int = self.args.get("min_brightness_pct", 0)
        self.sleep_brightness_pct: int = self.args.get("sleep_brightness_pct", 8)
        self.transition: int | None = self.args.get("transition", None)
        self.sun_pct: float = 0
        self.log("mostly completed init.")
        self.update_sun_position()
        self.log("completed init.")

    @property
    def state(self) -> float:
        """Return the circadian brightness."""
        return 100.0

    def get_location_astral_event_next(
        self,
        location: Location,
        elevation: Elevation,
        event: str,
        point_in_time: datetime.datetime | None = None,
        offset: datetime.timedelta | None = None
    ) -> datetime.datetime:
        """Calculate the next specified solar event."""
        if offset is None:
            offset = datetime.timedelta()
        if point_in_time is None:
            point_in_time = cast(datetime.datetime, self.get_now())
        kwargs: dict[str, Any] = {"local": True}
        
        mod = -1
        while True:
            try:
                next_dt = (
                    cast(_AstralSunEventCallable, getattr(location, event))(
                        point_in_time.date() + datetime.timedelta(days=mod),
                        **kwargs
                    )
                    + offset
                )
                if next_dt > point_in_time:
                    return point_in_time
            except ValueError:
                pass
            mod += 1
    
    def _check_event(self, point_in_time: datetime.datetime, sun_event: str, before: str | None) -> datetime.datetime:
        next_time = self.get_location_astral_event_next(
            self.location, self.elevation, sun_event, point_in_time
        )
        if next_time < self._next_change:
            self._next_change = next_time
            self.phase = before
        return next_time

    def update_events(self) -> None:
        """Update the solar events."""
        point_in_time = cast(datetime.datetime, self.get_now())
        self._next_change = point_in_time + timedelta(days=400)

        # Work our way around the solar cycle, figure out the next
        # phase. Some of these are stored.
        self.location.solar_depression = "astronomical"
        self._check_event(point_in_time, "dawn", PHASE_NIGHT)
        self.location.solar_depression = "nautical"
        self._check_event(point_in_time, "dawn", PHASE_ASTRONOMICAL_TWILIGHT)
        self.location.solar_depression = "civil"
        self.next_dawn = self._check_event(
            point_in_time, "dawn", PHASE_NAUTICAL_TWILIGHT
        )
        self.next_rising = self._check_event(
            point_in_time, SUN_EVENT_SUNRISE, PHASE_TWILIGHT
        )
        self.location.solar_depression = -10
        self._check_event(point_in_time, "dawn", PHASE_SMALL_DAY)
        self.next_noon = self._check_event(point_in_time, "noon", None)
        self._check_event(point_in_time, "dusk", PHASE_DAY)
        self.next_setting = self._check_event(
            point_in_time, SUN_EVENT_SUNSET, PHASE_SMALL_DAY
        )
        self.location.solar_depression = "civil"
        self.next_dusk = self._check_event(point_in_time, "dusk", PHASE_TWILIGHT)
        self.location.solar_depression = "nautical"
        self._check_event(point_in_time, "dusk", PHASE_NAUTICAL_TWILIGHT)
        self.location.solar_depression = "astronomical"
        self._check_event(point_in_time, "dusk", PHASE_ASTRONOMICAL_TWILIGHT)
        self.next_midnight = self._check_event(point_in_time, "midnight", None)
        self.location.solar_depression = "civil"

        # if the event was solar midday or midnight, phase will now
        # be None. Solar noon doesn't always happen when the sun is
        # even in the day at the poles, so we can't rely on it.
        # Need to calculate phase if next is noon or midnight
        if self.phase is None:
            elevation = self.location.solar_elevation(self._next_change, self.elevation)
            if elevation >= 10:
                self.phase = PHASE_DAY
            elif elevation >= 0:
                self.phase = PHASE_SMALL_DAY
            elif elevation >= -6:
                self.phase = PHASE_TWILIGHT
            elif elevation >= -12:
                self.phase = PHASE_NAUTICAL_TWILIGHT
            elif elevation >= -18:
                self.phase = PHASE_ASTRONOMICAL_TWILIGHT
            else:
                self.phase = PHASE_NIGHT

        self.rising = self.next_noon < self.next_midnight

        self.log(f"sun phase_update@{point_in_time.isoformat()}: phase={self.phase}")
        self.update_sun_position()

        # Set timer for the next solar event
        self._update_events_listener = self.run_at(self.update_events, self._next_change)
        
        self.log(f"next time: {self._next_change.isoformat()}")

    def get_sun_events(self, date: datetime.datetime) -> dict[str, float]:
        """Get the four sun event's timestamps at 'date'."""
        sunrise: datetime.datetime = self.location.sunrise(date=date, local=True)
        sunset: datetime.datetime = self.location.sunset(date=date, local=True)
        noon: datetime.datetime = self.location.noon(date=date, local=True)
        midnight: datetime.datetime = self.location.midnight(date=date, local=True)

        events = {
            "sunrise": sunrise.timestamp(),
            "sunset": sunset.timestamp(),
            "noon": noon.timestamp(),
            "midnight": midnight.timestamp(),
        }
        self.log(events)
        return events

    def update_sun_position(self) -> None:
        """Calculate the position of the sun."""
        # pylint: disable=attribute-defined-outside-init
        #grab the current time
        point_in_time: datetime.datetime = cast(datetime.datetime, self.get_now())
        self.solar_azimuth = round(
            self.location.solar_azimuth(point_in_time, self.elevation), 2
        )
        self.log(f"Your location's solar azimuth is {self.solar_azimuth}.")
        self.solar_elevation = round(
            self.location.solar_elevation(point_in_time, self.elevation), 2
        )
        self.log(f"Your location's solar elevation is {self.solar_elevation}.")

        assert self.phase
        delta = _PHASE_UPDATES[self.phase]
        if point_in_time + delta * 1.25 > self._next_change:
            self.

    def relevant_events(self, now: datetime.datetime) -> dict[str, float]:
        """Get the previous and next sun event."""
        events = []
        for days in [-1, 0, 1]:
            for event, timestamp in self.get_sun_events(
                now + timedelta(days=days)
            ).items():
                event_tuple = (event, timestamp)
                events += event_tuple
        events = sorted(events, key=lambda x: x[1])
        index_now = bisect([ts for _, ts in events], now.timestamp())
        return dict(events[index_now - 2 : index_now + 2])

    def calc_percent(self) -> float:
        """Calculate the position of the sun in %."""
        now = cast(datetime.datetime, self.get_now())
        now_ts = now.timestamp()
        today = self.relevant_events(now=now)
        self.log(today)

        if today["sunrise"] < now_ts < today["sunset"]:
            h: float = today["noon"]  # pylint: disable=invalid-name
            x: float = (  # pylint: disable=invalid-name
                today["sunrise"] if now_ts < today["noon"] else today["sunset"]
            )
            a = (-100) / (h - x) ** 2 # pylint: disable=invalid-name
            percentage: float = a * (now_ts - h) ** 2 + 100
            self.log(percentage)
            return percentage
        elif today["sunset"] < now_ts < today["sunrise"]:
            h: float = today["midnight"]  # pylint: disable=invalid-name
            x: float = (  # pylint: disable=invalid-name
                today["sunset"] if now_ts < today["midnight"] else today["sunrise"]
            )
            a = (100) / (h - x) ** 2 # pylint: disable=invalid-name
            percentage: float = a * (now_ts - h) ** 2 - 100
            self.log(percentage)
            return percentage
        else:
            return 100.0

    def calculate_brightness_pct(self, percent: float, is_sleep: bool) -> int:
        """Calculate the brightness in %."""
        if is_sleep:
            return self.sleep_brightness_pct
        if percent > 0:
            return self.max_brightness_pct
        delta_brightness = self.max_brightness_pct - self.min_brightness_pct
        percent = (100 + self.sun_pct) / 100
        return int((delta_brightness * percent) + self.min_brightness_pct)

    def get_settings(self, is_sleep: bool):
        """Get all light settings."""
        percent = self.calc_percent()
        brightness_pct = self.calculate_brightness_pct(
            percent=percent, is_sleep=is_sleep
        )
        return {
            "brightness_pct": brightness_pct,
            "sun_position": percent,
        }

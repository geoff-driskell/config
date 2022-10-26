"""Support for functionality to keep track of the sun."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Coroutine, cast

from astral.location import Elevation, Location
import appdaemon.adbase as ad


CALLBACK_TYPE = Callable[[], None]  # pylint: disable=invalid-name
COROUTINE_TYPE = Coroutine[Any, Any, str]  # pylint: disable=invalid-name
_AstralSunEventCallable = Callable[..., datetime]

ELEVATION_AGNOSTIC_EVENTS = ("noon", "midnight")

ENTITY_ID = "sun.sun"

STATE_ABOVE_HORIZON = "above_horizon"
STATE_BELOW_HORIZON = "below_horizon"

SUN_EVENT_SUNRISE = "sunrise"
SUN_EVENT_SUNSET = "sunset"
SUN_EVENT_NOON = "noon"
SUN_EVENT_MIDNIGHT = "midnight"

STATE_ATTR_AZIMUTH = "azimuth"
STATE_ATTR_ELEVATION = "elevation"
STATE_ATTR_RISING = "rising"
STATE_ATTR_NEXT_DAWN = "next_dawn"
STATE_ATTR_NEXT_DUSK = "next_dusk"
STATE_ATTR_NEXT_MIDNIGHT = "next_midnight"
STATE_ATTR_NEXT_NOON = "next_noon"
STATE_ATTR_NEXT_RISING = "next_rising"
STATE_ATTR_NEXT_SETTING = "next_setting"
STATE_ATTR_PERCENTAGE = "percentage"

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


class Sun(ad.ADBase):
    """Representation of the Sun."""

    _attr_name = "Sun"
    entity_id = ENTITY_ID

    location: Location
    elevation: Elevation
    next_rising: datetime
    next_setting: datetime
    next_dawn: datetime
    next_dusk: datetime
    next_midnight: datetime
    next_noon: datetime
    solar_elevation: float
    solar_azimuth: float
    rising: bool
    percentage: float
    _next_change: datetime

    def initialize(self) -> None:
        """Initialize the sun."""
        # pylint: disable=attribute-defined-outside-init
        self.adapi = self.get_ad_api()
        self.phase: str | None = None

        self._config_listener = None
        self._update_events_listener = None
        self._update_sun_position_listener = None
        self.update_location(initial=True)

    def get_astral_location(self) -> tuple[Location, Elevation]:
        """Get an astral location for the current Home Assistant configuration."""
        from astral import LocationInfo  # pylint: disable=import-outside-toplevel

        latitude = self.config["latitude"]
        longitude = self.config["longitude"]
        timezone = str(self.config["time_zone"])
        elevation: Elevation = self.config["elevation"]
        info: Location = Location(LocationInfo("", "", timezone, latitude, longitude))

        # Cache astral locations so they aren't recreated with the same args
        # if DATA_LOCATION_CACHE not in hass.data:
        #     hass.data[DATA_LOCATION_CACHE] = {}

        # if info not in hass.data[DATA_LOCATION_CACHE]:
        #     hass.data[DATA_LOCATION_CACHE][info] = Location(LocationInfo(*info))

        return info, elevation

    def get_location_astral_event_next(
        self,
        location: Location,
        elevation: Elevation,
        event: str,
        point_in_time: datetime | None = None,
        offset: timedelta | None = None,
    ) -> datetime:
        """Calculate the next specified solar event."""

        if offset is None:
            offset = timedelta()

        if point_in_time is None:
            point_in_time = cast(datetime, self.adapi.datetime(aware=True))

        kwargs: dict[str, Any] = {"local": False}
        if event not in ELEVATION_AGNOSTIC_EVENTS:
            kwargs["observer_elevation"] = elevation

        mod = -1
        while True:
            try:
                next_dt = (
                    cast(_AstralSunEventCallable, getattr(location, event))(
                        point_in_time.date() + timedelta(days=mod),
                        **kwargs,
                    )
                    + offset
                )
                if next_dt > point_in_time:
                    return next_dt
            except ValueError:
                pass
            mod += 1

    def get_location_astral_event_previous(
        self,
        location: Location,
        elevation: Elevation,
        event: str,
        point_in_time: datetime | None = None,
        offset: timedelta | None = None,
    ) -> datetime:
        """Calculate the next specified solar event."""

        if offset is None:
            offset = timedelta()

        if point_in_time is None:
            point_in_time = cast(datetime, self.adapi.datetime(aware=True))

        kwargs: dict[str, Any] = {"local": False}
        if event not in ELEVATION_AGNOSTIC_EVENTS:
            kwargs["observer_elevation"] = elevation

        mod = 0
        while True:
            try:
                next_dt = (
                    cast(_AstralSunEventCallable, getattr(location, event))(
                        point_in_time.date() + timedelta(days=mod),
                        **kwargs,
                    )
                    + offset
                )
                if next_dt < point_in_time:
                    return next_dt
            except ValueError:
                pass
            mod -= 1

    def update_location(self, initial: bool = False) -> None:
        """Update location."""
        location, elevation = self.get_astral_location()
        if not initial and location == self.location:
            return
        self.location = location
        self.elevation = elevation
        if self._update_events_listener:
            canceled = self.adapi.cancel_timer(self._update_events_listener)
        self.update_events(kwargs=None)

    def remove_listeners(self) -> None:
        """Remove listeners."""
        if self._update_events_listener:
            canceled = self.adapi.cancel_timer(self._update_events_listener)
        if self._update_sun_position_listener:
            canceled = self.adapi.cancel_timer(self._update_sun_position_listener)

    @property
    def state(self) -> str:
        """Return the state of the sun."""
        # 0.8333 is the same value as astral uses
        if self.solar_elevation > -0.833:
            return STATE_ABOVE_HORIZON

        return STATE_BELOW_HORIZON

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the sun."""
        return {
            STATE_ATTR_NEXT_DAWN: self.next_dawn.isoformat(),
            STATE_ATTR_NEXT_DUSK: self.next_dusk.isoformat(),
            STATE_ATTR_NEXT_MIDNIGHT: self.next_midnight.isoformat(),
            STATE_ATTR_NEXT_NOON: self.next_noon.isoformat(),
            STATE_ATTR_NEXT_RISING: self.next_rising.isoformat(),
            STATE_ATTR_NEXT_SETTING: self.next_setting.isoformat(),
            STATE_ATTR_ELEVATION: self.solar_elevation,
            STATE_ATTR_AZIMUTH: self.solar_azimuth,
            STATE_ATTR_RISING: self.rising,
            STATE_ATTR_PERCENTAGE: self.percentage,
        }

    def _check_event(
        self, point_in_time: datetime, sun_event: str, before: str | None
    ) -> datetime:
        # pylint: disable=attribute-defined-outside-init
        next_utc = self.get_location_astral_event_next(
            self.location, self.elevation, sun_event, point_in_time
        )
        if next_utc < self._next_change:
            self._next_change = next_utc
            self.phase = before
        return next_utc

    def update_events(self, kwargs) -> None:
        """Update the attributes containing solar events."""
        # pylint: disable=attribute-defined-outside-init
        # Grab current time in case system clock changed since last time we ran.
        self.adapi.log("entered update events.")
        point_in_time = cast(datetime, self.adapi.datetime(aware=True))
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

        self.adapi.log(f"Phase is {self.phase}")

        self.rising = self.next_noon < self.next_midnight

        self.adapi.log(
            f"sun phase_update@{point_in_time.isoformat()}: phase={self.phase}"
        )
        if self._update_sun_position_listener:
            canceled = self.adapi.cancel_timer(self._update_sun_position_listener)
        self.update_sun_position(kwargs=kwargs)

        # Set timer for the next solar event
        self._update_events_listener = self.adapi.run_at(
            self.update_events, self._next_change
        )
        self.adapi.log("next time: %s", self._next_change.isoformat())

    def update_sun_position(self, kwargs) -> None:
        """Calculate the position of the sun."""
        # Grab current time in case system clock changed since last time we ran.
        point_in_time = cast(datetime, self.adapi.datetime(aware=True))
        self.solar_azimuth = round(
            self.location.solar_azimuth(point_in_time, self.elevation), 2
        )
        self.solar_elevation = round(
            self.location.solar_elevation(point_in_time, self.elevation), 2
        )

        self.adapi.log(
            "sun position_update@%s: elevation=%s azimuth=%s",
            point_in_time.isoformat(),
            self.solar_elevation,
            self.solar_azimuth,
        )

        if self.state == STATE_ABOVE_HORIZON:
            if self.rising:
                self.prev_time = self.get_location_astral_event_previous(
                    self.location, self.elevation, SUN_EVENT_SUNRISE, point_in_time
                )
                h = self.next_noon.timestamp()  # pylint: disable=invalid-name
                x = self.prev_time.timestamp()  # pylint: disable=invalid-name
            else:
                self.prev_time = self.get_location_astral_event_previous(
                    self.location, self.elevation, SUN_EVENT_NOON, point_in_time
                )
                h = self.prev_time.timestamp()  # pylint: disable=invalid-name
                x = self.next_setting.timestamp()  # pylint: disable=invalid-name
            a = (-100) / (h - x) ** 2  # pylint: disable=invalid-name
            self.percentage = a * (point_in_time.timestamp() - h) ** 2 + 100
            self.adapi.log(f"Percentage is {self.percentage}")
        else:
            if self.rising:
                self.prev_time = self.get_location_astral_event_previous(
                    self.location, self.elevation, SUN_EVENT_MIDNIGHT, point_in_time
                )
                h = self.prev_time.timestamp()  # pylint: disable=invalid-name
                x = self.next_rising.timestamp()  # pylint: disable=invalid-name
            else:
                self.prev_time = self.get_location_astral_event_previous(
                    self.location, self.elevation, SUN_EVENT_SUNSET, point_in_time
                )
                h = self.next_midnight.timestamp()  # pylint: disable=invalid-name
                x = self.prev_time.timestamp()  # pylint: disable=invalid-name
            a = (100) / (h - x) ** 2  # pylint: disable=invalid-name
            self.percentage = a * (point_in_time.timestamp() - h) ** 2 - 100
            self.adapi.log(f"Percentage is {self.percentage}")

        updated = self.adapi.set_state(
            ENTITY_ID,
            state=self.state,
            attributes=self.extra_state_attributes,
            namespace="sun",
        )
        self.sun = self.adapi.get_entity(ENTITY_ID)

        # Next update as per the current phase
        assert self.phase
        delta = _PHASE_UPDATES[self.phase]
        # if the next update is within 1.25 of the next
        # position update just drop it
        if point_in_time + delta * 1.25 > self._next_change:
            self._update_sun_position_listener = None
            return
        self._update_sun_position_listener = self.adapi.run_at(
            self.update_sun_position, point_in_time + delta
        )

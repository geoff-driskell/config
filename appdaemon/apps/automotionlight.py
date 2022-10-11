"""
AutoMotionLight

Automated Motion Light
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterable
from copy import deepcopy
from enum import Enum
from inspect import stack
import logging
from pprint import pformat
import random
from typing import Any

# pylint: disable=import-error
import appdaemon.plugins.hass.hassapi as hass
from appdaemon.appdaemon import AppDaemon

__version__ = "0.0.1"

APP_NAME = "AutoMotionLights"
APP_ICON = "💡"
ON_ICON = APP_ICON
OFF_ICON = "🌑"
MODE_SWITCH_ICON = "⏰"

DEFAULT_NAME = "mode"
DEFAULT_LIGHT_SETTING = 100
DEFAULT_DELAY = 0
DEFAULT_MODES: list[dict[str, str | int]] = [
    dict(mode="Morning Quiet", light=15),
    dict(mode="Morning", light=15),
    dict(mode="Day", light=15),
    dict(mode="Evening", light=15),
    dict(mode="Night", light=15),
    dict(mode="Night Quiet", light=15),
]
DEFAULT_LOG_LEVEL = "INFO"
SECONDS_PER_MIN: int = 60

def natural_time(duration: int | float) -> str:
    """Converts time to a human readable format."""
    duration_min, duration_sec = divmod(duration, float(SECONDS_PER_MIN))

    # append suitable unit
    if duration >= SECONDS_PER_MIN:
        if duration_sec < 10 or duration_sec > 50:
            natural = f"{int(duration_min)}min"
        else:
            natural = f"{int(duration_min)}min {int(duration_sec)}sec"
    else:
        natural = f"{int(duration_sec)}sec"

    return natural

class Room:
    """Class for keeping track of a room."""
    def __init__(
        self,
        name: str,
        room_lights: set[str] = None,
        motion: set[str] = None,
        appdaemon: AppDaemon = None
    ) -> None:

        # Store the room name
        self.name: str = name

        self.room_lights: set[str] = room_lights

        self.motion: set[str] = motion

        self.handles: dict[str, str] = {}

        self.handles_automotionlight: set[str] = set()

        self._ad = appdaemon

    @property
    def lights_dimmable(self) -> list[str]:
        """Returns a list of dimmable lights in the room."""
        return [light for light in self.room_lights if light.startswith("light.")]

    @property
    def lights_non_dimmable(self) -> list[str]:
        """Returns a list of non dimmable lights in the room."""
        return [light for light in self.room_lights if light.startswith("switch.")]

class EntityType(Enum):
    """An enumeration for keeping track of entity types."""
    LIGHT = "light."
    SWITCH = "switch.{}_light"
    MOTION = "sensor.{}_motion"
    HUMIDITY = "sensor.{}_humidity"
    ILLUMINANCE = "sensor.{}_illuminance"

    @property
    def idx(self) -> str:
        """Returns the name of the enumeration."""
        return self.name.casefold()

    @property
    def prefix(self) -> str:
        """Returns the entity prefix of the type."""
        return str(self.value).casefold()


SENSORS_REQUIRED = [EntityType.MOTION.idx]
SENSORS_OPTIONAL = [EntityType.HUMIDITY.idx, EntityType.ILLUMINANCE.idx]

class AutoMotionLight(hass.Hass):
    """Automated Motion Lights."""


    def aml_log(
        self,
        msg: str,
        *args: Any,
        level: int | None = None,
        icon: str | None = None,
        repeat: int = 1,
        log_to_ha: bool = False,
        **kwargs: Any,
    ) -> None:
        """A custom appdaemon logger which can also log to HA."""
        kwargs.setdefault("ascii_encode", False)

        level = level if level else self.loglevel

        if level >= self.loglevel:
            message = f"{f'{icon} ' if icon else ' '}{msg}"
            _ = [self.log(message, *args, **kwargs) for _ in range(repeat)]

            if log_to_ha or self.log_to_ha:
                try:
                    ha_name = self.room.name.capitalize()
                except AttributeError:
                    ha_name = APP_NAME
                    self.aml_log(
                        "No room set yet, using 'automotionlight' for logging to HA",
                        level=logging.DEBUG,
                    )

                self.call_service(
                    "logbook/log",
                    name=ha_name,  # type:ignore
                    message=message,  # type:ignore
                )

    def listr(
        self,
        list_or_string: list[str] | set[str] | str | Any,
        entities_exist: bool = True,
    ) -> set[str]:
        """Checks the input type and returns a set of strings."""
        entity_list: list[str] = []

        if isinstance(list_or_string, str):
            entity_list.append(list_or_string)
        elif isinstance(list_or_string, (list, set)):
            entity_list += list_or_string
        elif list_or_string:
            self.aml_log(
                f"{list_or_string} is of type {type(list_or_string)} and "
                f"not 'Union[List[str], Set[str], str]'"
            )

        return set(
            filter(self.entity_exists, entity_list) if entities_exist else entity_list
        )

    async def initialize(self) -> None:
        """Initialize a room with automotionlight."""

        # pylint: disable=attribute-defined-outside-init

        self.icon = APP_ICON

        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)

        self.loglevel = (
            logging.DEBUG if self.args.get("debug_log", False) else logging.INFO
        )

        self.log_to_ha = self.args.get("log_to_ha", False)

        # notification thread (prevents doubled messages)
        self.notify_thread = random.randint(0, 9)  # nosec

        self.aml_log(
            f"setting log level to {logging.getLevelName(self.loglevel)}",
            level=logging.DEBUG,
        )

        # set room
        self.room_name = str(self.args.pop("room"))

        # general delay
        self.delay = int(self.args.pop("delay", DEFAULT_DELAY))

        # directly switch to new mode light settings
        self.transition_on_mode_switch: bool = bool(
            self.args.pop("transition_on_mode_switch", False)
        )

        # state values
        self.states = {
            "motion_on": self.args.pop("motion_state_on", None),
            "motion_off": self.args.pop("motion_state_off", None),
        }

        # threshold values
        self.thresholds = {
            "humidity": self.args.pop("humidity_threshold", None),
            EntityType.ILLUMINANCE.idx: self.args.pop("illuminance_threshold", None),
        }

        # on/off switch via input.boolean
        self.disable_switch_entities: set[str] = self.listr(
            self.args.pop("disable_switch_entities", set())
        )
        self.disable_switch_states: set[str] = self.listr(
            self.args.pop("disable_switch_states", set(["off"]))
        )

        # store if an entity has been switched on by automotionlight
        self.only_own_events: bool = bool(self.args.pop("only_own_events", False))
        self._switched_on_by_automotionlight: set[str] = set()

        # currently active mode settings
        self.active: dict[str, int | str] = {}

        self.active_mode: str = await self.get_state("input_select.house_mode")

        self.handle_turned_off: str | None = None

        # define light entities switched by automotionlight
        self.lights: set[str] = self.args.pop("lights", set())

        # sensors
        self.sensors: dict[str, Any] = {}

        # enumerate sensors for motion detection
        self.sensors[EntityType.MOTION.idx] = self.listr(
            self.args.pop(
                "motion",
                None
            )
        )

        self.room = Room(
            name=self.room_name,
            room_lights=self.lights,
            motion=self.sensors[EntityType.MOTION.idx],
            appdaemon=self.get_ad_api(),
        )

        # requirements check
        if not self.lights or not self.sensors[EntityType.MOTION.idx]:
            self.aml_log("")
            self.aml_log(
                f"{'No lights/sensors'} given and none found with name: "
                f"'{EntityType.LIGHT.prefix}*{self.room.name}*' or "
                f"'{EntityType.MOTION.prefix}*{self.room.name}*'",
                icon="⚠️ ",
            )
            return

        # enumerate optional sensors & disable optional features if sensors are not available
        for sensor_type in SENSORS_OPTIONAL:

            if sensor_type in self.thresholds and self.thresholds[sensor_type]:
                self.sensors[sensor_type] = self.listr(
                    self.args.pop(sensor_type, None)
                )

                self.aml_log(f"{self.sensors[sensor_type] = }", level=logging.DEBUG)

            else:
                self.aml_log(
                    f"No {sensor_type} sensors → disabling features based on {sensor_type}"
                    f" - {self.thresholds[sensor_type]}.",
                    level=logging.DEBUG,
                )
                del self.thresholds[sensor_type]

        # use user-defined modes if available
        self.mode_settings: dict[str, dict[str, str | int | bool]] = await self.build_modes(
            self.args.pop("modes", DEFAULT_MODES)
        )

        self.active[self.active_mode] = self.mode_settings.get(self.active_mode)

        # experimental fade on feature
        self.fading: bool = False

        # set up event listener for each sensor
        listener: set[Coroutine[Any, Any, Any]] = set()
        for sensor in self.sensors[EntityType.MOTION.idx]:
            listener.add(
                self.listen_state(
                    self.motion_detected,
                    entity_id=sensor,
                    new=self.states["motion_on"],
                )
            )
            listener.add(
                self.listen_state(
                    self.motion_cleared,
                    entity_id=sensor,
                    new=self.states["motion_off"],
                )
            )
        listener.add(
            self.listen_state(
                self.switch_mode, entity_id="input_select.house_mode"
            )
        )

        self.args.update(
            {
                "room": self.room_name.capitalize(),
                "delay": self.delay,
                "active_mode": self.active_mode,
                "modes": self.mode_settings,
                "lights": self.lights,
                "sensors": self.sensors,
                "only_own_events": self.only_own_events,
                "loglevel": self.loglevel,
            }
        )

        if self.thresholds:
            self.args.update({"thresholds": self.thresholds})

        # add disable entity to config if given
        if self.disable_switch_entities:
            self.args.update({"disable_switch_entities": self.disable_switch_entities})
            self.args.update({"disable_switch_states": self.disable_switch_states})

        # show parsed config
        self.show_info(self.args)

        await asyncio.gather(*listener)
        # await self.refresh_timer()

    def switch_mode(
        self, entity: str, attribute: str, old: str, new: str, kwargs: dict[str, Any]
    ) -> None:
        """Set new light settings according to mode."""
        # started the timer if motion is cleared
        self.aml_log(
            f"{stack()[0][3]}: {entity} changed {attribute} from {old} to {new}",
            level=logging.DEBUG,
        )
        mode = new
        self.active_mode = mode
        mode_settings = self.mode_settings.get(mode)
        
        self.active.update(mode_settings) 
        # = mode_settings.get("delay")
        # self.active["light_setting"] = mode_settings.get("light_setting")
        # self.active["fade_start"] = mode_settings.get("fade_start")
        # self.active["fade_end"] =   mode_settings.get("fade_end")
        # self.active["fade_delay"] = mode_settings.get("fade_delay")
        # self.active["fade_step"] =  mode_settings.get("fade_step")
        self.aml_log(self.active)

        if mode is not None:
            if not kwargs.get("initial"):

                delay = self.active["delay"]
                light_setting = self.active["light_setting"]
                if isinstance(light_setting, str):
                    is_scene = True
                    # if its a ha scene, remove the "scene." part
                    if "." in light_setting:
                        light_setting = (light_setting.split("."))[1]
                else:
                    is_scene = False

                self.aml_log(
                    f"{stack()[0][3]}: {self.transition_on_mode_switch = }",
                    level=logging.DEBUG,
                )

                action_done = "set"

                if self.transition_on_mode_switch and any(
                    [self.get_state(light) == "on" for light in self.lights]
                ):
                    self.lights_on(force=True)
                    action_done = "activated"

                self.aml_log(
                    f"{action_done} mode {mode} → "
                    f"{'scene' if is_scene else 'brightness'}: {light_setting}"
                    f"{'' if is_scene else '%'}, delay: {natural_time(delay)}",
                    icon=MODE_SWITCH_ICON,
                )

    async def motion_cleared(
        self, entity: str, attribute: str, old: str, new: str, _: dict[str, Any]
    ) -> None:
        """wrapper for motion sensors that do not push a certain event but.
        instead the default HA `state_changed` event is used for presence detection
        schedules the callback to switch the lights off after a `state_changed` callback
        of a motion sensors changing to "cleared" is received
        """

        # started the timer if motion is cleared
        self.aml_log(
            f"{stack()[0][3]}: {entity} changed {attribute} from {old} to {new}",
            level=logging.DEBUG,
        )

        if all(
            [
                await self.get_state(sensor) == self.states["motion_off"]
                for sensor in self.sensors[EntityType.MOTION.idx]
            ]
        ):
            # all motion sensors off, starting timer
            await self.refresh_timer()
        else:
            # cancel scheduled callbacks
            await self.clear_handles()

    async def motion_detected(
        self, entity: str, attribute: str, old: str, new: str, kwargs: dict[str, Any]
    ) -> None:
        """wrapper for motion sensors that do not push a certain event but.
        instead the default HA `state_changed` event is used for presence detection
        maps the `state_changed` callback of a motion sensors changing to "detected"
        to the `event` callback`
        """

        self.aml_log(
            f"{stack()[0][3]}: {entity} changed {attribute} from {old} to {new}",
            level=logging.DEBUG,
        )

        # cancel scheduled callbacks
        await self.clear_handles()

        self.aml_log(
            f"{stack()[0][3]}: handles cleared and cancelled all scheduled timers",
            level=logging.DEBUG,
        )

        # calling motion event handler
        data: dict[str, Any] = {"entity_id": entity, "new": new, "old": old}
        await self.motion_event("state_changed_detection", data, kwargs)

    async def motion_event(
        self, event: str, data: dict[str, str], _: dict[str, Any]
    ) -> None:
        """Main handler for motion events."""

        self.aml_log(
            f"{stack()[0][3]}: received '{event}' event from "
            f"'{data['entity_id'].replace(EntityType.MOTION.prefix, '')}'",
            level=logging.DEBUG,
        )
        fade_start = self.active["fade_start"]

        # check if automotionlight is disabled via home assistant entity
        self.aml_log(
            f"{stack()[0][3]}: {await self.is_disabled() = }",
            level=logging.DEBUG,
        )
        if await self.is_disabled():
            return

        # turn on the lights if not already
        if not any(
            [await self.get_state(light) == "on" for light in self.lights]
        ):
            self.aml_log(
                f"{stack()[0][3]}: switching on ",
                level=logging.DEBUG,
            )
            if fade_start is not None:
                self.fading = True
                self.fade_on_lights()
            else:
                await self.lights_on()
        else:
            self.aml_log(
                f"{stack()[0][3]}: light in {self.room.name.capitalize()} already on → refreshing "
                f"timer ",
                level=logging.DEBUG,
            )

        if event != "state_changed_detection":
            await self.refresh_timer()

    async def clear_handles(self, handles: set[str] = None) -> None:
        """clear scheduled timers/callbacks."""

        if not handles:
            handles = deepcopy(self.room.handles_automotionlight)
            self.room.handles_automotionlight.clear()


        await asyncio.gather(
            *[
                self.cancel_timer(handle)
                for handle in handles
                if await self.timer_running(handle)
            ]
        )

        self.aml_log(f"{stack()[0][3]}: cancelled scheduled callbacks", level=logging.DEBUG)

    async def refresh_timer(self) -> None:
        """refresh delay timer."""

        fnn = f"{stack()[0][3]}:"

        # cancel scheduled callbacks
        await self.clear_handles()

        # if no delay is set or delay = 0, lights will not switched off by automotionlight
        if delay := self.active.get("delay"):

            self.aml_log(
                f"{fnn} {self.active = } | {delay = }",
                level=logging.DEBUG,
            )

            handle = await self.run_in(self.lights_off, delay)

            self.room.handles_automotionlight.add(handle)

            if timer_info := await self.info_timer(handle):
                self.aml_log(
                    f"{fnn} scheduled callback to switch off the lights"
                    f"({timer_info[0].isoformat()}) | "
                    f"handles: {self.room.handles_automotionlight = }",
                    level=logging.DEBUG,
                )

    async def is_disabled(self) -> bool:
        """check if automotionlight is disabled via home assistant entity"""
        for entity in self.disable_switch_entities:
            if (
                state := await self.get_state(entity, copy=False)
            ) and state in self.disable_switch_states:
                self.aml_log(f"{APP_NAME} is disabled by {entity} with {state = }")
                return True

        return False

    async def is_blocked(self) -> bool:
        """
        Helper function to determine if light is blocked from turning off by
        the state of an entity.
        """
        # the "shower case"
        if humidity_threshold := self.thresholds.get("humidity"):

            for sensor in self.sensors[EntityType.HUMIDITY.idx]:
                try:
                    current_humidity = float(
                        await self.get_state(sensor)  # type:ignore
                    )
                except ValueError as error:
                    self.aml_log(
                        f"self.get_state(sensor) raised a ValueError for {sensor}: {error}",
                        level=logging.ERROR,
                    )
                    continue

                self.aml_log(
                    f"{stack()[0][3]}: {current_humidity = } >= {humidity_threshold = } "
                    f"= {current_humidity >= humidity_threshold}",
                    level=logging.DEBUG,
                )

                if current_humidity >= humidity_threshold:

                    await self.refresh_timer()
                    self.aml_log(
                        f"🛁 no motion in {self.room.name.capitalize()} since "
                        f"{natural_time(int(self.active['delay']))} → "
                        f"but {current_humidity}%RH > "
                        f"{humidity_threshold}%RH"
                    )
                    return True

        return False

    async def fade_on_lights(self) -> None:
        """Fade on the lights"""
        start = self.active.get("fade_start")
        end = self.active.get("fade_end")
        delay = self.active.get("fade_delay")
        step = self.active.get("fade_step")

        while start <= end and self.fading:
            await self.lights_on(force=True)
            start = await self.step_counter(start=start, step=step)
            self.active["light_setting"] = start
            self.sleep(delay=delay)
            if not self.fading:
                break

    async def step_counter(self, start: int, step: int) -> int:
        """Increment the light brightness"""
        start += step
        return start

    async def turn_off_lights(self, kwargs: dict[str, Any]) -> None:
        """Turn off the lights"""
        if lights := kwargs.get("lights"):
            self.aml_log(f"{stack()[0][3]}: {lights = }", level=logging.DEBUG)
            for light in lights:
                await self.call_service("homeassistant/turn_off", entity_id=light)
            self.run_in_thread(self.turned_off, thread=self.notify_thread)

    async def lights_on(self, force: bool = False) -> None:
        """Turn on the lights."""

        self.aml_log(
            f"{stack()[0][3]}: {self.thresholds.get(EntityType.ILLUMINANCE.idx) = }"
            f" | {force = } | {bool(force) = }",
            level=logging.DEBUG,
        )

        force = bool(force)

        if illuminance_threshold := self.thresholds.get(EntityType.ILLUMINANCE.idx):

            # the "eco mode" check
            for sensor in self.sensors[EntityType.ILLUMINANCE.idx]:
                self.aml_log(
                    f"{stack()[0][3]}: {self.thresholds.get(EntityType.ILLUMINANCE.idx) = } | "
                    f"{float(await self.get_state(sensor)) = }",  # type:ignore
                    level=logging.DEBUG,
                )
                try:
                    if (
                        illuminance := float(
                            await self.get_state(sensor)  # type:ignore
                        )  # type:ignore
                    ) >= illuminance_threshold:
                        self.aml_log(
                            f"According to {sensor} its already bright enough ¯\\_(ツ)_/¯"
                            f" | {illuminance} >= {illuminance_threshold}"
                        )
                        return

                except ValueError as error:
                    self.aml_log(
                        f"could not parse illuminance '{await self.get_state(sensor)}' "
                        f"from '{sensor}': {error}"
                    )
                    return

        light_setting = (
            self.active.get("light_setting")
        )
        self.aml_log(light_setting)

        if isinstance(light_setting, str):

            # last check until we switch the lights on... really!
            if not force and any(
                [await self.get_state(light) == "on" for light in self.lights]
            ):
                self.aml_log("¯\\_(ツ)_/¯")
                return

            for entity in self.lights:

                item = light_setting if light_setting.startswith("scene.") else entity

                await self.call_service(
                    "homeassistant/turn_on", entity_id=item  # type:ignore
                )  # type:ignore
                if self.only_own_events:
                    self._switched_on_by_automotionlight.add(item)

            self.aml_log(
                f"{self.room.name.capitalize()} turned {'on'} → "
                f"{'ha'} scene: "
                f"{light_setting.replace('scene.', '')}"
                f" | delay: {natural_time(int(self.active['delay']))}",
                icon=ON_ICON,
            )

        elif isinstance(light_setting, int):

            if light_setting == 0:
                await self.lights_off({})

            else:
                # last check until we switch the lights on... really!
                if not force and any(
                    [await self.get_state(light) == "on" for light in self.lights]
                ):
                    self.aml_log("¯\\_(ツ)_/¯")
                    return

                for entity in self.lights:
                    if entity.startswith("switch."):
                        await self.call_service(
                            "homeassistant/turn_on", entity_id=entity  # type:ignore
                        )
                    else:
                        await self.call_service(
                            "homeassistant/turn_on",
                            entity_id=entity,  # type:ignore
                            brightness_pct=light_setting,  # type:ignore
                        )

                        self.aml_log(
                            f"{self.room.name.capitalize()} turned {'on'} → "
                            f"brightness: {light_setting}%"
                            f" | delay: {natural_time(int(self.active['delay']))}",
                            icon=ON_ICON,
                        )
                    if self.only_own_events:
                        self._switched_on_by_automotionlight.add(entity)

        else:
            raise ValueError(
                f"invalid brightness/scene: {light_setting!s} " f"in {self.room.name}"
            )

    async def lights_off(self, _: dict[str, Any]) -> None:
        """Turn off the lights."""

        self.aml_log(
            f"{stack()[0][3]} {await self.is_disabled()} | {await self.is_blocked() = }",
            level=logging.DEBUG,
        )

        # check if automotionlight is disabled via home assistant entity
        # or blockers like the "shower case"
        if (await self.is_disabled()) or (await self.is_blocked()):
            return

        # cancel scheduled callbacks
        await self.clear_handles()

        self.aml_log(
            f"{stack()[0][3]}: "
            f"{any([await self.get_state(entity) == 'on' for entity in self.lights]) = }"
            f" | {self.lights = }",
            level=logging.DEBUG,
        )

        # if any([await self.get_state(entity) == "on" for entity in self.lights]):
        if all([await self.get_state(entity) == "off" for entity in self.lights]):
            return

        at_least_one_turned_off = False
        for entity in self.lights:
            if self.only_own_events:
                if entity in self._switched_on_by_automotionlight:
                    self.fading = False
                    self.active["light_setting"] = self.mode_settings[self.active_mode]["light_setting"]
                    await self.call_service(
                        "homeassistant/turn_off", entity_id=entity  # type:ignore
                    )  # type:ignore
                    self._switched_on_by_automotionlight.remove(entity)
                    at_least_one_turned_off = True
            else:
                self.fading = False
                self.active["light_setting"] = self.mode_settings[self.active_mode]["light_setting"]
                await self.call_service(
                    "homeassistant/turn_off", entity_id=entity  # type:ignore
                )  # type:ignore
                at_least_one_turned_off = True
        if at_least_one_turned_off:
            self.run_in_thread(self.turned_off, thread=self.notify_thread)

    async def turned_off(self, _: dict[str, Any] | None = None) -> None:
        """Helper function to handle when light is manually turned off."""
        # cancel scheduled callbacks
        await self.clear_handles()

        self.aml_log(
            f"no motion in {self.room.name.capitalize()} since "
            f"{natural_time(int(self.active['delay']))} → turned {'off'}",
            icon=OFF_ICON,
        )

    async def build_modes(
        self, modes: list[Any]
    ) -> dict[str, dict[str, int | str | bool]] | None:
        """Build the settings for each mode."""
        mode_dict: dict[str, dict[str, str | int | bool]] = {}
        for idx, mode in enumerate(modes):
            mode_name = mode.get("mode", f"{DEFAULT_NAME}_{idx}")
            mode_delay = mode.get("delay", self.delay)
            mode_light_setting = mode.get("light", DEFAULT_LIGHT_SETTING)
            mode_fade_start = mode.get("fade_start", None)
            mode_fade_end = mode.get("fade_end", None)
            mode_fade_delay = mode.get("fade_delay", None)
            mode_fade_step = mode.get("fade_step", None)

            # configuration for this mode
            mode_dict[mode_name] = {}
            mode_dict[mode_name]["light_setting"] = mode_light_setting
            mode_dict[mode_name]["delay"] = mode_delay
            mode_dict[mode_name]["fade_start"] = mode_fade_start
            mode_dict[mode_name]["fade_end"] = mode_fade_end
            mode_dict[mode_name]["fade_delay"] = mode_fade_delay
            mode_dict[mode_name]["fade_step"] = mode_fade_step

            # check if this mode should be active now
            if mode_name == self.active_mode:
                self.active["delay"] = mode_delay
                self.active["light_setting"] = mode_light_setting
                self.active["fade_start"] = mode_fade_start
                self.active["fade_end"] = mode_fade_end
                self.active["fade_delay"] = mode_fade_delay
                self.active["fade_step"] = mode_fade_step

        return mode_dict

    def show_info(self, config: dict[str, Any] | None = None) -> None:
        """Show the configuration."""
        # check if a room is given

        if config:
            self.config = config

        if not self.config:
            self.aml_log("no configuration available", icon="‼️", level=logging.ERROR)
            return

        room = ""
        if "room" in self.config:
            room = f" · {self.config['room'].capitalize()}"

        self.aml_log("", log_to_ha=False)
        self.aml_log(
            f"{APP_NAME} v{__version__}{room}", icon=self.icon, log_to_ha=False
        )
        self.aml_log("", log_to_ha=False)

        listeners = self.config.pop("listeners", None)

        for key, value in self.config.items():

            # hide "internal keys" when displaying config
            if key in ["module", "class"] or key.startswith("_"):
                continue

            if isinstance(value, (list, set)):
                self.print_collection(key, value, 2)
            elif isinstance(value, dict):
                self.print_collection(key, value, 2)
            else:
                self._print_cfg_setting(key, value, 2)

        if listeners:
            self.aml_log("  event listeners:", log_to_ha=False)
            for listener in sorted(listeners):
                self.aml_log(f"    · {listener}", log_to_ha=False)

        self.aml_log("", log_to_ha=False)

    def print_collection(
        self, key: str, collection: Iterable[Any], indentation: int = 0
    ) -> None:
        """Print contents of a dict or set or list"""
        self.aml_log(f"{indentation * ' '}{key}:", log_to_ha=False)
        indentation = indentation + 2

        for item in collection:
            indent = indentation * " "

            if isinstance(item, dict):

                if "name" in item:
                    self.print_collection(item.pop("name", ""), item, indentation)
                else:
                    self.aml_log(
                        f"{indent}{pformat(item, compact=True)}", log_to_ha=False
                    )

            elif isinstance(collection, dict):

                if isinstance(collection[item], set):
                    self.print_collection(item, collection[item], indentation)
                else:
                    self._print_cfg_setting(item, collection[item], indentation)

            else:
                self.aml_log(f"{indent}· {item}", log_to_ha=False)

    def _print_cfg_setting(self, key: str, value: int | str, indentation: int) -> None:
        unit = prefix = ""
        indent = indentation * " "

        # legacy way
        if key == "delay" and isinstance(value, int):
            unit = "min"
            min_value = f"{int(value / 60)}:{int(value % 60):02d}"
            self.aml_log(
                f"{indent}{key}: {prefix}{min_value}{unit} ≈ " f"{value}sec",
                ascii_encode=False,
                log_to_ha=False,
            )

        else:
            if "_units" in self.config and key in self.config["_units"]:
                unit = self.config["_units"][key]
            if "_prefixes" in self.config and key in self.config["_prefixes"]:
                prefix = self.config["_prefixes"][key]

            self.aml_log(f"{indent}{key}: {prefix}{value}{unit}", log_to_ha=False)

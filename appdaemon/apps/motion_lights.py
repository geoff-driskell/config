from collections.abc import Coroutine, Iterable
from copy import deepcopy
from datetime import time
from xml.dom.minidom import Entity
import appdaemon.plugins.hass.hassapi as hass
from typing import Any
from enum import Enum
import logging

APP_NAME = "MOTION_LIGHTS"
APP_ICON = "💡"

DEFAULT_NAME = "mode"
DEFAULT_LIGHT_SETTING = 100
DEFAULT_DELAY = 0
DEFAULT_MODES: list[dict[str, str | int]] = [
    dict(mode="Morning Quiet", light=15, fade_to=None, fade_time=None),
    dict(mode="Morning", light=15, fade_to=None, fade_time=None),
    dict(mode="Day", light=15, fade_to=None, fade_time=None),
    dict(mode="Evening", light=15, fade_to=None, fade_time=None),
    dict(mode="Night", light=15, fade_to=None, fade_time=None),
    dict(mode="Night Quiet", light=15, fade_to=None, fade_time=None),
]
DEFAULT_LOG_LEVEL = "INFO"
class EntityType(Enum):
    LIGHT = 1
    SWITCH = 2
    MOTION = 3
    HUMIDITY = 4
    ILLUMINANCE = 5

    @property
    def idx(self) -> str:
        return self.name.casefold()


SENSORS_REQUIRED = [EntityType.MOTION.idx]
SENSORS_OPTIONAL = [EntityType.HUMIDITY.idx, EntityType.ILLUMINANCE.idx]

class OccupancyLights(hass.Hass):
    def hass_logger(self, msg: str, *args: Any, level: int | None = None, icon: str | None = None, **kwargs: Any,) -> None:
        kwargs.setdefault("ascii_encode", False)

        level = level if level else self.loglevel
        
        message = message.replace("\033[1m", "").replace("\033[0m", "")

        try:
            ha_name = self.room.name.capitalize()
        except:
            ha_name = APP_NAME
            self.log("No room set yet, using 'MOTION_LIGHTS' for logging to HA.", level=logging.DEBUG,)
        
        self.call_service("logbook/log", name=ha_name, message=message)


    def list_or_string(self, list_or_string: list[str] | set[str] | str | Any) -> set[str]:
        entity_list: list[str] = []

        if isinstance(list_or_string, str):
            entity_list.append(list_or_string)
        elif isinstance(list_or_string, (list, set)):
            entity_list += list_or_string
        
        return set(filter(self.entity_exists, entity_list))

    def initialize(self):
        # Check some Params
        self.icon = APP_ICON

        # get an actual dict for configuration values
        self.args: dict[str, Any] = dict(self.args)
        
        self.loglevel = (logging.DEBUG if self.args.get("debug_log", False) else logging.INFO)

        # set room
        self.room_name = str(self.args.pop("room"))

        # general delay
        self.delay = int(self.args.pop("delay"))

        # directly switch to new light settings on mode switch
        self.transition_on_mode_change: bool = bool(self.args.pop("transition_on_mode_switch", False))

        # state values
        self.states = {
            "motion_on": self.args.pop("motion_state_on", None),
            "motion_off": self.args.pop("motion_state_off", None),
        }

        # threshold values
        self.thresholds = {
            EntityType.HUMIDITY: self.args.pop("humidity_threshold", None),
            EntityType.ILLUMINANCE: self.args.pop("illuminance_threshold", None)
        }

        self.disable_switch_entities: set[str] = self.list_or_string(self.args.pop("disable_switch_entities", set()))
        self.disable_switch_states: set[str] = self.list_or_string(self.args.pop("disable_switch_states", set(["off"])))

        self.active: dict[str, int | str] = {}

        states = self.get_state()

        self.handle_turned_off: str | None = None
        
        self.lights: set[str] = self.args.pop("lights", set())
        
        self.sensors: dict[str, Any] = {}

        self.sensors[EntityType.MOTION] = self.list_or_string(self.args.pop("motion", None))

        self.room = Room(
            name=self.room_name,
            room_lights=self.lights,
            motion=self.sensors[EntityType.MOTION],
            appdaemon=self.get_ad_api()
        )
        
        if not self.lights or not self.sensors[EntityType.MOTION]:
            self.log("")
            self.log("No lights or sensors given.")
            self.log("")
            return
        
        for sensor_type in SENSORS_OPTIONAL:
            if sensor_type in self.thresholds and self.thresholds[sensor_type]:
                self.sensors[sensor_type] = self.list_or_string(self.args.pop(sensor_type, None))
            else:
                del self.thresholds[sensor_type]
        
        modes = self.build_modes(self.args.pop("modes", DEFAULT_MODES))


        # Subscribe to sensors
        listener: set[Coroutine[Any, Any, Any]] = set()
        for sensor in self.sensors[EntityType.MOTION.idx]:
            listener.add(
                self.listen_state(self.motion_detected, entity_id=sensor, new=self.states["motion_on"],)
            )
            listener.add(
                self.listen_state(self.motion_cleared, entity_id=sensor, new=self.states["motion_off"],)
            )


        self.listen_state(self.switch_mode, entity_id="input_select.house_mode")

        self.motion_sensors: set[str] = self.args.pop("motion", None)
        self.humidity_sensor = self.args.pop("humidity", None)
        self.morning_quiet_light = self.args.pop("morning_quiet_light", None)
        self.morning_light = self.args.pop("morning_light", None)
        self.day_light = self.args.pop("day_light", None)
        self.evening_light = self.args.pop("evening_light", None)
        self.night_light = self.args.pop("night_light", None)
        self.night_quiet_light = self.args.pop("night_quiet_light", None)
        self.log("App completed initialization.", level="INFO")

    def switch_mode(self, kwargs: dict[str, Any]) -> None:
        mode = self.get_state("input_select.house_mode")
        self.active["mode"] = mode
        if mode is not None:
            if mode == "Morning Quiet":
                self.active["light_setting"] = self.morning_quiet_light
            elif mode == "Morning Quiet":
                self.active["light_setting"] = self.morning_light
            elif mode == "Day":
                self.active["light_setting"] = self.day_light
            elif mode == "Evening":
                self.active["light_setting"] = self.evening_light
            elif mode == "Night":
                self.active["light_setting"] = self.night_light
            elif mode == "Night Quiet":
                self.active["light_setting"] = self.night_quiet_light
            else:
                self.log("The current house mode ({0}) is invalid, doing nothing.".format(self.mode))
    
    def motion_cleared(self, entity, attribute, old, new, kwargs):
        if all(
            [
                self.get_state(sensor) == self.states["motion_off"]
                for sensor in self.sensors["motion"]
            ]
        ):
    
    def motion_detected(self, entity, attribute, old, new, kwargs):
        self.clear_handles()
        if not self.get_state(self.light) == "on":
            self.light_on()
    

    def clear_handles(self):
        pass

    def lights_on(self):
        light_setting = self.active.get("light_setting")
        if isinstance(light_setting, str):
            for entity in self.lights:
                item = light_setting if light_setting.startswith("scene.") else entity
                self.call_service("homeassistant/turn_on", entity_id=item)
        elif isinstance(light_setting, int):
            if light_setting == 0:
                self.lights_off()
            else:
                for entity in self.lights:
                    if entity.startswith("switch."):
                        self.call_service("homeassistant/turn_on", entity_id=self.light)
                    else:
                        self.call_service("homeassistant/turn_on", entity_id=self.light, brightness_pct=light_setting)
        else:
            raise ValueError(f"Invalid brightness/scene: {light_setting!s}")
    
    def lights_off(self):
        if self.is_disabled() or self.is_blocked():
            return
        
        self.clear_handles()

        if all(self.get_state(entity) == "off" for entity in self.lights):
            return
        
        for entity in self.lights:
            self.call_service("homeassistant/turn_off", entity_id=entity)
    
    def turned_off(self):
        self.clear_handles()




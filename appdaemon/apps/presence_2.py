from enum import Enum
import time

import appdaemon.plugins.hass.hassapi as hass

import utils

__version__ = "0.0.1"


class State(Enum):
    Home = "home"
    JustArrived = "just_arrived"
    Away = "away"
    JustLeft = "just_left"
    ExtendedAway = "extended_away"

    @staticmethod
    def from_string(label):
        if not isinstance(label, str):
            raise TypeError("Argument label needs to be a string.")
        if label.casefold() in ("home"):
            return State.Home
        elif label.casefold() in ("arrived", "just arrived", "just_arrived"):
            return State.JustArrived
        elif label.casefold() in ("away", "not_home", "not home"):
            return State.Away
        elif label.casefold() in ("left", "just left", "just_left"):
            return State.JustLeft
        elif label.casefold() in ("extended away", "extended_away", "vacation"):
            return State.ExtendedAway
        else:
            raise ValueError(f"Argument label '{label}' is not a valid state.")


class TrackerState(Enum):
    Home = "home"
    NotHome = "not_home"

    @staticmethod
    def from_string(label):
        if not isinstance(label, str):
            raise TypeError("Argument label needs to be a string.")
        if label.casefold() == "home":
            return TrackerState.Home
        else:
            return TrackerState.NotHome


class Validator:
    from voluptuous import Schema, Required, Optional, Range, All, Or

    TIME_5_MINUTES = 5 * 60
    TIME_24_HOURS = 24 * 60 * 60

    SCHEMA = Schema(
        {
            Required("tracker"): str,
            Required("state"): str,
            Optional("map", default={state.value: state.value for state in State}): {
                state.value: str for state in State
            },
            Optional(
                "just_left_delay", default=TIME_5_MINUTES
            ): utils.parse_duration_literal,
            Optional(
                "just_arrived_delay", default=TIME_5_MINUTES
            ): utils.parse_duration_literal,
            Optional(
                "extended_away_delay", default=TIME_24_HOURS
            ): utils.parse_duration_literal,
        },
        extra=True,
    )

    @classmethod
    def validate(cls, dict):
        return cls.SCHEMA(dict)


class Presence(hass.Hass):
    def initialize(self):
        self.log(f"Presence App @ {__version__}")

        config = Validator.validate(self.args)

        self._tracker_entity = config["tracker"]
        self._state_entity = config["state"]
        self._just_left_delay = config["just_left_delay"]
        self._just_arrived_delay = config["just_arrived_delay"]
        self._extended_away_delay = config["extended_away_delay"]

        user_map = config["map"]
        user_map = {State.from_string(k): v for k, v in user_map.items()}
        self._map = {state: user_map.get(state, state.value) for state in State}
        self._imap = {v: k for k, v in self._map.items()}

        self.timer = None
        self.current_state = None

        if config.get("init_options", False):
            self._set_options()
            time.sleep(1)

        self._init_current_state()
        self.listen_state(self._on_tracker_change, self._tracker_entity)

    def _on_tracker_change(self, entity, attribute, old, new, kwargs):
        self.log(f"On tracker change: {old} -> {new}")
        old_state = TrackerState.from_string(old)
        new_state = TrackerState.from_string(new)
        if old_state == TrackerState.NotHome and new_state == TrackerState.Home:
            if self._current_state is State.JustLeft:
                self._set_person_state(State.Home)
            else:
                self._set_person_state(State.JustArrived)
        if old_state == TrackerState.Home and new_state == TrackerState.NotHome:
            self._set_person_state(State.JustLeft)

    def _on_scheduled_state_change(self, kwargs):
        new_state = kwargs.pop("new_state")
        self._set_person_state(new_state)

    def _schedule_state_change(self, delay, new_state):
        self.timer = self.run_in(
            self._on_scheduled_state_change, delay=delay, new_state=new_state
        )

    def _set_person_state(self, state):
        self._current_state = state

        if self.timer:
            self.cancel_timer(self.timer)
        if state == State.JustArrived:
            self._schedule_state_change(self._just_arrived_delay, State.Home)
        elif state == State.JustLeft:
            self._schedule_state_change(self._just_left_delay, State.Away)
        elif state == State.Away:
            self._schedule_state_change(self._extended_away_delay, State.ExtendedAway)

    def _init_current_state(self):
        hass_state = self.get_state(entity_id=self._state_entity)
        current_state = self._imap.get(hass_state)
        if current_state is None:
            self.log(f"Current state in hass is invalid. Falling back to {State.Home}.")
            current_state = State.Home
        tracker_state = TrackerState.from_string(
            self.get_state(entity_id=self._tracker_entity)
        )
        if tracker_state is TrackerState.Home and current_state not in (
            State.JustArrived,
            State.Home,
        ):
            self.log(
                f"Current state '{current_state}' is invalid with tracker state '{tracker_state}'. Resetting to home."
            )
            current_state = State.Home
        elif tracker_state is TrackerState.NotHome and current_state not in (
            State.JustLeft,
            State.Away,
            State.ExtendedAway,
        ):
            self.log(
                f"Current state '{current_state}' is invalid with tracker state '{tracker_state}'. Resetting to away."
            )
            current_state = State.Away

        self._set_person_state(state=current_state)

    def _set_options(self):
        current_state = self.get_state(entity_id=self._state_entity)
        self.log(f"Current state is {current_state}.")
        options = list(self._map.values())
        self.log(f"Setting state options to {options}.")
        self.call_service(
            "input_select/set_options", entity_id=self._state_entity, options=options
        )

        if current_state not in options:
            self.log(f"Previous state is no longer valid - reverting to state = home.")
            current_state = self._map[State.Home]
        self.log(f"Restoring state to {current_state}.")
        self._set_person_state(self._imap[current_state])

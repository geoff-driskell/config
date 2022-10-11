"""Module to handle shutting down the house at bedtime."""

from enum import Enum
from typing import Any
import appdaemon.plugins.hass.hassapi as hass

TV_ACTIVE_STATES: list[str] = ["Idle", "Paused", "Playing"]
TV_INACTIVE_STATES: list[str] = ["Standby", "Off", "Unavailable", "Unknown"]
DEFAULT_DELAY: int = 600

TV_ENTITY = "media_player.master_bedroom"


class RoomStates(Enum):
    """Enum to track the state of the bedroom."""
    EMPTY = 1
    BATHROOM = 2
    MAYBE_BED = 3
    BED = 4


class Bedtime(hass.Hass):
    """Bedtime class."""

    def initialize(self):
        """Initialize the bedtime class and listeners."""
        # pylint: disable=attribute-defined-outside-init
        # get a real dict for the configuration
        self.args: dict[str, Any] = dict(self.args)
        self.mode: str = self.get_state("input_select.house_mode")
        self.lamp_timer_handle = None
        self.tv_check_handle = None
        self.current_state: str = RoomStates.EMPTY
        self.delay: int = int(self.args.pop("delay", DEFAULT_DELAY))
        self.tv_delay: int = int(self.args.pop("tv_delay", DEFAULT_DELAY))

        self.listen_state(self.entered_bathroom, "light.master_bathroom_vanity_lights",
                          new="on",
                          constrain_input_select="input_select.house_mode,Night,Night Quiet")
        self.listen_state(self.left_bathroom, "light.master_bathroom_vanity_lights",
                          new="off",
                          constrain_input_select="input_select.house_mode,Night,Night Quiet")
        self.run_daily(self.reset_room_state, "09:00:00")

    def entered_bathroom(self, entity, attribute, old, new, kwargs):
        # pylint: disable=attribute-defined-outside-init
        """Get the room ready for bed."""
        self.log(
            "Someone went into the master bathroom, we may be getting ready for bed.")

        if self.current_state == RoomStates.EMPTY:
            # First time in the room tonight, prep the room.
            # Turn the lamp on.
            if self.get_state("switch.master_bedroom_lamps") == "off":
                self.turn_on("switch.master_bedroom_lamps")
            else:
                self.log("Lamp is already on.")

            # Turn the fan on
            if self.get_state("fan.master_bedroom_fan") == "off":
                self.turn_on("fan.master_bedroom_fan")
            else:
                self.log("Fan is already on.")
            # Record someone in the bathroom
            self.current_state = RoomStates.BATHROOM
        elif self.current_state == RoomStates.BED:
            # Someone needs to potty don't change the room
            return
        elif self.current_state == RoomStates.MAYBE_BED:
            # False Alarm, not bedtime yet
            self.current_state = RoomStates.BATHROOM
        else:
            self.log(
                f"Someone went into the bathroom and the room state was {self.current_state}. \
                This was unexpected.")

    def tv_is_on(self) -> bool:
        """Determine if the tv is on."""
        # pylint: disable=attribute-defined-outside-init
        self.log("TV is playing called")
        return bool(
            any(
                self.get_state("media_player.master_bedroom") == state for state in TV_ACTIVE_STATES
            )
        )

    def down_for_the_night(self):
        """Turn off the lamp."""
        # pylint: disable=attribute-defined-outside-init
        self.log("Occupants are down for the night.")
        self.run_in(self.turn_off("switch.master_bedroom_lamps"), self.delay)

    def final_bed_check(self, entity, attribute, old, new, kwargs):
        """Check one last time to see if this is down for the night."""
        # pylint: disable=attribute-defined-outside-init
        if self.tv_is_on():
            self.current_state = RoomStates.BED
            self.down_for_the_night()
        else:
            self.current_state = RoomStates.EMPTY

    def reset_room_state(self):
        """Reset the room to empty state."""
        # pylint: disable=attribute-defined-outside-init
        self.current_state = RoomStates.EMPTY

    def left_bathroom(self, entity, attribute, old, new, kwargs):
        """Handle people in bed."""
        # pylint: disable=attribute-defined-outside-init
        if self.current_state == RoomStates.BATHROOM:
            self.current_state = RoomStates.MAYBE_BED
            if self.tv_is_on():
                # Turn off the lamps in the specified time
                self.current_state = RoomStates.BED
                self.down_for_the_night()
            else:
                self.tv_check_handle = self.run_in(
                    self.left_bathroom, self.delay)
        if self.current_state == RoomStates.BED:
            return

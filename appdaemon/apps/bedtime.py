"""Module to handle shutting down the house at bedtime."""

from enum import Enum
from typing import Any
import appdaemon.plugins.hass.hassapi as hass

TV_ACTIVE_STATES: list[str] = ["idle", "paused", "playing"]
TV_INACTIVE_STATES: list[str] = ["standby", "off", "unavailable", "unknown"]
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

    def lamp_off(self, kwargs):
        """Turn off the lamp."""
        self.log("Turning off the light, night night!")
        self.turn_off("switch.master_bedroom_lamps")

    def refresh_tv_timer(self):
        """Extend the TV timer if it is running."""
        # pylint: disable=attribute-defined-outside-init
        if self.timer_running(self.tv_check_handle):
            self.log("The TV time was running. We are going to reset it.")
            self.cancel_timer(self.tv_check_handle)
            self.tv_check_handle = self.run_in(self.final_bed_check, self.tv_delay)

    def refresh_lamp_timer(self):
        """Extend the lamp timer if it is running."""
        # pylint: disable=attribute-defined-outside-init
        if self.timer_running(self.lamp_timer_handle):
            self.log("The lamp timer was running. We are going to reset it.")
            self.cancel_timer(self.lamp_timer_handle)
            self.lamp_timer_handle = self.run_in(
                self.lamp_off, self.delay
            )

    def entered_bathroom(self, entity, attribute, old, new, kwargs):
        # pylint: disable=attribute-defined-outside-init
        """Get the room ready for bed."""
        self.log("Someone entered the master bathroom.")
        self.log(f"The master bedroom state is {self.current_state}.")

        if self.current_state == RoomStates.EMPTY:
            # First time in the room tonight, prep the room.
            self.log("Setting the state to BATHROOM")
            # Record someone in the bathroom
            self.current_state = RoomStates.BATHROOM
            # Turn the lamp on.
            #if self.get_state("switch.master_bedroom_lamps") == "off":
            #    self.log("Turning the lamp on.")
            #    self.turn_on("switch.master_bedroom_lamps")
            #else:
            #    self.log("Lamp is already on.")

            # Turn the fan on
            if self.get_state("fan.master_bedroom_fan") == "off":
                self.log("Turning the fan on.")
                self.turn_on("fan.master_bedroom_fan")
            else:
                self.log("Fan is already on.")
        elif self.current_state == RoomStates.BED:
            # Someone needs to potty don't change the room
            self.log("Someone is stirring. Resetting the lamp off timer if it's still on.")
            self.log(self.lamp_timer_handle)
            self.refresh_lamp_timer()
        elif self.current_state == RoomStates.MAYBE_BED:
            # False Alarm, not bedtime yet
            self.log("I guess we weren't quite ready for bed.")
            self.log("Setting the room state back to BATHROOM.")
            self.current_state = RoomStates.BATHROOM
            self.log(self.tv_check_handle)
            self.refresh_tv_timer()
        else:
            self.log(f"Someone went into the bathroom and the room state was {self.current_state}.")
            self.log("How did that happen?")

    def tv_is_on(self) -> bool:
        """Determine if the tv is on."""
        # pylint: disable=attribute-defined-outside-init
        self.log("Checking to see if the tv is playing.")
        self.log(self.get_state("media_player.master_bedroom"))
        return bool(
            any(
                self.get_state("media_player.master_bedroom") == state for state in TV_ACTIVE_STATES
            )
        )

    def down_for_the_night(self, kwargs):
        """Turn off the lamp."""
        # pylint: disable=attribute-defined-outside-init
        self.log("Occupants are down for the night.")
        self.log("Starting the lamp timer.")
        self.log(f"The lamp will turn off in {self.delay} seconds.")
        self.run_in(self.lamp_off, self.delay)

    def reset_room_state(self, kwargs):
        """Reset the room to empty state."""
        # pylint: disable=attribute-defined-outside-init
        self.log("Reset room state called.")
        if self.timer_running(self.tv_check_handle):
            self.log("The TV check timer was running, canceling it.")
            self.cancel_timer(self.tv_check_handle)
        if self.timer_running(self.lamp_timer_handle):
            self.log("The lamp timer was running, canceling it.")
            self.cancel_timer(self.lamp_timer_handle)
        self.log("Resetting the room back to empty.")
        self.current_state = RoomStates.EMPTY

    def final_bed_check(self, kwargs):
        """Check one last time to see if this is down for the night."""
        # pylint: disable=attribute-defined-outside-init
        if self.tv_is_on():
            self.log("The TV was on this time!")
            self.log("Setting the room state to BED.")
            self.current_state = RoomStates.BED
            self.log("We are down for the night.")
            self.down_for_the_night(kwargs)
        else:
            self.log("False alarm, we aren't going to bed now.")
            self.log("Resetting room to empty.")
            self.reset_room_state(kwargs)

    def left_bathroom(self, entity, attribute, old, new, kwargs):
        """Handle people in bed."""
        # pylint: disable=attribute-defined-outside-init
        if self.current_state == RoomStates.BATHROOM:
            self.current_state = RoomStates.MAYBE_BED
            if self.tv_is_on():
                # Turn off the lamps in the specified time
                self.log("The TV is on. I am going to assume we are down for the night.")
                self.log("Setting the room state to BED.")
                self.current_state = RoomStates.BED
                self.down_for_the_night(kwargs)
            else:
                self.log("The TV was not on.")
                self.log(f"I am going to check one more time in {self.tv_delay} seconds.")
                self.tv_check_handle = self.run_in(
                    self.final_bed_check, self.tv_delay)
        if self.current_state == RoomStates.BED:
            self.log("The one stirring is back in bed.")
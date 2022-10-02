from platform import machine
import appdaemon.plugins.hass.hassapi as hass
from enum import Enum

from libs.machine import Machine, ANY, StateIs, Timeout

class States(Enum):
    IDLE = 1
    MAYBE_IDLE = 10
    MAYBE_WASHING = 11
    PRE_WASH = 2
    MAIN_WASH = 3
    WATER_CLEANING = 4
    FINAL_WASH = 5
    DRYING = 6
    MAYBE_DONE = 70
    DONE = 7

IDLE = States.IDLE
MAYBE_IDLE = States.MAYBE_IDLE
MAYBE_WASHING = States.MAYBE_WASHING
PRE_WASH = States.PRE_WASH
MAIN_WASH = States.MAIN_WASH
WATER_CLEANING = States.WATER_CLEANING
FINAL_WASH = States.FINAL_WASH
DRYING = States.DRYING
MAYBE_DONE = States.MAYBE_DONE
DONE = States.DONE

POWER_SENSOR = "sensor.dishwasher"
OUTPUT_ENTITY = "sensor.dishwasher_2"

class PowerState(StateIs):
    def __init__(self, name):
        super().__init__(POWER_SENSOR, self.test_predicate)
        self.name = name
    
    def __str__(self):
        return self.name
    
    def test_predicate(self, new):
        return new.lower() == self.name.lower()

state_is_idle = lambda: PowerState("idle")
state_is_washing = lambda: PowerState("washing")
state_is_drying = lambda: PowerState("drying")

class Dishwasher(hass.Hass):
    def initialize(self):
        machine = Machine(self, States, initial=IDLE, entity=OUTPUT_ENTITY)
        machine.add_transitions()
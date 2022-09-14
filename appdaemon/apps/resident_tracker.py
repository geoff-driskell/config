from operator import add, sub

import appdaemon.plugins.hass.hassapi as hass


class ResidentTracker(hass.Hass):
    def initialize(self):
        self.n_residents = 0
        self.map = {}

        for resident_id in self.args["residents"]:
            tracker = self.get_state(resident_id, attribute="source")
            self.log(f"tracking {resident_id} via {tracker}")
            self.map[tracker] = resident_id
            self.listen_state(
                self.resident_arrived, tracker, old="not_home", new="home"
            )
            self.listen_state(
                self.resident_departed, tracker, old="home", new="not_home"
            )

    def resident_arrived(self, entity, attribute, old, new, kwargs):
        entity = self.map[entity]
        if self.n_residents == 0:
            self.house_became_occupied(entity)
        self.n_residents += 1
        self.log(f"firing resident_arrived with person={entity}")
        self.fire_event("resident_arrived", person=entity)

    def house_became_occupied(self, entity):
        self.log(f"firing house_became_occupied with person={entity}")
        self.fire_event("house_became_occupied", person=entity)

    def resident_departed(self, entity, attribute, old, new, kwargs):
        entity = self.map[entity]
        self.n_residents -= 1
        self.log(f"firing resident_departed with person={entity}")
        self.fire_event("resident_departed", person=entity)
        if self.n_residents == 0:
            self.house_became_vacant(entity)

    def house_became_vacant(self, entity):
        self.log(f"firing house_became_vacant with person={entity}")
        self.fire_event("house_became_vacant", person=entity)
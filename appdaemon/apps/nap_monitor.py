import appdaemon.plugins.hass.hassapi as hass
#
# App to send notification when a door left open for too long
#
# Args: (set these in appdaemon.cfg)
# ttl = # of seconds to wait until notified
#
#
# EXAMPLE appdaemon.cfg entry below
# 
# # Apps
# 
# [door_notifications]
# module = door_notifications
# class = DoorMonitor
# ttl = 15
#

class NapMonitor(hass.Hass):

    def initialize(self):
        self.naptime_entities = ['input_boolean.avery_naptime', 'input_boolean.benjamin_naptime']

        self.sleep_timer_library = {}

        for child in self.naptime_entities:
            self.listen_state(self.tracker, entity=child)

    def tracker(self, entity, attribute, old, new, kwargs):

        try:
            self.cancel_timer(self.sleep_timer_library[entity])
        except KeyError:
            self.log('Tried to cancel the sleep timer for {}, but none existed!'.format(entity), 
                     level='DEBUG')

        if new == 'on':
            if self.now_is_between("08:00:00", "17:00:00"):
                self.sleep_timer_library[entity] = self.run_in(self.notifier, 
                                                          int(self.args['max_nap_seconds']), 
                                                          entity_name=entity)
            else:
                self.sleep_timer_library[entity] = self.run_in(self.notifier, 
                                                          int(self.args['max_bed_seconds']), 
                                                          entity_name=entity)

    def notifier(self, kwargs):
        friendly_name = self.get_state(kwargs['entity_name'], attribute='friendly_name')

        title = "Message from HASS!"
        message = "{} has been open for more than {} seconds.".format(friendly_name,
                                                                      self.args['max_nap_seconds'])

        self.call_service('notify/notify', title=title, message=message)
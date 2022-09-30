from concurrent.futures import thread
import appdaemon.plugins.hass.hassapi as hass
from queue import Queue
import sys
from threading import Thread
from threading import Event
import time

class Sound(hass.Hass):
    def initialize(self):
        self.queue = Queue(maxsize=0)

        t = Thread(target=self.worker)
        t.daemon = True
        t.start()

        self.event = Event()

    def worker(self):
        active = True
        while active:
            try:
                data = self.queue.get()
                if data["type"] == "terminate":
                    active = False
                else:
                    # Save the current volume of the Sonos
                    self.call_service("sonos/snapshot", entity_id=self.args["player"])
                    self.call_service("media_player/unjoin", entity_id=self.args["player"])
                    # Set the desired volume
                    self.call_service("media_player/volume_set", entity_id=self.args["player"], volume_level=data["volume"],)
                    if data["type"] == "tts":
                        # Call tts service
                        self.call_service("tts/amazon_polly_say", entity_id=self.args["player"], message="<speak><break time='1s'/>'{}'</speak>".format(data["text"]),)
                    if data["type"] == "play":
                        netpath = netpath = "http://{}:{}/local/{}/{}".format(self.args["ip"], self.args["port"], self.args["base"], data["path"],)
                        self.call_service("media_player/play_media", entity_id=self.args["player"], media_content_id=netpath, media_content_type=data["content"],)
                    time.sleep(int(data["length"]))
                    self.call_service("sonos/restore", entity_id=self.args["player"],)
                    #self.set_state(self.args["player"], attributes={"volume_level": volume})
            except Exception:
                self.log("Error")
                self.log(sys.exc_info())
            
            self.queue.task_done()
        
        self.log("Worker thread exiting")
        self.event.set()
    
    def tts(self, text, volume, length):
        self.queue.put({"type": "tts", "text": text, "volume": volume, "length": length})
    
    def play(self, path, content, volume, length):
        self.queue.put({"type": "play", "path": path, "content": content, "volume": volume, "length": length})
    
    def terminate(self):
        self.event.clear()
        self.queue.put({"type": "terminate"})
        self.event.wait()
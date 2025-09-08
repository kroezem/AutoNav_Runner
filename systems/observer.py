import os, base64, time, threading
from queue import Queue
from picamera2 import Picamera2
from PIL import Image
from openai import OpenAI

client = OpenAI(
    api_key="KEY_GOES_HERE")
SAVE_DIR = "captures"
MODEL_NAME = "gpt-4o"


class ImageRecognizer:
    def __init__(self, output_queue: Queue):
        self.cam = None
        self.output_queue = output_queue
        self.stop_event = threading.Event()
        self.thread = None
        self.is_running = False
        self.status = 'off'
        os.makedirs(SAVE_DIR, exist_ok=True)

    def _describe_image(self, path: str) -> str | None:
        try:
            small_path = os.path.join(SAVE_DIR, "capture_small.jpg")
            with Image.open(path) as im:
                im = im.rotate(-90, expand=True)
                im.resize((640, 480)).save(small_path, "JPEG", quality=25)

            with open(small_path, "rb") as f:
                b64_image = base64.b64encode(f.read()).decode()
            data_uri = f"data:image/jpeg;base64,{b64_image}"
            resp = client.chat.completions.create(model=MODEL_NAME, messages=[
                {"role": "system", "content": "You describe images for visually-impaired users."},
                {"role": "user", "content": [
                    {"type": "text",
                     "text": "Act as a mobility assistant. Describe obstacles and their approximate distances in meters. Use one crisp sentence per obstacle; max 50 words total. Exclude emotional tone."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_uri}}]}],
                                                  max_tokens=100, temperature=0.5)

            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Recognizer] Error describing image: {e}")
            return None

    def _recognition_loop(self):
        try:
            self.status = 'initializing'
            self.cam = Picamera2()
            self.cam.configure(self.cam.create_still_configuration())
            self.cam.start()
            time.sleep(2.0)
            self.status = 'ok'
            while not self.stop_event.is_set():
                capture_path = os.path.join(SAVE_DIR, "capture.jpg")
                self.cam.capture_file(capture_path)
                description = self._describe_image(capture_path)
                if description: self.output_queue.put(description)
                for _ in range(100):
                    if self.stop_event.is_set(): break
                    time.sleep(0.1)
        except Exception as e:
            print(f"[Recognizer] FATAL ERROR: {e}")
            self.status = 'error'
        finally:
            self.cleanup_resources()

    def start(self):
        if self.is_running: return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._recognition_loop)
        self.thread.start()
        self.is_running = True

    def stop(self):
        if not self.is_running: return
        self.stop_event.set()
        if self.thread: self.thread.join()
        self.is_running = False

    def cleanup_resources(self):
        if self.cam: self.cam.stop(); self.cam.close(); self.cam = None
        self.status = 'off'

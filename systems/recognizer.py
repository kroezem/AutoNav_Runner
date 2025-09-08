# systems/recognizer.py  – caption + TTS in one subsystem
import os, time, base64, io, traceback
from queue import Queue, Empty
from PIL import Image
from openai import OpenAI
from systems.subsystem import Subsystem

SAVE_DIR = "captures"
MODEL_NAME = "gpt-4o"

client = OpenAI(
    api_key="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")


class ImageRecognizer(Subsystem):
    def __init__(self, state, in_q: Queue):
        super().__init__(state, name="recognizer")
        self.in_q = in_q
        os.makedirs(SAVE_DIR, exist_ok=True)

    # ----------------------------------------------------
    def init_hardware(self):  # nothing to init
        pass

    def loop(self):
        try:
            frame = self.in_q.get(timeout=0.1)  # ndarray / PIL.Image / path
        except Empty:
            return

        try:
            jpg_path = self._to_jpg(frame)
            caption = self._describe(jpg_path)
            audio_b64 = self._speech_mp3(caption) if caption else ""

            self.publish(status="running",
                         caption=caption or "",
                         mp3=audio_b64,
                         ts=time.time())
        except Exception as e:
            self.publish(status="error", error=str(e))
            traceback.print_exc()

    # ----------------------------------------------------
    def _to_jpg(self, src) -> str:
        if isinstance(src, str):
            return src  # already a path

        if not isinstance(src, Image.Image):
            src = Image.fromarray(src)

        fname = os.path.join(SAVE_DIR, f"{int(time.time() * 1e3)}.jpg")
        src.save(fname, "JPEG", quality=90)
        return fname

    def _describe(self, path: str) -> str:
        # resize + compress for bandwidth
        with Image.open(path) as im:
            im.rotate(-90, expand=True).resize((640, 480)).save(path, "JPEG", quality=25)

        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        data_uri = f"data:image/jpeg;base64,{b64}"

        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system",
                 "content": "You describe images for visually-impaired users."},
                {"role": "user",
                 "content": [
                     {"type": "text",
                      "text": "Act as a mobility assistant. Describe obstacles "
                              "and their approximate distances in metres. "
                              "One crisp sentence per obstacle, max 50 words. "
                              "No emotion."},
                     {"type": "image_url",
                      "image_url": {"url": data_uri}}
                 ]}
            ],
            max_tokens=100, temperature=0.5
        )
        print(resp.choices[0].message.content.strip())
        return resp.choices[0].message.content.strip()

    def _speech_mp3(self, text: str) -> str:
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        mp3_bytes = response.content
        b64 = base64.b64encode(mp3_bytes).decode()
        return f"data:audio/mpeg;base64,{b64}"

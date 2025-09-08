# vpr.py – VPR subsystem with top-k output only
import os, threading, json, time, torch, torch.nn.functional as F
import timm
from PIL import Image
from collections import deque, defaultdict
from systems.subsystem import Subsystem

MODEL_NAME = "efficientnet_b0"
EMBED_FILE = "assets/heading_embeddings.json"
FRAME_DT = 0.01
AVG_WINDOW = 3
TOP_K = 5


class VPRSystem(Subsystem):
    def __init__(self, state, name="vpr"):
        super().__init__(state, name)
        self._image = None
        self._lock = threading.Lock()
        self._top_k = [("", 0.0)] * TOP_K
        self.publish(top_regions=self._top_k)

    # ── external frame input ────────────────────────────────────
    def set_image(self, image):
        if image is None:
            return
        with self._lock:
            self._image = image.copy()

    # ── hardware / model init ──────────────────────────────────
    def init_hardware(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=0
                                       ).to(self.device).eval()
        cfg = timm.data.resolve_model_data_config(self.model)
        self.tf = timm.data.create_transform(**cfg, is_training=False)

        with open(EMBED_FILE) as f:
            data = json.load(f)

        vecs, regions = [], []
        for r, entries in sorted(data.items()):
            for e in entries:
                vecs.append(e["vec"])
                regions.append(r)

        self.db_vecs = F.normalize(torch.tensor(vecs, dtype=torch.float32),
                                   p=2, dim=1).to(self.device)
        self.regions = regions
        self.pred_hist = deque(maxlen=AVG_WINDOW)

    # ── main loop ──────────────────────────────────────────────
    def loop(self):
        if self._image is None:
            time.sleep(FRAME_DT)
            return

        with self._lock:
            img, self._image = self._image, None

        with torch.no_grad():
            vec = self.model(self.tf(img).unsqueeze(0).to(self.device))
            vec = F.normalize(vec, p=2, dim=1)

        sims = torch.mm(vec, self.db_vecs.T).squeeze(0)
        confs, idxs = torch.topk(sims, TOP_K)  # top-k cosine sims
        frame_top = [(self.regions[i], confs[j].item())
                     for j, i in enumerate(idxs.cpu().tolist())]

        self.pred_hist.append(frame_top)

        # aggregate over rolling window
        acc: dict[str, list[float]] = defaultdict(list)
        for frame in self.pred_hist:
            for r, c in frame:
                acc[r].append(c)
        mean_conf = {r: sum(v) / len(v) for r, v in acc.items()}
        ordered = sorted(mean_conf.items(), key=lambda x: x[1], reverse=True)[:TOP_K]

        with self._lock:
            self._top_k = ordered

        self.publish(top_regions=self._top_k)
        # time.sleep(FRAME_DT)

    # ── accessor ───────────────────────────────────────────────
    def get_top_regions(self):
        with self._lock:
            return list(self._top_k)  # deep-copy for thread safety

    def clear(self):
        with self._lock:
            self._top_k = [("", 0.0)] * TOP_K
        self.publish(top_regions=self._top_k)  # <-- this line was missing

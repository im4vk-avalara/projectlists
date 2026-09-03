"""
Long-term semantic memory for the AIOS host bridge.

TurboVec (Rust vector index, TurboQuant 4-bit compression) stores embeddings of
past exchanges; sentence-transformers (all-MiniLM-L6-v2, ~90 MB, local after
the first download) produces them. Fully offline -- no API key, no cloud.

TurboVec stores only vectors and returns numeric ids, so a JSONL sidecar maps
id -> original text. Both files live under the memory dir and survive bridge
restarts -- this is the long-term layer; per-session HISTORY in bridge.py stays
the short-term one.
"""
import json
import os
import sys

import numpy as np

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Cosine scores below this are noise (MiniLM rarely ranks a true match under
# ~0.35); injecting them would just distract the model.
RECALL_MIN_SCORE = 0.30


class Memory:
    def __init__(self, dirpath):
        from sentence_transformers import SentenceTransformer
        from turbovec import IdMapIndex

        os.makedirs(dirpath, exist_ok=True)
        self.index_path = os.path.join(dirpath, "index.tvim")
        self.texts_path = os.path.join(dirpath, "texts.jsonl")

        print(f"[memory] loading embedding model {EMBED_MODEL} ...", file=sys.stderr)
        self.model = SentenceTransformer(EMBED_MODEL)
        dim = self.model.get_embedding_dimension()

        self.texts = {}
        if os.path.exists(self.index_path) and os.path.exists(self.texts_path):
            self.index = IdMapIndex.load(self.index_path)
            with open(self.texts_path) as f:
                for line in f:
                    rec = json.loads(line)
                    self.texts[rec["id"]] = rec["text"]
            print(f"[memory] recalled {len(self.texts)} records from {dirpath}",
                  file=sys.stderr)
        else:
            self.index = IdMapIndex(dim=dim, bit_width=4)
        self.next_id = max(self.texts) + 1 if self.texts else 0

    def _embed(self, texts):
        return self.model.encode(texts, normalize_embeddings=True).astype(np.float32)

    def add(self, text):
        i = self.next_id
        self.next_id += 1
        self.index.add_with_ids(self._embed([text]), np.array([i], dtype=np.uint64))
        self.texts[i] = text
        with open(self.texts_path, "a") as f:
            f.write(json.dumps({"id": i, "text": text}) + "\n")
        self.index.write(self.index_path)

    def recall(self, query, k=3):
        """Top-k past records relevant to `query`, as (score, text) pairs."""
        n = len(self.texts)
        if n == 0:
            return []
        scores, ids = self.index.search(self._embed([query]), k=min(k, n))
        return [(float(s), self.texts[int(i)])
                for s, i in zip(scores[0], ids[0])
                if float(s) >= RECALL_MIN_SCORE and int(i) in self.texts]

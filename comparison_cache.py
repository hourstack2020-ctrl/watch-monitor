"""Bounded process-local comparison response cache; no client data persisted."""
import gzip
import json
import threading
import time

class ComparisonResponseCache:
    def __init__(self,ttl=60):
        self.ttl=ttl
        self.lock=threading.Lock()
        self.key=None
        self.expires=0
        self.payload=None

    def get(self,key,build):
        with self.lock:
            if self.key==key and self.payload is not None and time.monotonic()<self.expires:
                return self.payload,True
            result=build()
            # The web list/export uses groups. Pairwise items repeat the same
            # product many times and are only needed by internal alert callers.
            result={k:v for k,v in result.items() if k not in {'items','image_review','review_pairs'}}
            raw=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
            payload=(raw,gzip.compress(raw,compresslevel=4,mtime=0))
            self.key=key
            self.payload=payload
            self.expires=time.monotonic()+self.ttl
            return payload,False

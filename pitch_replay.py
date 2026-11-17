"""Replays a stretch of a recorded call in real time, the way meetcap would deliver it live, to test the pitch
timer without a call.

    .venv/bin/python pitch_replay.py "<meeting folder>" <from seconds> <seconds> "<out folder>"

Prints "lv <them> <me>" five times a second and appends the call side to <out>/them-live.raw as it goes.
Face menu doesn't use this; meetings.lua's M.pitchReplay does.
"""
import os
import sys
import time
import wave

import numpy as np

src, start, length, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
RATE, STEP = 16000, 0.2


def load(name):
    with wave.open(os.path.join(src, name)) as w:
        w.setpos(int(start * RATE))
        return np.frombuffer(w.readframes(int(length * RATE)), np.int16)


them, me = load("them.wav"), load("me_clean.wav" if os.path.exists(os.path.join(src, "me_clean.wav")) else "me.wav")
n = int(STEP * RATE)
t0 = time.time()
with open(os.path.join(out, "them-live.raw"), "wb") as live:
    for k in range(0, min(len(them), len(me)) // n):
        a, b = them[k * n:(k + 1) * n], me[k * n:(k + 1) * n]
        live.write(a.tobytes()); live.flush()
        rms = lambda x: float(np.sqrt(np.mean((x.astype(np.float32) / 32768) ** 2)))
        print(f"lv {rms(a):.5f} {rms(b):.5f}", flush=True)
        time.sleep(max(0, t0 + (k + 1) * STEP - time.time()))

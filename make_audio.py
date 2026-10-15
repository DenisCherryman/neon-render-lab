import math
import random
import struct
import wave

random.seed(7)
rate = 32000
seconds = 3.10
shots = [16/24, 24/24, 30/24, 44/24, 50/24, 55/24]
samples = []

for i in range(round(rate * seconds)):
    t = i / rate
    signal = (
        0.08 * math.sin(2 * math.pi * 55 * t)
        + 0.034 * math.sin(2 * math.pi * 110 * t)
    ) * math.sin(math.pi * min(t / 2.8, 1))
    signal += 0.014 * random.uniform(-1, 1)

    for shot in shots:
        a = t - shot
        if 0 <= a < 0.22:
            crack = random.uniform(-1, 1) * math.exp(-96 * a)
            bass = math.sin(2 * math.pi * (90 - 45 * a) * a)
            signal += 0.51 * math.exp(-27 * a) * bass + 0.46 * crack

    samples.append(int(max(-1, min(1, signal)) * 32767))

with wave.open("action.wav", "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(rate)
    audio.writeframes(struct.pack("<" + "h" * len(samples), *samples))

print("Generated action.wav")

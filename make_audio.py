import math
import random
import struct
import wave

random.seed(7)
rate = 32000
seconds = 15.0
shots = [(17-1)/24,(32-1)/24,(48-1)/24,(65-1)/24,(80-1)/24,(99-1)/24,(115-1)/24,(133-1)/24,(147-1)/24,(166-1)/24,(179-1)/24,(193-1)/24,(212-1)/24,(227-1)/24,(244-1)/24,(259-1)/24,(277-1)/24,(302-1)/24,(321-1)/24,(341-1)/24]
samples = []

for i in range(round(rate * seconds)):
    t = i / rate
    # moody synth bed
    signal = (
        0.095 * math.sin(2 * math.pi * 48 * t)
        + 0.025 * math.sin(2 * math.pi * 96 * t)
        + 0.014 * math.sin(2 * math.pi * 190 * t)
    ) * (0.7 + 0.3*math.sin(2*math.pi*t/7.5))
    signal += 0.01 * random.uniform(-1, 1)

    # rain / city hiss
    signal += 0.006 * random.uniform(-1, 1)

    for shot in shots:
        a = t - shot
        if 0 <= a < 0.26:
            crack = random.uniform(-1, 1) * math.exp(-110 * a)
            body = math.sin(2 * math.pi * (100 - 58 * a) * a)
            tail = math.sin(2 * math.pi * 18 * a) * math.exp(-5*a)
            signal += 0.56 * crack + 0.52 * math.exp(-22*a) * body + 0.20 * tail
        if 0 <= a < 0.09:
            signal += 0.08 * math.sin(2 * math.pi * 1400 * a) * math.exp(-40*a)

    # subtle whooshes during camera movement
    sweep = abs(math.sin(2*math.pi*(t/3.4)))
    signal += 0.021 * sweep * random.uniform(-1, 1)

    samples.append(int(max(-1, min(1, signal)) * 32767))

with wave.open('action.wav', 'wb') as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(rate)
    audio.writeframes(struct.pack('<' + 'h' * len(samples), *samples))

print('Generated action.wav')

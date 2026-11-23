# neon-render-lab

15-second cinematic Cyberpunk Blender scene: 1280×720, 24 fps, 360 frames.

## Scene V5: cinematic action

- Eight camera beats with fast lateral movement, over-the-shoulder angles, whip pans and close-up shots.
- Two actors follow choreographed paths with advances, retreats and dodges; blend imported run animation when available.
- Balanced cyan/magenta neon, moving light pulses, reflective wet-ground patches, aimed muzzle flashes and impact lights without the blown-out V5 preview.
- Twenty reciprocal shot events synced frame-by-frame, with visible directed beams, impact bursts and hit reactions. Both actors face one another and their weapons actively track the opponent. Synthetic mono 32 kHz 16-bit WAV lasts exactly 15 seconds.
- CC0 Poly Haven surfaces and original Soldier.glb import still used. Keep this PR in draft until visual inspection.

## Validation before a full render

Pull requests run offline regression checks, audio generation and preview frames:
`1,17,18,32,33,48,65,81,115,147,193,212,227,244,259,302,341,360`. These samples include exact shot frames and impact reactions.
Manual Actions runs default to `preview`; select `full` explicitly for the full 360-frame render.
Pushes to `main` retain full-render behavior.

Local commands, from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 make_audio.py
python3 verify_outputs.py audio
PREVIEW_FRAMES=1,17,18,32,33,48,65,81,115,147,193,212,227,244,259,302,341,360 xvfb-run -a -s "-screen 0 1280x720x24" blender -b -t 3 --python-exit-code 1 -P render.py
python3 verify_outputs.py preview
```

Inspect *all camera cuts*, imported run animation, skin/props, puddles,
muzzle flashes, weapon grip, tracer direction, highlight detail and both actors.
Watch for black frames or clipping caused by close camera moves.

The full workflow checks all 360 PNG headers and dimensions, WAV sample count,
MP4 dimensions/FPS/decoded frame count/duration, and decodes both MP4 streams.
Expected full artifact: `Cyberpunk_Cloud_3D_Cinematic_15s` with MP4, WAV and V5 .blend.

## Assets and reproducibility

Poly Haven surface maps are required. Downloads validate imagery before publishing
cache files and try 2K/1K JPG/PNG candidates. Cached Soldier.glb validates GLB header
and size. `pack_all` runs before saving V5 .blend.

Reopen the saved blend without original assets to confirm portability.
Blender installed via Ubuntu 24.04 apt and the three.js/master model are not pinned
to exact revisions. Fix those after visual acceptance. Timeout is **150 minutes**,
not a guaranteed render time. Full render could take longer than prior V4's
240-frame run; **do not run full until preview has been reviewed**.

Legacy 3-second workflows remain archived; do not reactivate them.

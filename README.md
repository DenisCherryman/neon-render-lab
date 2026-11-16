# neon-render-lab

10-second Cyberpunk Blender scene: 1280x720, 24 fps, 240 frames.

## Validation before a full render

Pull requests run offline regression checks, generate and validate audio, and
render ten preview frames: 1, 31–34, 45–48, 240. Manual Actions runs default to
preview; select full explicitly for all frames. Pushes to main retain the
existing full-render behavior.

Local commands, from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 make_audio.py
python3 verify_outputs.py audio
PREVIEW_FRAMES=1,31,32,33,34,45,46,47,48,240 xvfb-run -a -s "-screen 0 1280x720x24" blender -b -t 3 --python-exit-code 1 -P render.py
python3 verify_outputs.py preview
```

Inspect texture tiling, weapon grip, tracer direction, muzzle flashes and both
actors. Listen to action.wav: it is synthesized mono PCM, not recorded gunshots.
The first shot starts at 31/24 seconds and the last at 213/24 seconds.
Offline tests compare all audio shot times against the visual event list.

The full workflow checks PNG filenames, headers and dimensions; validates WAV
sample count and format; probes the MP4 dimensions, FPS, decoded frame count,
audio and duration; then fully decodes the video and audio streams.

## Assets and reproducibility

Poly Haven surface maps are required. Downloads use temporary files, validate
images before publishing them to the cache, and try available 2K/1K JPG/PNG
candidates. A missing required map fails explicitly. A cached Soldier.glb is
checked for its GLB header and declared size before import.

The scene calls pack_all before saving. Reopen the saved blend without the
original assets directory to confirm portability; this is still a manual check.

Blender is installed from Ubuntu 24.04 packages and its version is logged.
Soldier.glb still references three.js/master. Pin an actually validated Blender
version and model revision after a successful preview, rather than guessing.
The 85-minute timeout is a limit, not a measured completion-time guarantee.

Legacy 3-second workflows are archived under archive/workflows and must not be
activated: they overwrite the current Python source with embedded old code.

## Review status

These changes were prepared through the GitHub API because local execution was
unavailable. No local Python, Blender, audio listening, or render validation was
performed. Check the pull request Actions run and inspect its artifacts before
treating materials, sound or the full render as verified.

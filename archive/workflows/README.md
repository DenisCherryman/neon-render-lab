# Archived 3-second workflow

render_v3.yml is the unchanged legacy workflow from .github/render_v3.yml.
The identical copy previously at
.github/workflows/.github/workflows/render.yml was removed.

Do not move this file into .github/workflows: it overwrites render.py and
make_audio.py with embedded older code, renders 72 frames and assembles 3 seconds.

The current 10-second workflow is .github/workflows/render.yml.

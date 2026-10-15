import bpy
import math
import random
import os
from mathutils import Vector
from urllib.request import urlretrieve

random.seed(72)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for m in list(bpy.data.materials):
    bpy.data.materials.remove(m)

scene = bpy.context.scene
scene.render.resolution_x = 720
scene.render.resolution_y = 406
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 72
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = os.path.abspath("./frames/frame_")
scene.render.film_transparent = False

try:
    scene.view_settings.view_transform = "AgX"
except (ValueError, TypeError):
    scene.view_settings.view_transform = "Standard"

scene.render.engine = (
    "BLENDER_EEVEE_NEXT"
    if bpy.app.version >= (4, 2, 0)
    else "BLENDER_EEVEE"
)
if hasattr(scene, "eevee"):
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16
    if hasattr(scene.eevee, "use_bloom"):
        scene.eevee.use_bloom = True

scene.world.color = (0.012, 0.017, 0.035)


def material(name, color, metal=0, rough=0.43, glow=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Metallic"].default_value = metal
    bs.inputs["Roughness"].default_value = rough
    if glow:
        em = bs.inputs.get("Emission Color")
        if em is None:
            em = bs.inputs.get("Emission")
        strength = bs.inputs.get("Emission Strength")
        if em is not None:
            em.default_value = (*color, 1)
        if strength is not None:
            strength.default_value = glow
    return m


asphalt = material("Wet asphalt", (.016, .019, .026), .4, .17)
chassis = material("Midnight metal", (.027, .035, .051), .84, .28)
cyan = material("Cyan neon", (.006, .7, 1), .12, .1, 6)
pink = material("Pink neon", (1, .01, .33), .1, .16, 5)
warm = material("Warm flash", (1, .42, .03), .03, .2, 4)


def cube(name, location, dimensions, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(
        location=False, rotation=False, scale=True
    )
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Soft edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new("Normals", "WEIGHTED_NORMAL")
    return obj


cube("Street", (0, 0, -.08), (24, 34, .13), asphalt)

for side in (-1, 1):
    for i in range(14):
        x = side * (5 + random.random() * 4)
        y = -16 + i * 2.6
        height = 3.2 + random.random() * 11
        cube(
            "Building",
            (x, y, height * .5 - .02),
            (2 + random.random() * 2,
             2 + random.random() * 1.2,
             height),
            chassis,
        )
        for j in range(3):
            z = 1 + j * 1.8 + random.random() * .4
            if z < height - .5:
                cube(
                    "Office light",
                    (x - side * 1.37, y, z),
                    (.035, .95, .035),
                    cyan if (j + i) % 3 else pink,
                )

paint = material("Street paint", (.24, .27, .31), 0, .83)
for k in range(8):
    cube(
        "Crosswalk",
        (-3 + k * .85, 1, .018),
        (.5, 2.4, .012),
        paint,
    )


def area(name, color, power, position, radius):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.color = color
    data.shape = "DISK"
    data.size = radius
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (
        Vector((0, 0, 1.4)) - obj.location
    ).to_track_quat("-Z", "Y").to_euler()


area("Cyan key", (.02, .75, 1), 1600, (4, -2, 6), 6)
area("Magenta rim", (1, .04, .36), 1850, (-4, 2, 6), 6)
area("Warm backlight", (1, .53, .1), 1400, (0, 5, 7), 4)
area("Fill", (.25, .32, .9), 600, (0, -5, 4), 9)

os.makedirs("assets", exist_ok=True)
model = os.path.abspath("assets/Soldier.glb")
url = (
    "https://raw.githubusercontent.com/mrdoob/three.js/"
    "master/examples/models/gltf/Soldier.glb"
)
if not os.path.exists(model):
    urlretrieve(url, model)
if os.path.getsize(model) < 50000:
    raise RuntimeError("Character download failed")

characters = []
for idx in range(2):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=model)
    imported = set(bpy.data.objects) - before
    rig = next(
        (obj for obj in imported if obj.type == "ARMATURE"),
        None,
    )
    if rig is None:
        raise RuntimeError("Character armature missing")

    root = bpy.data.objects.new("Actor " + str(idx + 1), None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        if obj.parent not in imported:
            matrix = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = matrix

    root.location = (
        -2.1 if idx == 0 else 2.1,
        .15 if idx == 0 else 1.3,
        .04,
    )
    root.rotation_euler.z = -.19 if idx == 0 else math.pi + .24

    for obj in imported:
        if obj.type == "MESH":
            for polygon in obj.data.polygons:
                polygon.use_smooth = True

    if rig.animation_data:
        tracks = rig.animation_data.nla_tracks
        for track in tracks:
            track.mute = "idle" not in track.name.lower()
        if len(tracks) and all(track.mute for track in tracks):
            tracks[0].mute = False

    characters.append((root, rig))


def weapon_for(rig, index):
    names = [bone.name for bone in rig.data.bones]
    candidates = [
        name for name in names
        if ("right" in name.lower() or name.lower().endswith(".r"))
        and "hand" in name.lower()
    ]
    if not candidates:
        candidates = [name for name in names if "hand" in name.lower()]
    hand = candidates[0] if candidates else None
    print("Hand bone:", hand)

    anchor = bpy.data.objects.new("Weapon " + str(index), None)
    bpy.context.collection.objects.link(anchor)
    anchor.parent = rig
    if hand:
        anchor.parent_type = "BONE"
        anchor.parent_bone = hand
        anchor.location = (0, .04, .02)
        anchor.rotation_euler = (math.radians(90), 0, 0)
    else:
        anchor.location = (0, -.15, 1.25)

    parts = [
        ("Receiver", (.13, .30, .12), (0, .10, 0), chassis, .017),
        ("Grip", (.085, .09, .23), (0, -.09, -.13), asphalt, .012),
        ("Barrel", (.075, .25, .07), (0, .34, .012), chassis, .007),
        ("Neon slot", (.025, .18, .012), (0, .20, .07), cyan, .004),
    ]
    for name, dimensions, position, mat, bevel in parts:
        obj = cube(name, (0, 0, 0), dimensions, mat, bevel)
        obj.parent = anchor
        obj.location = position
    return anchor


weapons = [
    weapon_for(rig, index)
    for index, (_, rig) in enumerate(characters)
]

events = [(17, 0), (25, 0), (31, 1), (45, 0), (51, 1), (56, 0)]
shots = [frame for frame, actor in events]

for index, weapon in enumerate(weapons):
    actor_shots = [frame for frame, actor in events if actor == index]
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=14, ring_count=8, radius=.1
    )
    muzzle = bpy.context.object
    muzzle.name = "Muzzle flash"
    muzzle.parent = weapon
    muzzle.location = (0, .49, .012)
    muzzle.data.materials.append(warm)
    for frame in range(1, 73):
        distance = min(abs(frame - shot) for shot in actor_shots)
        scale = 1.5 if distance == 0 else (.6 if distance == 1 else .001)
        muzzle.scale = (scale, scale, scale)
        muzzle.keyframe_insert(data_path="scale", frame=frame)

brass = material("Brass", (.55, .29, .075), .85, .22)
for shot, actor in events:
    scene.frame_set(shot)
    bpy.context.view_layer.update()
    start = weapons[actor].matrix_world @ Vector((.08, .15, .02))
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=.014, depth=.065
    )
    casing = bpy.context.object
    casing.name = "Spent casing"
    casing.data.materials.append(brass)
    velocity = Vector((.5 if actor == 0 else -.5, -.8, 1.2))

    for frame in range(1, 73):
        visible = frame >= shot
        casing.scale = (1, 1, 1) if visible else (.001, .001, .001)
        casing.keyframe_insert(data_path="scale", frame=frame)
        t = max(0, (frame - shot) / 24)
        position = start + velocity * t + Vector((0, 0, -4.905 * t * t))
        position.z = max(.035, position.z)
        casing.location = position
        casing.rotation_euler = (t * 7, t * 11, t * 9)
        casing.keyframe_insert(data_path="location", frame=frame)
        casing.keyframe_insert(data_path="rotation_euler", frame=frame)

bpy.ops.object.camera_add(location=(0, -8.7, 3.4))
camera = bpy.context.object
scene.camera = camera
camera.data.lens = 35

for frame in range(1, 73):
    phase = (frame - 1) / 72
    pan = math.sin(phase * math.pi * .95)
    base = Vector((
        pan,
        -8.4 + phase,
        3 + .17 * math.sin(phase * math.pi * 2),
    ))
    shake = Vector((0, 0, 0))
    for shot in shots:
        elapsed = frame - shot
        if 0 <= elapsed <= 8:
            amplitude = .11 * math.exp(-elapsed / 2.7)
            shake += Vector((
                math.sin(elapsed * 6.2 + shot) * amplitude,
                math.sin(elapsed * 9.4) * amplitude * .35,
                math.cos(elapsed * 5.6) * amplitude,
            ))
    camera.location = base + shake
    camera.rotation_euler = (
        Vector((0, .6, 1.43)) - camera.location
    ).to_track_quat("-Z", "Y").to_euler()
    camera.keyframe_insert(data_path="location", frame=frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=frame)

scene.frame_set(1)
os.makedirs("frames", exist_ok=True)
bpy.ops.wm.save_as_mainfile(
    filepath=os.path.abspath("CYBERPUNK_CLOUD_EXPERIMENT.blend")
)
bpy.ops.render.render(animation=True)

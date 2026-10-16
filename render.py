"""Cyberpunk cloud render V4
10-second Blender Eevee firefight using free CC0 textures where available.
Textures are attempted from Poly Haven's free/CC0 CDN; if unavailable, the script falls back to procedural materials.
Run with: blender -b -P render.py
"""
import bpy
import math
import os
import random
import json
from urllib.request import urlopen, urlretrieve, Request
from urllib.error import URLError, HTTPError
from mathutils import Vector

random.seed(42)
FPS = 24
DURATION = 10
TOTAL_FRAMES = FPS * DURATION
RES_X = 1280
RES_Y = 720
SHOT_EVENTS = [
    (32,0),(46,1),(60,0),(72,1),(95,0),(106,0),
    (122,1),(138,0),(160,1),(176,1),(196,0),(214,1)
]

# ---------------- Scene setup ----------------

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)
    for block in list(bpy.data.images):
        if block.users == 0:
            bpy.data.images.remove(block)

clear_scene()
scene = bpy.context.scene
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = TOTAL_FRAMES
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.filepath = os.path.abspath('./frames/frame_')
scene.render.film_transparent = False
try:
    scene.view_settings.view_transform = 'AgX'
except Exception:
    scene.view_settings.view_transform = 'Standard'
scene.render.engine = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (4,2,0) else 'BLENDER_EEVEE'
if hasattr(scene, 'eevee'):
    if hasattr(scene.eevee, 'taa_render_samples'):
        scene.eevee.taa_render_samples = 32
    if hasattr(scene.eevee, 'use_gtao'):
        scene.eevee.use_gtao = True
    if hasattr(scene.eevee, 'use_ssr'):
        scene.eevee.use_ssr = True
    if hasattr(scene.eevee, 'use_bloom'):
        scene.eevee.use_bloom = True
        scene.eevee.bloom_intensity = 0.08
scene.world.use_nodes = True
w_nodes = scene.world.node_tree.nodes
w_links = scene.world.node_tree.links
for n in list(w_nodes):
    w_nodes.remove(n)
bg = w_nodes.new('ShaderNodeBackground')
out = w_nodes.new('ShaderNodeOutputWorld')
texcoord = w_nodes.new('ShaderNodeTexCoord')
mapping = w_nodes.new('ShaderNodeMapping')
grad = w_nodes.new('ShaderNodeTexGradient')
ramps = w_nodes.new('ShaderNodeValToRGB')
ramps.color_ramp.elements[0].position = 0.22
ramps.color_ramp.elements[0].color = (0.01,0.02,0.05,1)
ramps.color_ramp.elements[1].position = 0.86
ramps.color_ramp.elements[1].color = (0.05,0.02,0.08,1)
bg.inputs['Strength'].default_value = 0.8
w_links.new(texcoord.outputs['Normal'], mapping.inputs['Vector'])
w_links.new(mapping.outputs['Vector'], grad.inputs['Vector'])
w_links.new(grad.outputs['Color'], ramps.inputs['Fac'])
w_links.new(ramps.outputs['Color'], bg.inputs['Color'])
w_links.new(bg.outputs['Background'], out.inputs['Surface'])

# ---------------- Utilities ----------------
ASSET_DIR = os.path.abspath('./assets')
os.makedirs(ASSET_DIR, exist_ok=True)


def fetch(url, path):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=25) as r, open(path, 'wb') as f:
        f.write(r.read())
    return path


def download_first(candidates, out_name):
    path = os.path.join(ASSET_DIR, out_name)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    for url in candidates:
        try:
            print('Trying texture', url)
            return fetch(url, path)
        except Exception as e:
            print('Texture download failed:', url, e)
    return None


def load_image(path, colorspace='sRGB'):
    if not path or not os.path.exists(path):
        return None
    img = bpy.data.images.load(path, check_existing=True)
    try:
        img.colorspace_settings.name = colorspace
    except Exception:
        pass
    return img


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m, nt, bsdf


def pbr_material(name, base_urls, rough_urls=None, normal_urls=None, metal=0.0,
                 fallback=(0.3,0.3,0.3,1.0), scale=3.0, emission=None):
    m, nt, bsdf = new_mat(name)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (scale, scale, scale)
    nt.links.new(tc.outputs['UV'], mp.inputs['Vector'])

    base = download_first(base_urls, name+'_base') if base_urls else None
    rough = download_first(rough_urls, name+'_rough') if rough_urls else None
    normal = download_first(normal_urls, name+'_normal') if normal_urls else None

    if base:
        img = load_image(base, 'sRGB')
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        bsdf.inputs['Base Color'].default_value = fallback

    if rough:
        img = load_image(rough, 'Non-Color')
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Roughness'])
    else:
        bsdf.inputs['Roughness'].default_value = 0.55

    if normal:
        img = load_image(normal, 'Non-Color')
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        nmap = nt.nodes.new('ShaderNodeNormalMap')
        nmap.inputs['Strength'].default_value = 0.7
        nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Color'], nmap.inputs['Color'])
        nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])

    bsdf.inputs['Metallic'].default_value = metal
    if emission:
        em = bsdf.inputs.get('Emission Color') or bsdf.inputs.get('Emission')
        st = bsdf.inputs.get('Emission Strength')
        if em is not None:
            em.default_value = emission
        if st is not None:
            st.default_value = 2.0
    return m


def procedural_neon(name, color):
    m, nt, bsdf = new_mat(name)
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 12
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.06
    nt.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Base Color'].default_value = (*color,1)
    bsdf.inputs['Roughness'].default_value = 0.18
    em = bsdf.inputs.get('Emission Color') or bsdf.inputs.get('Emission')
    st = bsdf.inputs.get('Emission Strength')
    if em is not None:
        em.default_value = (*color,1)
    if st is not None:
        st.default_value = 4.0
    return m


def cube(name, location, dimensions, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel > 0:
        mod = obj.modifiers.new('Bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
    return obj

# ---------------- Free texture materials ----------------
# Powered by Poly Haven. All downloaded surface maps are CC0.
def ph_material(name, asset, metal=0, scale=3):
    url = 'https://api.polyhaven.com/files/' + asset
    req = Request(url, headers={'User-Agent': 'NeonRenderLab/1.0 (personal Blender artwork)'})
    with urlopen(req, timeout=40) as response:
        data = json.load(response)
    def urls(channel):
        aliases = {'diff': ('diffuse', 'diff', 'albedo'), 'rough': ('rough', 'roughness'), 'nor_gl': ('nor_gl', 'normal')}
        key = next((k for k in aliases[channel] if k in data), None)
        if key is None:
            raise RuntimeError('Texture maps available: ' + str(list(data)))
        choices = data[key]
        for resolution in ('2k', '1k'):
            for fmt in ('jpg', 'png'):
                if fmt in choices.get(resolution, {}):
                    return [choices[resolution][fmt]['url']]
        raise RuntimeError('Missing texture channel: ' + asset + '/' + channel)
    result = pbr_material(name, urls('diff'), urls('rough'), urls('nor_gl'), metal=metal, scale=scale)
    for suffix in ('_base', '_rough', '_normal'):
        if not os.path.exists(os.path.join(ASSET_DIR, name + suffix)):
            raise RuntimeError('Required CC0 texture failed: ' + name + suffix)
    print('CC0 texture loaded:', asset, flush=True)
    return result
street_mat = ph_material('Street_CC0', 'asphalt_02', scale=8)
wall_mat = ph_material('Wall_CC0', 'concrete_floor_02', scale=6)
metal_mat = ph_material('Metal_CC0', 'rusty_painted_metal', metal=0.8, scale=2)
cyan_mat = procedural_neon('Cyan_Neon', (0.0, 0.78, 1.0))
magenta_mat = procedural_neon('Magenta_Neon', (1.0, 0.15, 0.45))
warm_mat = procedural_neon('Warm_Neon', (1.0, 0.55, 0.08))
paint_mat = pbr_material('Line_Paint', None, None, None, fallback=(0.72,0.74,0.78,1), scale=1.0)

# ---------------- Environment ----------------
# Alleyway
cube('Ground', (0,0,-0.08), (18,36,0.18), street_mat)
left_wall = cube('Left_Wall', (-5.5,0,2.6), (0.25,36,5.2), wall_mat)
right_wall = cube('Right_Wall', (5.5,0,2.6), (0.25,36,5.2), wall_mat)
back_wall = cube('Back_Wall', (0,16,2.6), (11.5,0.25,5.2), wall_mat)

# Buildings + windows + props
for side in (-1, 1):
    for i in range(7):
        x = side * (7.0 + random.random() * 2.6)
        y = -14 + i * 4.7
        h = 4 + random.random() * 8
        cube(f'Building_{side}_{i}', (x, y, h*0.5), (3.8, 3.0, h), metal_mat, bevel=0.02)
        for j in range(4):
            z = 1 + j * 1.4
            if z < h - 0.5:
                cube(f'Win_{side}_{i}_{j}', (x - side*1.91, y, z), (0.03, 1.2, 0.45), cyan_mat if (i+j)%2 else magenta_mat)

for i in range(10):
    cube(f'Cross_{i}', (-3.6 + i*0.8, 2.0, 0.01), (0.42, 2.0, 0.01), paint_mat)

for i in range(7):
    x = -3.8 + i * 1.2
    sign = cube(f'NeonSign_{i}', (x, -10.5 + i*2.7, 2.2 + 0.3*math.sin(i)), (0.1, 0.6, 0.6), cyan_mat if i%2 else magenta_mat)

for i in range(8):
    cube(f'Crate_{i}', (random.uniform(-3.8,3.8), random.uniform(-12,12), 0.45),
         (0.9+random.random()*0.7,0.9+random.random()*0.7,0.9), metal_mat, bevel=0.02)

# Lights

def area_light(name, color, power, location, size=4.0, aim=(0,0,1.4)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = power
    ld.color = color
    ld.shape = 'DISK'
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = (Vector(aim) - ob.location).to_track_quat('-Z','Y').to_euler()
    return ob

area_light('Key_Cyan', (0.02,0.75,1), 2300, (4.7,-7,5.6), 6)
area_light('Rim_Magenta', (1,0.08,0.35), 2600, (-4.8,2.5,5.0), 5)
area_light('Back_Warm', (1,0.50,0.1), 1800, (0,9,6.8), 6)
area_light('Fill', (0.3,0.35,0.9), 800, (0,-10,4.2), 8)

# ---------------- Characters ----------------
model_url = 'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/models/gltf/Soldier.glb'
model = os.path.join(ASSET_DIR, 'Soldier.glb')
if not os.path.exists(model):
    urlretrieve(model_url, model)
if os.path.getsize(model) < 50000:
    raise RuntimeError('Soldier.glb failed to download')

characters = []
for idx in range(2):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=model)
    imported = set(bpy.data.objects) - before
    rig = next((o for o in imported if o.type == 'ARMATURE'), None)
    if rig is None:
        raise RuntimeError('Character armature missing')
    root = bpy.data.objects.new(f'Actor_{idx+1}', None)
    bpy.context.collection.objects.link(root)
    top = [o for o in imported if o.parent not in imported]
    for o in top:
        m = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = m
    root.location = (-2.2 if idx==0 else 2.2, -1.5 if idx==0 else 1.3, 0.04)
    root.rotation_euler.z = (0.18 if idx==0 else math.pi-0.2)
    # Lightly darken clothes to fit scene
    for o in imported:
        if o.type == 'MESH':
            for poly in o.data.polygons:
                poly.use_smooth = True
    if rig.animation_data and rig.animation_data.nla_tracks:
        tracks = rig.animation_data.nla_tracks
        for t in tracks:
            t.mute = 'idle' not in t.name.lower()
        if len(tracks) and all(t.mute for t in tracks):
            tracks[0].mute = False
    if rig.animation_data:
        rig.animation_data.action = None
        for track in rig.animation_data.nla_tracks:
            if not track.mute:
                for strip in track.strips:
                    strip.repeat = max(1, TOTAL_FRAMES / max(1, strip.action_frame_end-strip.action_frame_start) + 1)
    characters.append((root, rig))

# simple root movement
for frame in range(1, TOTAL_FRAMES+1):
    phase = (frame-1)/(TOTAL_FRAMES-1)
    lx = -2.4 + 0.9*phase
    ly = -1.6 + 0.35*math.sin(phase*math.pi*2.4)
    rx =  2.4 - 0.9*phase
    ry =  1.6 - 0.25*math.sin(phase*math.pi*2.0+1.1)
    for idx, (root, _) in enumerate(characters):
        if idx == 0:
            root.location = (lx, ly, 0.04)
            root.rotation_euler.z = 0.18 + 0.08*math.sin(phase*math.pi*2)
        else:
            root.location = (rx, ry, 0.04)
            root.rotation_euler.z = math.pi - 0.25 + 0.08*math.sin(phase*math.pi*2+1.2)
        root.keyframe_insert('location', frame=frame)
        root.keyframe_insert('rotation_euler', frame=frame)

# ---------------- Weapons ----------------
def weapon_for(rig, idx):
    names = [b.name for b in rig.data.bones]
    candidates = [n for n in names if ('right' in n.lower() or n.lower().endswith('.r')) and 'hand' in n.lower()]
    candidates = candidates or [n for n in names if 'hand' in n.lower()]
    hand = candidates[0] if candidates else None
    anchor = bpy.data.objects.new(f'Weapon_{idx}', None)
    bpy.context.collection.objects.link(anchor)
    anchor.parent = rig
    if hand:
        anchor.parent_type = 'BONE'
        anchor.parent_bone = hand
        anchor.location = (0, 0.04, 0.02)
        anchor.rotation_euler = (math.radians(90), 0, 0)
    else:
        anchor.location = (0, -0.15, 1.2)
    receiver = cube(f'Receiver_{idx}', (0,0,0), (0.13,0.34,0.13), metal_mat, bevel=0.01)
    barrel = cube(f'Barrel_{idx}', (0,0,0), (0.07,0.28,0.07), metal_mat, bevel=0.006)
    grip = cube(f'Grip_{idx}', (0,0,0), (0.085,0.11,0.24), wall_mat, bevel=0.008)
    neon = cube(f'Neon_{idx}', (0,0,0), (0.025,0.21,0.014), cyan_mat if idx==0 else magenta_mat, bevel=0.003)
    sight = cube(f'Sight_{idx}', (0,0,0), (0.02,0.06,0.03), warm_mat, bevel=0.003)
    for ob, loc in [(receiver,(0,0.12,0)),(barrel,(0,0.39,0.01)),(grip,(0,-0.09,-0.14)),(neon,(0,0.21,0.06)),(sight,(0,0.16,0.09))]:
        ob.parent = anchor
        ob.location = loc
    return anchor

weapons = [weapon_for(rig, i) for i,(_,rig) in enumerate(characters)]

# animate weapon recoil
for idx, weapon in enumerate(weapons):
    own_shots = [f for f,a in SHOT_EVENTS if a == idx]
    for f in range(1, TOTAL_FRAMES+1):
        kick = 0.0
        for s in own_shots:
            dt = f - s
            if 0 <= dt <= 3:
                kick += (0.11 if dt == 0 else 0.05 if dt == 1 else 0.02)
        weapon.location = (weapon.location.x, 0.04-kick*0.7 if weapon.parent_bone else weapon.location.y, 0.02-kick*0.25 if weapon.parent_bone else weapon.location.z)
        weapon.rotation_euler = (math.radians(90)-kick, 0, 0)
        weapon.keyframe_insert('location', frame=f)
        weapon.keyframe_insert('rotation_euler', frame=f)

# muzzle flashes and shell ejection
brass = pbr_material('Brass', None, None, None, metal=0.9, fallback=(0.63,0.42,0.12,1), scale=1)
for idx, weapon in enumerate(weapons):
    own_shots = [f for f,a in SHOT_EVENTS if a == idx]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.08)
    flash = bpy.context.object
    flash.name = f'Flash_{idx}'
    flash.parent = weapon
    flash.location = (0,0.55,0.012)
    flash.data.materials.append(warm_mat if idx==0 else cyan_mat)
    for f in range(1, TOTAL_FRAMES+1):
        d = min((f-s for s in own_shots if f >= s), default=99)
        scale = 1.7 if d == 0 else 0.7 if d == 1 else 0.001
        flash.scale = (scale, scale, scale)
        flash.keyframe_insert('scale', frame=f)

for shot, actor in SHOT_EVENTS:
    scene.frame_set(shot)
    bpy.context.view_layer.update()
    start = weapons[actor].matrix_world @ Vector((0.08, 0.20, 0.02))
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.012, depth=0.05, location=start)
    casing = bpy.context.object
    casing.data.materials.append(brass)
    velocity = weapons[actor].matrix_world.to_quaternion() @ Vector((1.1, 0, 0.8))
    velocity.z = abs(velocity.z) + 0.5
    for f in range(1, TOTAL_FRAMES+1):
        if f < shot:
            casing.scale = (0.001,0.001,0.001)
        else:
            casing.scale = (1,1,1)
            t = (f - shot)/FPS
            pos = start + velocity*t + Vector((0,0,-4.9*t*t))
            pos.z = max(0.05, pos.z)
            casing.location = pos
            casing.rotation_euler = (t*7,t*11,t*9)
            casing.keyframe_insert('location', frame=f)
            casing.keyframe_insert('rotation_euler', frame=f)
        casing.keyframe_insert('scale', frame=f)

# tracer beams
for shot, actor in SHOT_EVENTS:
    scene.frame_set(shot)
    bpy.context.view_layer.update()
    transform = weapons[actor].matrix_world.copy()
    origin = transform @ Vector((0, 0.55, 0.012))
    direction = (transform.to_quaternion() @ Vector((0, 1, 0))).normalized()
    length = 2.4
    mid = origin + direction * length / 2
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.008, depth=length, location=mid)
    tracer = bpy.context.object
    tracer.data.materials.append(warm_mat)
    tracer.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    for f in range(1, TOTAL_FRAMES+1):
        vis = 1.0 if shot <= f <= shot+1 else 0.001
        tracer.scale = (vis, vis, vis)
        tracer.keyframe_insert('scale', frame=f)

# ---------------- Camera ----------------
bpy.ops.object.camera_add(location=(0,-11.5,3.2))
camera = bpy.context.object
scene.camera = camera
camera.data.lens = 32
focus = Vector((0, 0.5, 1.5))
all_shots = [f for f,_ in SHOT_EVENTS]
for f in range(1, TOTAL_FRAMES+1):
    phase = (f-1)/(TOTAL_FRAMES-1)
    # 3-part move: intro dolly, orbit, push-in
    x = 2.8*math.sin(phase*math.pi*1.15)
    y = -8.8 + 2.4*phase + 0.6*math.sin(phase*math.pi*4)
    z = 3.1 + 0.25*math.sin(phase*math.pi*2.7)
    shake = Vector((0,0,0))
    for s in all_shots:
        dt = f - s
        if 0 <= dt <= 8:
            amp = 0.09*math.exp(-dt/2.7)
            shake += Vector((math.sin(dt*6.2+s)*amp, math.sin(dt*4.8)*amp*0.35, math.cos(dt*5.2)*amp))
    camera.location = Vector((x,y,z)) + shake
    camera.rotation_euler = (focus - camera.location).to_track_quat('-Z','Y').to_euler()
    camera.keyframe_insert('location', frame=f)
    camera.keyframe_insert('rotation_euler', frame=f)

# ---------------- Save + render ----------------
scene.frame_set(1)
os.makedirs('frames', exist_ok=True)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath('CYBERPUNK_CLOUD_EXPERIMENT_V4_10s.blend'))
print('Starting render:', TOTAL_FRAMES, 'frames at', FPS, 'fps')
bpy.ops.render.render(animation=True)

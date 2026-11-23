"""Cyberpunk cloud render V5
15-second cinematic Blender Eevee firefight using free CC0 textures where available.
Poly Haven surface maps are required; missing or invalid maps stop scene generation.
Run with: blender -b --python-exit-code 1 -P render.py
"""
import bpy
import math
import os
import random
import json
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from mathutils import Vector

random.seed(42)
FPS = 24
DURATION = 15
TOTAL_FRAMES = FPS * DURATION
RES_X = 1280
RES_Y = 720
SHOT_EVENTS = [
    (17,0),(32,1),(48,0),(65,1),(80,0),(99,1),
    (115,0),(133,1),(147,0),(166,1),(179,0),(193,1),
    (212,0),(227,1),(244,0),(259,1),(277,0),(302,1),
    (321,0),(341,1)
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
scene.render.fps_base = 1.0
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
scene.view_settings.exposure = -0.42
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
bg.inputs['Strength'].default_value = 1.1
w_links.new(texcoord.outputs['Normal'], mapping.inputs['Vector'])
w_links.new(mapping.outputs['Vector'], grad.inputs['Vector'])
w_links.new(grad.outputs['Color'], ramps.inputs['Fac'])
w_links.new(ramps.outputs['Color'], bg.inputs['Color'])
w_links.new(bg.outputs['Background'], out.inputs['Surface'])

# ---------------- Utilities ----------------
ASSET_DIR = os.path.abspath('./assets')
os.makedirs(ASSET_DIR, exist_ok=True)


def fetch(url, path, validator=None):
    """Publish only complete, optionally validated downloads."""
    tmp = path + '.part'
    req = Request(url, headers={'User-Agent': 'NeonRenderLab/1.0'})
    try:
        with urlopen(req, timeout=25) as response:
            payload = response.read()
            expected = response.headers.get('Content-Length')
        if expected is not None and len(payload) != int(expected):
            raise RuntimeError('Incomplete download: ' + url)
        if not payload:
            raise RuntimeError('Empty download: ' + url)
        with open(tmp, 'wb') as output:
            output.write(payload)
        if validator is not None:
            validator(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def validate_texture(path):
    image = bpy.data.images.load(path, check_existing=False)
    try:
        if min(image.size) <= 0:
            raise RuntimeError('Invalid texture: ' + path)
    finally:
        bpy.data.images.remove(image)


def download_first(candidates, out_name):
    path = os.path.join(ASSET_DIR, out_name)
    if os.path.isfile(path):
        try:
            validate_texture(path)
            return path
        except Exception as exc:
            print('Invalid cached texture:', path, exc, flush=True)
            os.remove(path)
    errors = []
    for url in candidates:
        try:
            return fetch(url, path, validator=validate_texture)
        except Exception as exc:
            errors.append(f'{url}: {exc}')
            print('Texture download failed:', url, exc, flush=True)
    raise RuntimeError(
        f'Required texture failed: {out_name}\n' + '\n'.join(errors)
    )


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
        st.default_value = 3.2
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
        channels = {key.casefold(): value for key, value in data.items()}
        key = next((k for k in aliases[channel] if k in channels), None)
        if key is None:
            raise RuntimeError('Texture maps available: ' + str(list(data)))
        choices = channels[key]
        candidates = []
        for resolution in ('2k', '1k'):
            for fmt in ('jpg', 'png'):
                entry = choices.get(resolution, {}).get(fmt, {})
                if entry.get('url'):
                    candidates.append(entry['url'])
        if not candidates:
            raise RuntimeError('Missing texture channel: ' + asset + '/' + channel)
        return candidates
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
wet_mat = pbr_material('Wet_Asphalt_Reflections', None, None, None, metal=0.55,
                       fallback=(0.015, 0.035, 0.075, 1.0))
wet_mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = 0.12

# Multiply the imported bright concrete albedo by a deep-blue pigment:
# preserve real CC0 detail but bring back the dark Cyberpunk silhouette.
def tint_texture(material, tint=(0.13, 0.23, 0.41, 1.0), factor=0.64):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = next(node for node in nodes if node.type == 'BSDF_PRINCIPLED')
    base_input = bsdf.inputs['Base Color']
    base_link = next((link for link in links if link.to_socket == base_input), None)
    if base_link is None:
        return
    tint_node = nodes.new('ShaderNodeMixRGB')
    tint_node.blend_type = 'MULTIPLY'
    tint_node.inputs[0].default_value = factor
    tint_node.inputs[2].default_value = tint
    source = base_link.from_socket
    links.remove(base_link)
    links.new(source, tint_node.inputs[1])
    links.new(tint_node.outputs[0], base_input)

tint_texture(wall_mat)
tint_texture(street_mat, (0.16, 0.25, 0.42, 1.0), 0.43)

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

# Glossy wet patches and additional visible strips for cinematic color contrast.
for i in range(14):
    x = random.uniform(-4.1, 4.1)
    y = random.uniform(-11, 10)
    cube(f'Wet_Patch_{i}', (x, y, 0.017), (random.uniform(0.6, 2.3),
         random.uniform(0.5, 2.5), 0.006), wet_mat)
for side, mat in ((-1, cyan_mat), (1, magenta_mat)):
    for j in range(4):
        cube(f'Wall_Neon_{side}_{j}', (side*5.29, -10 + j*5, 2.3 + j%2),
             (0.06, 2.6, 0.09), mat)

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

key_light = area_light('Key_Cyan', (0.02,0.75,1), 2500, (4.7,-7,5.6), 6)
rim_light = area_light('Rim_Magenta', (1,0.08,0.35), 2900, (-4.8,2.5,5.0), 5)
area_light('Back_Warm', (1,0.50,0.1), 1900, (0,9,6.8), 6)
area_light('Fill', (0.3,0.35,0.9), 950, (0,-10,4.2), 8)
for f in range(1, TOTAL_FRAMES + 1, 4):
    for light, base, offset in ((key_light, 2500, 0.2), (rim_light, 2900, 1.8)):
        light.data.energy = base * (0.86 + 0.20*math.sin(f*0.14 + offset))
        light.data.keyframe_insert(data_path='energy', frame=f)

# ---------------- Characters ----------------
model_url = 'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/models/gltf/Soldier.glb'
model = os.path.join(ASSET_DIR, 'Soldier.glb')
def validate_model(path):
    with open(path, 'rb') as source:
        header = source.read(12)
    size = os.path.getsize(path)
    if (len(header) != 12 or header[:4] != b'glTF'
            or int.from_bytes(header[4:8], 'little') != 2
            or int.from_bytes(header[8:12], 'little') != size
            or size < 50000):
        raise RuntimeError('Invalid or incomplete Soldier.glb: ' + path)


if os.path.isfile(model):
    try:
        validate_model(model)
    except RuntimeError:
        os.remove(model)
if not os.path.isfile(model):
    fetch(model_url, model, validator=validate_model)

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
            t.mute = not any(word in t.name.lower() for word in ('idle', 'run'))
        if len(tracks) and all(t.mute for t in tracks):
            tracks[0].mute = False
    if rig.animation_data:
        rig.animation_data.action = None
        for track in rig.animation_data.nla_tracks:
            if not track.mute:
                for strip in track.strips:
                    strip.repeat = max(1, TOTAL_FRAMES / max(1, strip.action_frame_end-strip.action_frame_start) + 1)
                    # Blend imported running motion with idle around action beats.
                    if 'run' in track.name.lower():
                        strip.use_animated_influence = True
                        for f, weight in ((1,0.9),(70,0.9),(95,0.15),
                                          (155,0.20),(211,0.9),(270,0.9),
                                          (300,0.15),(360,0.25)):
                            strip.influence = weight
                            strip.keyframe_insert(data_path='influence', frame=f)
    characters.append((root, rig))

# Choreographed paths: advances, retreats and lateral dodges.
ACTOR_PATHS = [
    [(1,(-3.0,-3.1)),(40,(-2.1,-1.8)),(80,(-3.0,-0.8)),
     (120,(-2.0,-1.3)),(145,(-1.8,-0.6)),(156,(-2.9,-0.8)),
     (169,(-1.5,0.1)),(182,(-3.0,-0.6)),(195,(-1.8,0.8)),
     (214,(-2.6,1.5)),(235,(-1.2,0.2)),(260,(-3.1,-0.8)),
     (283,(-2.3,0.6)),(306,(-1.4,1.8)),(330,(-2.7,0.4)),
     (360,(-1.7,2.2))],
    [(1,(3.0,2.9)),(40,(2.5,1.2)),(80,(3.0,1.5)),
     (120,(2.2,0.7)),(145,(2.6,0.5)),(156,(1.4,-0.2)),
     (169,(2.8,0.4)),(182,(1.5,-0.8)),(195,(3.0,0.5)),
     (214,(1.8,-0.6)),(235,(3.0,1.3)),(260,(2.1,0.0)),
     (283,(2.9,2.1)),(306,(1.7,1.1)),(330,(3.1,1.4)),
     (360,(2.1,2.5))]
]


def path_position(path, frame):
    for (f0, p0), (f1, p1) in zip(path, path[1:]):
        if f0 <= frame <= f1:
            t = (frame - f0) / (f1 - f0)
            t = t*t*(3-2*t)
            return (p0[0] + (p1[0]-p0[0])*t,
                    p0[1] + (p1[1]-p0[1])*t)
    return path[-1][1]


for frame in range(1, TOTAL_FRAMES + 1):
    for idx, (root, _) in enumerate(characters):
        x, y = path_position(ACTOR_PATHS[idx], frame)
        other_x, other_y = path_position(ACTOR_PATHS[1-idx], frame)
        # The two soldiers face one another rather than always looking down the alley.
        dx, dy = other_x-x, other_y-y
        heading = math.atan2(-dx, dy)
        impact = 0.0
        for shot, attacker in SHOT_EVENTS:
            age = frame-shot-3  # projectile crosses the alley before impact
            if attacker != idx and 0 <= age <= 8:
                impact += 0.45*math.sin(math.pi*(age+1)/10)
        away = Vector((x-other_x, y-other_y, 0))
        if away.length > 0.01:
            away.normalize()
        root.location = (x + away.x*impact, y + away.y*impact,
                         0.04 + 0.070*abs(math.sin(frame*0.29 + idx))-0.05*impact)
        root.rotation_euler = (impact*1.1, (-1 if idx == 0 else 1)*impact*0.38,
                               heading + 0.05*math.sin(frame*0.13+idx))
        root.keyframe_insert('location', frame=frame)
        root.keyframe_insert('rotation_euler', frame=frame)

# ---------------- Weapons: both rifles track the opposing soldier ----------------
def weapon_for(rig, idx):
    anchor = bpy.data.objects.new(f'Weapon_{idx}', None)
    bpy.context.collection.objects.link(anchor)
    receiver = cube(f'Receiver_{idx}', (0,0,0), (0.20,0.62,0.19), metal_mat, bevel=0.012)
    barrel = cube(f'Barrel_{idx}', (0,0,0), (0.095,0.49,0.095), metal_mat, bevel=0.006)
    grip = cube(f'Grip_{idx}', (0,0,0), (0.095,0.13,0.26), wall_mat, bevel=0.009)
    neon = cube(f'Neon_{idx}', (0,0,0), (0.05,0.37,0.02),
                cyan_mat if idx==0 else magenta_mat, bevel=0.004)
    sight = cube(f'Sight_{idx}', (0,0,0), (0.04,0.09,0.05), warm_mat, bevel=0.004)
    for obj, loc in [(receiver,(0,0.18,0)), (barrel,(0,0.58,0)),
                     (grip,(0,-0.13,-0.16)), (neon,(0,0.3,0.11)),
                     (sight,(0,0.27,0.13))]:
        obj.parent = anchor
        obj.location = loc
    return anchor


weapons = [weapon_for(rig, idx) for idx, (_, rig) in enumerate(characters)]
for idx, weapon in enumerate(weapons):
    own_shots = [f for f,actor in SHOT_EVENTS if actor == idx]
    for frame in range(1, TOTAL_FRAMES + 1):
        x, y = path_position(ACTOR_PATHS[idx], frame)
        tx, ty = path_position(ACTOR_PATHS[1-idx], frame)
        direction = Vector((tx-x,ty-y,0.06)).normalized()
        recoil = sum(0.19*math.exp(-(frame-shot)/1.5)
                     for shot in own_shots if 0 <= frame-shot <= 4)
        # Explicit chest-level aiming is readable even if imported hand bones differ.
        weapon.location = Vector((x,y,1.25)) + 0.35*direction-recoil*direction
        weapon.rotation_euler = direction.to_track_quat('Y','Z').to_euler()
        weapon.keyframe_insert('location', frame=frame)
        weapon.keyframe_insert('rotation_euler', frame=frame)

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
        scale = 3.0 if d == 0 else 1.2 if d == 1 else 0.001
        flash.scale = (scale, scale, scale)
        flash.keyframe_insert('scale', frame=f)
    muzzle_data = bpy.data.lights.new(f'Muzzle_Light_{idx}', 'POINT')
    muzzle_data.color = (1.0, 0.37, 0.04) if idx == 0 else (0.02, 0.75, 1.0)
    muzzle_data.energy = 0
    muzzle_data.shadow_soft_size = 0.35
    muzzle = bpy.data.objects.new(f'Muzzle_Light_{idx}', muzzle_data)
    bpy.context.collection.objects.link(muzzle)
    muzzle.parent = weapon
    muzzle.location = (0, 0.56, 0.012)
    for shot in own_shots:
        for f, energy in ((shot - 1, 0), (shot, 750), (shot + 2, 0)):
            muzzle_data.energy = energy
            muzzle_data.keyframe_insert(data_path='energy', frame=f)

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

# Reciprocal fire: a moving short tracer crosses the alley and strikes the other actor.
def glowing_segment(name, start, end, material, radius=0.03):
    delta = end-start
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius,
                                        depth=delta.length, location=(start+end)*0.5)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = delta.to_track_quat('Z','Y').to_euler()
    obj.data.materials.append(material)
    return obj


for shot, attacker in SHOT_EVENTS:
    scene.frame_set(shot)
    bpy.context.view_layer.update()
    defender = 1-attacker
    tx,ty = path_position(ACTOR_PATHS[defender],shot+3)
    target = Vector((tx,ty,1.40))
    origin = weapons[attacker].matrix_world @ Vector((0,0.89,0))
    direction = target-origin
    mat = warm_mat if attacker == 0 else cyan_mat
    beam = glowing_segment(f'Beam_to_actor_{defender}_at_{shot}',
                           origin,target,mat,0.048)
    beam.scale = (0.001,0.001,0.001)
    beam.keyframe_insert('scale',frame=shot-1)
    beam.keyframe_insert('location',frame=shot-1)
    for dt in range(4):
        head = min(1.0,(dt+1)/4)
        tail = max(0.0,head-0.25)
        beam.location = origin+direction*((head+tail)/2)
        beam.scale = (1.0,1.0,head-tail)
        beam.keyframe_insert('location',frame=shot+dt)
        beam.keyframe_insert('scale',frame=shot+dt)
    beam.scale = (0.001,0.001,0.001)
    beam.keyframe_insert('scale',frame=shot+4)
    beam.keyframe_insert('location',frame=shot+4)

    # Delayed shield-impact burst at the victim, timed to the projectile arrival.
    hit = shot+3
    for n in range(7):
        v = Vector((math.cos(n*math.pi*2/7),math.sin(n*math.pi*2/7),
                    0.45*math.sin(n*math.pi*4/7)))
        spark = glowing_segment(f'Impact_actor_{defender}_{shot}_{n}',
                               target-v*0.3,target+v*0.3,mat,0.026)
        for frame,vis in ((hit-1,0.001),(hit,0.65),
                          (hit+2,1.15),(hit+5,0.001)):
            spark.scale = (vis,vis,vis)
            spark.keyframe_insert('scale',frame=frame)

    light_data = bpy.data.lights.new(f'HitLight_{shot}','POINT')
    light_data.color = (1.0,0.38,0.1) if attacker==0 else (0.08,0.75,1.0)
    light_data.energy = 0.0
    light_data.shadow_soft_size = 0.35
    hit_light = bpy.data.objects.new(f'HitLight_{shot}',light_data)
    bpy.context.collection.objects.link(hit_light)
    hit_light.location = target
    for frame,power in ((hit-1,0),(hit,380),(hit+2,210),(hit+5,0)):
        light_data.energy = power
        light_data.keyframe_insert('energy',frame=frame)

# ---------------- Camera: quick alternating tracking angles keep both fighters visible ----------------
# Eight connected shots: wide exchanges interleaved with opposing shoulders.
CAMERA_SHOTS = [
    (1,30, (0,-8.7,2.6),(-1.1,-7.6,2.3),(0,0,1.5),(0,0,1.5),33),
    (31,62,(-2.6,-6.4,1.7),(-1.3,-6.8,1.8),(0,0,1.5),(0,0,1.5),34),
    (63,94,(2.3,-7.0,2.0),(0,-6.1,1.7),(0,0,1.5),(0,0,1.5),33),
    (95,126,(0,-7.4,2.6),(1.5,-6.5,2.0),(0,0,1.5),(0,0,1.5),34),
    (127,158,(-2.1,-6.1,1.9),(0,-5.7,1.8),(0,0,1.5),(0,0,1.5),33),
    (159,190,(2.3,-6.8,1.8),(-1.0,-5.5,2.0),(0,0,1.5),(0,0,1.5),35),
    (191,220,(0,-7.3,2.6),(2.2,-6.1,1.9),(0,0,1.5),(0,0,1.5),33),
    (221,250,(-2.1,-6.4,1.7),(1.2,-5.9,2.1),(0,0,1.5),(0,0,1.5),34),
    (251,281,(2.3,-6.5,1.7),(-1.0,-6.1,2.0),(0,0,1.5),(0,0,1.5),33),
    (282,310,(0,-7.6,2.9),(-2.2,-6.0,1.7),(0,0,1.5),(0,0,1.5),32),
    (311,335,(-2.6,-6.5,1.8),(1.8,-6.1,1.9),(0,0,1.5),(0,0,1.5),33),
    (336,360,(0,-8.2,2.5),(0,-5.8,1.9),(0,0,1.5),(0,0,1.5),32)
]
bpy.ops.object.camera_add(location=CAMERA_SHOTS[0][2])
camera = bpy.context.object
scene.camera = camera
all_shots = [frame for frame,_ in SHOT_EVENTS]
for frame in range(1,TOTAL_FRAMES+1):
    beat = next(b for b in CAMERA_SHOTS if b[0] <= frame <= b[1])
    first,last,a,b,_,_,lens = beat
    t = (frame-first)/max(1,last-first)
    pos = Vector(a).lerp(Vector(b),t)
    left = path_position(ACTOR_PATHS[0],frame)
    right = path_position(ACTOR_PATHS[1],frame)
    focus = Vector(((left[0]+right[0])*0.5,
                    (left[1]+right[1])*0.5,1.45))
    shake = Vector((0.015*math.sin(frame*0.7),0,0.013*math.sin(frame*1.1)))
    for shot in all_shots:
        dt = frame-shot
        if 0 <= dt <= 5:
            amp = 0.085*math.exp(-dt/2.2)
            shake += Vector((math.sin(dt*6.2+shot)*amp, 0,
                             math.cos(dt*5.2)*amp))
    camera.location = pos+shake
    camera.rotation_euler = (focus-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.lens = lens+1.5*math.sin(t*math.pi)
    camera.keyframe_insert('location',frame=frame)
    camera.keyframe_insert('rotation_euler',frame=frame)
    camera.data.keyframe_insert('lens',frame=frame)

try:
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    layers = tree.nodes.new('CompositorNodeRLayers')
    glare = tree.nodes.new('CompositorNodeGlare')
    glare.glare_type = 'FOG_GLOW'
    glare.quality = 'HIGH'
    glare.threshold = 1.8
    glare.mix = -0.88
    composite = tree.nodes.new('CompositorNodeComposite')
    tree.links.new(layers.outputs['Image'],glare.inputs['Image'])
    tree.links.new(glare.outputs['Image'],composite.inputs['Image'])
except (AttributeError,TypeError,ValueError) as exc:
    print('Optional glow unavailable:',exc,flush=True)

# ---------------- Save + render ----------------
scene.frame_set(1)
os.makedirs('frames', exist_ok=True)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath('CYBERPUNK_CLOUD_EXPERIMENT_V5_15s.blend'))
print('Starting render:', TOTAL_FRAMES, 'frames at', FPS, 'fps')
preview_frames = os.environ.get('PREVIEW_FRAMES', '').strip()
motion_preview = os.environ.get('MOTION_PREVIEW_START', '').strip()
if motion_preview:
    first_frame = int(motion_preview)
    count = int(os.environ.get('MOTION_PREVIEW_COUNT', '48'))
    if count <= 0 or first_frame < 1 or first_frame + count - 1 > TOTAL_FRAMES:
        raise ValueError('Invalid motion preview frame range')
    scene.render.resolution_percentage = 50  # Fast 640x360 action sample
    os.makedirs('motion', exist_ok=True)
    for frame in range(first_frame, first_frame + count):
        scene.frame_set(frame)
        scene.render.filepath = os.path.abspath(f'motion/frame_{frame:04d}.png')
        bpy.ops.render.render(write_still=True)
elif preview_frames:
    selected = [int(value) for value in preview_frames.split(',')]
    if any(frame < 1 or frame > TOTAL_FRAMES for frame in selected):
        raise ValueError('Preview frame outside animation range')
    os.makedirs('preview', exist_ok=True)
    for frame in selected:
        scene.frame_set(frame)
        scene.render.filepath = os.path.abspath(f'preview/frame_{frame:04d}.png')
        bpy.ops.render.render(write_still=True)
else:
    bpy.ops.render.render(animation=True)

"""Validate the 15-second cinematic render's WAV, PNG sequence and MP4."""
import argparse
import json
from pathlib import Path
import subprocess
import wave

FPS = 24
FRAMES = 360
DURATION = 15
VIDEO = 'Cyberpunk_Cloud_3D_Cinematic_15s.mp4'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_audio():
    with wave.open('action.wav', 'rb') as audio:
        require(audio.getnchannels() == 1, 'Expected mono WAV')
        require(audio.getsampwidth() == 2, 'Expected 16-bit PCM')
        require(audio.getframerate() == 32000, 'Expected 32000 Hz')
        require(audio.getnframes() == 480000, 'Expected exactly 15 seconds')
        payload = audio.readframes(audio.getnframes())
        require(len(payload) == 960000, 'Truncated WAV payload')


def check_frames(directory, frames, dimensions=(1280,720)):
    root = Path(directory)
    expected = {f'frame_{frame:04d}.png' for frame in frames}
    actual = {path.name for path in root.glob('frame_*.png')}
    require(actual == expected,
            f'Missing: {sorted(expected - actual)}; '
            f'Unexpected: {sorted(actual - expected)}')
    for name in expected:
        with (root / name).open('rb') as image:
            header = image.read(24)
        require(len(header) == 24 and header[:8] == b'\x89PNG\r\n\x1a\n',
                'Invalid PNG header: ' + name)
        require(header[12:16] == b'IHDR', 'Missing PNG IHDR: ' + name)
        require(int.from_bytes(header[16:20], 'big') == dimensions[0]
                and int.from_bytes(header[20:24], 'big') == dimensions[1],
                'Unexpected dimensions: ' + name)


def check_video():
    report = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', VIDEO,
    ], text=True))
    video = [s for s in report['streams'] if s['codec_type'] == 'video']
    audio = [s for s in report['streams'] if s['codec_type'] == 'audio']
    require(len(video) == 1 and len(audio) == 1, 'Expected video and audio')
    stream = video[0]
    require((stream['width'], stream['height']) == (1280, 720), 'Bad dimensions')
    numerator, denominator = map(int, stream['avg_frame_rate'].split('/'))
    require(denominator != 0 and numerator == FPS * denominator, 'Bad FPS')
    require(int(stream['nb_read_frames']) == FRAMES, 'Bad decoded frame count')
    require(abs(float(report['format']['duration']) - DURATION) < 0.1,
            'Bad container duration')
    require(abs(float(audio[0]['duration']) - DURATION) < 0.1,
            'Bad audio duration')
    # Fully decode both streams; probing alone does not catch all corruption.
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', VIDEO,
                    '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
                   check=True)
    print(json.dumps(report, indent=2))


def check_motion():
    check_frames('motion', range(147,195), dimensions=(640,360))
    filename = 'Cyberpunk_Fight_Motion_Preview_2s.mp4'
    info = json.loads(subprocess.check_output([
        'ffprobe','-v','error','-count_frames','-show_streams',
        '-show_format','-of','json',filename
    ],text=True))
    video = [s for s in info['streams'] if s['codec_type']=='video']
    audio = [s for s in info['streams'] if s['codec_type']=='audio']
    require(len(video)==1 and len(audio)==1,'Preview needs video and audio')
    stream = video[0]
    require((stream['width'],stream['height'])==(640,360),'Bad preview size')
    require(stream['avg_frame_rate']=='24/1','Bad preview FPS')
    require(int(stream['nb_read_frames'])==48,'Bad preview frame count')
    require(abs(float(info['format']['duration'])-2.0)<0.15,'Bad preview duration')
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',filename,
                    '-map','0:v:0','-map','0:a:0','-f','null','-'],check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('audio', 'frames', 'preview', 'motion', 'video'))
    parser.add_argument('--preview-frames', default='1,17,32,36,37,80,81,124,125,165,166,205,206,250,251,300,301,360')
    args = parser.parse_args()
    if args.mode == 'audio':
        check_audio()
    elif args.mode == 'frames':
        check_frames('frames', range(1, FRAMES + 1))
    elif args.mode == 'preview':
        check_frames('preview', [int(f) for f in args.preview_frames.split(',')])
    elif args.mode == 'motion':
        check_motion()
    else:
        check_audio()
        check_video()
    print('Validated:', args.mode)

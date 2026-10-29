import json
import logging
import os
import shutil
import struct
import subprocess

logger = logging.getLogger(__name__)


def get_video_info(file_path: str) -> dict:
    """
    ffprobe yordamida video eni, bo'yi, davomiyligi (soniya) va audio oqimi mavjudligini aniqlaydi.
    ffprobe bo'lmasa yoki xato bersa, fallback orqali MP4 atomlarini (tkhd, mvhd) tahlil qiladi.
    """
    info = {
        'width': 0,
        'height': 0,
        'duration': 0.0,
        'has_audio': False,
    }

    if not os.path.exists(file_path):
        return info

    ffprobe_bin = shutil.which('ffprobe')
    if ffprobe_bin:
        cmd = [
            ffprobe_bin,
            '-v', 'error',
            '-show_entries', 'stream=codec_type,width,height,duration',
            '-show_entries', 'format=duration',
            '-of', 'json',
            file_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                streams = data.get('streams', [])
                for s in streams:
                    ctype = s.get('codec_type')
                    if ctype == 'video' and not info['width']:
                        info['width'] = int(s.get('width') or 0)
                        info['height'] = int(s.get('height') or 0)
                        dur_stream = s.get('duration')
                        if dur_stream:
                            try:
                                info['duration'] = float(dur_stream)
                            except (ValueError, TypeError):
                                pass
                    elif ctype == 'audio':
                        info['has_audio'] = True

                fmt = data.get('format', {})
                if not info['duration'] and fmt.get('duration'):
                    try:
                        info['duration'] = float(fmt['duration'])
                    except (ValueError, TypeError):
                        pass

                if info['width'] > 0 and info['height'] > 0:
                    return info
        except Exception as exc:
            logger.debug("ffprobe bilan ma'lumot olishda xatolik: %s", exc)

    # Fallback: MP4 tkhd va mvhd atomlarini to'g'ridan-to'g'ri o'qish
    try:
        with open(file_path, 'rb') as f:
            data = f.read(1024 * 1024)

        # 1. Width va Height (tkhd)
        idx = 0
        while True:
            pos = data.find(b'tkhd', idx)
            if pos == -1:
                break
            version = data[pos + 4]
            offset = 80 if version == 0 else 92
            if pos + offset + 8 <= len(data):
                w_raw, h_raw = struct.unpack('>II', data[pos + offset : pos + offset + 8])
                w = w_raw / 65536.0
                h = h_raw / 65536.0
                if w > 0 and h > 0:
                    info['width'] = int(w)
                    info['height'] = int(h)
                    break
            idx = pos + 4

        # 2. Duration (mvhd)
        mvhd_pos = data.find(b'mvhd')
        if mvhd_pos != -1:
            version = data[mvhd_pos + 4]
            if version == 0 and mvhd_pos + 28 <= len(data):
                timescale, duration = struct.unpack('>II', data[mvhd_pos + 16 : mvhd_pos + 24])
                if timescale > 0:
                    info['duration'] = round(duration / timescale, 2)
            elif version == 1 and mvhd_pos + 40 <= len(data):
                timescale = struct.unpack('>I', data[mvhd_pos + 24 : mvhd_pos + 28])[0]
                duration = struct.unpack('>Q', data[mvhd_pos + 28 : mvhd_pos + 36])[0]
                if timescale > 0:
                    info['duration'] = round(duration / timescale, 2)
    except Exception as exc:
        logger.debug("Fallback MP4 o'qishda xatolik: %s", exc)

    return info


def needs_aspect_ratio_conversion(width: int, height: int) -> bool:
    """
    Video 9:16 vertikal formatga mosligini tekshiradi (9/16 = 0.5625).
    Agar nisbat taxminan 0.50 .. 0.60 oralig'ida bo'lsa, konvertatsiya talab etilmaydi.
    Aks holda (masalan 16:9, 1:1, 4:3), 9:16 ga o'tkazish kerak.
    """
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return not (0.50 <= ratio <= 0.60)


def validate_video_duration(duration: float) -> str | None:
    """
    Instagram Reels talabi: 3 soniyadan 90 soniyagacha.
    Agar davomiylik talabga mos kelmasa, aniq xato xabarini qaytaradi, aks holda None.
    """
    if duration <= 0:
        return None
    if duration < 3.0:
        return (
            f"Video davomiyligi 3 soniyadan kam (amalda: {duration:.1f} soniya). "
            f"Instagram Reels uchun davomiylik 3 dan 90 soniyagacha bo'lishi kerak."
        )
    if duration > 90.0:
        return (
            f"Video davomiyligi 90 soniyadan ko'p (amalda: {duration:.1f} soniya). "
            f"Instagram Reels uchun davomiylik 3 dan 90 soniyagacha bo'lishi kerak."
        )
    return None


def convert_video_to_9_16(input_path: str, output_path: str, timeout: int = 180) -> bool:
    """
    ffmpeg orqali gorizontal yoki nostandart videoni blur fonli 1080x1920 (9:16) MP4 ga o'tkazadi.
    Tepa va past qismga xira fon qo'yiladi, video asl nisbatida o'rtada saqlanadi.
    H.264 + AAC, faststart formatida saqlanadi.
    """
    ffmpeg_bin = shutil.which('ffmpeg')
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg tizimda o'rnatilmagan.")

    info = get_video_info(input_path)
    has_audio = info.get('has_audio', False)

    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
        "[0:v]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )

    if has_audio:
        cmd = [
            ffmpeg_bin,
            '-y',
            '-i', input_path,
            '-filter_complex', filter_complex,
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            output_path,
        ]
    else:
        # Audio bo'lmagan videolarga silent audio qo'shish (Instagram Reels audio talab qiladi)
        cmd = [
            ffmpeg_bin,
            '-y',
            '-i', input_path,
            '-f', 'lavfi',
            '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
            '-filter_complex', filter_complex,
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-shortest',
            '-movflags', '+faststart',
            output_path,
        ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            logger.error("ffmpeg konvertatsiyasida xatolik: %s", res.stderr)
            return False
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg konvertatsiyasi timeout bo'ldi (%s soniya).", timeout)
        return False
    except Exception as exc:
        logger.error("ffmpeg ishga tushirishda xatolik: %s", exc)
        return False


def process_video_file(video) -> tuple[bool, str | None]:
    """
    Video faylini tahlil qiladi va kerak bo'lsa 9:16 ga o'tkazadi.
    1. Fayl mavjudligini tekshiradi.
    2. ffprobe/fallback orqali width, height, duration oladi.
    3. Davomiylik 3-90 soniya oralig'ida ekanini tekshiradi.
    4. 9:16 nisbatda bo'lmasa, ffmpeg orqali blur-fonli 1080x1920 ga o'tkazadi.
    5. Asl faylni konvertatsiya qilingan fayl bilan almashtiradi.

    Qaytaradi: (success: bool, error_message: str | None)
    """
    if not video.file:
        return False, "Video fayli mavjud emas."

    try:
        file_path = video.file.path
    except Exception as exc:
        return False, f"Video fayl yo'lini aniqlab bo'lmadi: {exc}"

    if not os.path.exists(file_path):
        return False, f"Video fayli diskda topilmadi: {file_path}"

    info = get_video_info(file_path)
    width = info.get('width', 0)
    height = info.get('height', 0)
    duration = info.get('duration', 0.0)

    # 1. Davomiylik tekshiruvi (3 - 90 soniya)
    duration_err = validate_video_duration(duration)
    if duration_err:
        return False, duration_err

    # 2. Nisbat tekshiruvi (9:16)
    if needs_aspect_ratio_conversion(width, height):
        logger.info(
            "Video 9:16 nisbatda emas (%sx%s). ffmpeg bilan 1080x1920 ga o'tkazilmoqda: %s",
            width, height, file_path
        )
        output_path = f"{file_path}.converted.mp4"
        try:
            success = convert_video_to_9_16(file_path, output_path)
            if not success or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return False, "ffmpeg orqali videoni 9:16 formatiga o'tkazishda xatolik yuz berdi."

<<<<<<< HEAD
            # Asl fayl zaxirasi (.orig.mp4) saqlab qolinadi
            backup_path = f"{file_path}.orig.mp4"
            if not os.path.exists(backup_path):
                import shutil
                try:
                    shutil.copy2(file_path, backup_path)
                    logger.info("Asl video zaxira nusxasi yaratildi: %s", backup_path)
                except Exception as b_err:
                    logger.warning("Asl videoni zaxiralashda xatolik: %s", b_err)

=======
>>>>>>> origin/messi
            os.replace(output_path, file_path)
            logger.info("Video muvaffaqiyatli 1080x1920 formatiga o'tkazildi: %s", file_path)
        finally:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
    else:
        logger.info("Video allaqachon 9:16 nisbatda (%sx%s). Konvertatsiya shart emas.", width, height)

    return True, None

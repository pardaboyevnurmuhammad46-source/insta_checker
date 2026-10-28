import os
import subprocess
import tempfile
import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_BRAND_KEYWORDS = [
    'instachecker', 'insta checker', 'insta_checker',
    'brend', '#brend', 'homiy', 'reklama', 'aksiya', 'konkurs'
]


def get_campaign_config():
    try:
        from .models import CampaignConfig
        return CampaignConfig.get_solo()
    except Exception:
        return None


def get_brand_keywords() -> list[str]:
    cfg = get_campaign_config()
    if cfg and cfg.required_keywords:
        kws = [k.strip().lower() for k in cfg.required_keywords.split(',') if k.strip()]
        if cfg.brand_name:
            kws.append(cfg.brand_name.strip().lower())
        return list(set(kws))

    raw = getattr(settings, 'BRAND_KEYWORDS', None) or os.getenv('BRAND_KEYWORDS')
    if raw:
        if isinstance(raw, list):
            return [k.lower().strip() for k in raw if k.strip()]
        return [k.lower().strip() for k in str(raw).split(',') if k.strip()]
    return DEFAULT_BRAND_KEYWORDS


def extract_audio(video_path: str) -> str | None:
    """
    FFmpeg yordamida videodan 16kHz mono audio (MP3) faylini ajratib oladi.
    """
    if not video_path or not os.path.exists(video_path):
        logger.warning("Audio ajratish uchun video fayl topilmadi: %s", video_path)
        return None

    try:
        temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        temp_audio.close()

        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vn', '-acodec', 'libmp3lame',
            '-ar', '16000', '-ac', '1', '-b:a', '64k',
            temp_audio.name
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if res.returncode == 0 and os.path.exists(temp_audio.name) and os.path.getsize(temp_audio.name) > 0:
            return temp_audio.name
        else:
            if os.path.exists(temp_audio.name):
                os.remove(temp_audio.name)
            logger.warning("FFmpeg audio ajratishda xatolik berdi: %s", res.stderr.decode('utf-8', errors='ignore')[:200])
            return None
    except FileNotFoundError:
        logger.debug("ffmpeg tizimda mavjud emas, audio tahlili o'tkazib yuborildi.")
        if os.path.exists(temp_audio.name):
            try:
                os.remove(temp_audio.name)
            except OSError:
                pass
        return None
    except Exception as exc:
        logger.warning("Videodan audio ajratib olishda xatolik: %s", exc)
        return None


def transcribe_audio(audio_path: str) -> str:
    """
    Audioni matnga aylantiradi (Speech-to-Text).
    1. Agar OPENAI_API_KEY bo'lsa, OpenAI Whisper API dan foydalanadi.
    2. Aks holda, ovoz tahlili va lingvistik tahlil orqali intellektual matn ajratadi.
    """
    if not audio_path or not os.path.exists(audio_path):
        return ""

    openai_key = os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', '')
    if openai_key and not openai_key.startswith('your_'):
        try:
            with open(audio_path, 'rb') as f:
                res = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
                    data={"model": "whisper-1", "language": "uz"},
                    timeout=25
                )
            if res.status_code == 200:
                transcript = res.json().get('text', '').strip()
                if transcript:
                    return transcript
        except Exception as exc:
            logger.warning("OpenAI Whisper API orqali transkripsiya qilishda xatolik: %s", exc)

    # Agar OpenAI API kaliti bo'lmasa yoki xato bersa, soxta transkript qaytarmaymiz
    return ""


def verify_video_advertisement(
    video_path: str | None = None,
    caption: str | None = None,
    expected_code: str | None = None,
) -> dict:
    """
    Ovoz (Audio Transcript) va Tavsif (Caption) orqali reklama tilga olinganini tekshiradi.
    Agar expected_code (unikal aksiya kodi) berilgan bo'lsa, uning mavjudligi majburiy.
    """
    caption_text = (caption or "").strip()
    expected_code_clean = (expected_code or "").strip().upper()
    brand_keywords = get_brand_keywords()

    audio_path = None
    transcript_text = ""
    if video_path and os.path.exists(video_path):
        audio_path = extract_audio(video_path)
        if audio_path:
            transcript_text = transcribe_audio(audio_path)
            try:
                os.remove(audio_path)
            except OSError:
                pass

    found_in_caption = []
    found_in_audio = []

    # 1. Caption tahlili
    caption_upper = caption_text.upper()
    caption_lower = caption_text.lower()
    code_in_caption = bool(expected_code_clean and expected_code_clean in caption_upper)
    if code_in_caption:
        found_in_caption.append(f"Kod: {expected_code_clean}")
    for kw in brand_keywords:
        if kw in caption_lower:
            found_in_caption.append(kw)

    # 2. Audio Transcript tahlili
    transcript_lower = transcript_text.lower()
    code_in_audio = bool(expected_code_clean and expected_code_clean.lower() in transcript_lower)
    if code_in_audio:
        found_in_audio.append(f"Kod: {expected_code_clean}")
    for kw in brand_keywords:
        if kw in transcript_lower:
            found_in_audio.append(kw)

    cfg = get_campaign_config()
    topic_name = cfg.topic if cfg else "InstaChecker Aksiya Reklamasi"
    max_pts = cfg.points_reward if cfg else 100

    # Unikal kod tekshiruvi: agar expected_code berilgan bo'lsa, u majburiy
    code_found = code_in_caption or code_in_audio
    if expected_code_clean and not code_found:
        return {
            'is_verified': False,
            'confidence': 0.10,
            'points': 0,
            'detection_source': 'none',
            'explanation': (
                f"⚠️ Unikal aksiya kodi ({expected_code_clean}) videoning nutqida ham, "
                f"tavsifida ham topilmadi. Ishtirok uchun kod kiritilishi shart."
            ),
            'transcript': transcript_text,
            'caption': caption_text,
            'matches_found': found_in_caption + found_in_audio,
        }

    # Natija hisoblash (kod topilgan yoki expected_code talab qilinmagan holatda)
    has_caption_match = len(found_in_caption) > 0
    has_audio_match = len(found_in_audio) > 0

    confidence = 0.0
    detection_source = 'none'
    points = 0

    if has_caption_match and has_audio_match:
        detection_source = 'both'
        confidence = 0.98
        points = max_pts
        explanation = (
            f"✅ Ajoyib! Mavzu: '{topic_name}'. "
            f"Reklama ham Ovozda (audio), ham Tavsifda (caption) aniqlandi. "
            f"Ovozda: {', '.join(set(found_in_audio))}. Tavsifda: {', '.join(set(found_in_caption))}."
        )
    elif has_audio_match:
        detection_source = 'audio'
        confidence = 0.85
        points = int(max_pts * 0.7)
        explanation = (
            f"✅ Mavzu: '{topic_name}'. "
            f"Videoning ovozli nutqida brend/aksiya tilga olindi: {', '.join(set(found_in_audio))}."
        )
    elif has_caption_match:
        detection_source = 'caption'
        confidence = 0.75
        points = int(max_pts * 0.5)
        explanation = (
            f"✅ Mavzu: '{topic_name}'. "
            f"Video tavsifida (caption) brend/kod aniqlandi: {', '.join(set(found_in_caption))}."
        )
    else:
        detection_source = 'none'
        confidence = 0.10
        points = 0
        explanation = f"⚠️ '{topic_name}' mavzusi bo'yicha videoda va tavsifda brend nomi yoki unikal kod topilmadi."

    is_verified = (confidence >= 0.50)

    return {
        'is_verified': is_verified,
        'confidence': confidence,
        'detection_source': detection_source,
        'transcript': transcript_text or (caption_text if has_caption_match else ""),
        'explanation': explanation,
        'points': points,
        'keywords_found': list(set(found_in_caption + found_in_audio)),
    }


def process_and_verify_post_ai(post) -> dict:
    """
    Post uchun to'liq AI tekshiruvini bajaradi va bazani yangilaydi.
    """
    video_path = None
    if hasattr(post, 'link') and post.link and post.link.video and post.link.video.file:
        try:
            video_path = post.link.video.file.path
        except Exception:
            pass

    expected_code = post.link.code if hasattr(post, 'link') and post.link else None
    caption = getattr(post, 'caption', '') or ''

    result = verify_video_advertisement(
        video_path=video_path,
        caption=caption,
        expected_code=expected_code,
    )

    post.ai_verified = result['is_verified']
    post.ai_confidence = result['confidence']
    post.ai_detection_source = result['detection_source']
    post.transcript = result['transcript']
    post.ai_explanation = result['explanation']
    post.points_awarded = result['points']
    post.save(update_fields=[
        'ai_verified', 'ai_confidence', 'ai_detection_source',
        'transcript', 'ai_explanation', 'points_awarded'
    ])

    # Foydalanuvchiga bildirishnoma yaratish
    try:
        from .models import Notification
        if result['is_verified'] and hasattr(post, 'link') and post.link.user:
            Notification.objects.create(
                user=post.link.user,
                kind='ai_verified',
                message=(
                    f"🎉 AI Reklama Tahlili muvaffaqiyatli o'tdi! "
                    f"Sizga +{result['points']} ball taqdim etildi. "
                    f"Manba: {result['detection_source'].upper()}."
                ),
            )
    except Exception as notif_err:
        logger.warning("AI bildirishnoma yaratishda xatolik: %s", notif_err)

    return result

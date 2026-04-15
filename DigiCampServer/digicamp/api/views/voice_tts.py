# ─── imports ──────────────────────────────────────────────────────────
import io, os, zipfile, tempfile, logging, subprocess
from pathlib import Path
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import StreamingHttpResponse
from django.conf import settings
from botocore.exceptions import ClientError
from src import verification_uploader as vup

from src.elevenlabs_tts import VerificationCallTTS      # NEW ← your wrapper
# -- remove old import:  from src.elevenlabs_tts import ElevenLabs

LANG_PROFILES = settings.VOICE_TTS_LANGS                 # unchanged
# ──────────────────────────────────────────────────────────


def _downsample_wav16(src_wav16: str, dst_wav8: str) -> None:
    """16-kHz WAV → 8 kHz / 16-bit / mono WAV (Asterisk-friendly)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", src_wav16, "-ar", "8000", "-ac", "1",
         "-sample_fmt", "s16", dst_wav8],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


@api_view(["POST"])
def generate_verification_clip(request):
    # 1) ─── auth ──────────────────────────────────────────────────────
    host = request.data.get("hostname") or request.data.get("host")
    pwd  = request.data.get("password") or request.data.get("system_password")
    if not host or not pwd:
        return Response({"detail": "hostname and password required"}, 400)
    if settings.DIGICAMP_CREDENTIALS.get(host) != pwd:
        return Response({"detail": "Invalid credentials"}, 401)

    # 2) ─── segments & profile ───────────────────────────────────────
    lang = request.data.get("language", "hi")
    segs = {
        "name":     request.data.get("name"),
        "channel":  request.data.get("channel_name"),
        "surveyor": request.data.get("surveyor_name"),
        "gender": request.data.get("gender"),
    }
    segs = {k: v for k, v in segs.items() if v}
    if not segs:
        return Response({"detail":
                         "Provide at least one of name/channel_name/surveyor_name"},
                        400)

    prof = LANG_PROFILES.get(lang)
    if not prof:
        return Response({"detail": f"Unsupported language '{lang}'"}, 400)

    # 3) ─── TTS helper (your wrapper) ────────────────────────────────
    tts = VerificationCallTTS(
        api_key   = settings.ELEVENLABS_API_KEY,
        voice_id  = prof["voice_id"],
        model_id  = prof.get("model_id", settings.ELEVENLABS_MODEL_ID),
        # optional: output_dir="tts_cache", seed=12345
    )
    ctx_map = prof["ctx"]

    s3_client = vup._make_s3_client()

    # 4) ─── generate (or fetch) clips & ZIP result ───────────────────
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for seg, txt in segs.items():
                if seg not in ctx_map:
                    return Response({"detail": f"Invalid segment '{seg}'"}, 400)

                key = vup._key_for_text(txt)  # hashed key
                try:
                    # Does the clip already exist in Spaces?
                    s3_client.head_object(Bucket=vup.SPACE_NAME, Key=key)
                    obj = s3_client.get_object(Bucket=vup.SPACE_NAME, Key=key)
                    print(f"[SPACE HIT] segment '{seg}' text '{txt}' fetched from Spaces → using cached audio")
                    audio_bytes = obj["Body"].read()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_f:
                        tmp_f.write(audio_bytes)
                        tmp_path = tmp_f.name
                    zf.write(tmp_path, arcname=f"{seg}.wav")
                    os.unlink(tmp_path)
                    continue  # done; fetched from cache
                except ClientError as exc:
                    if exc.response.get("Error", {}).get("Code") != "404":
                        raise  # unexpected S3 error
                    # else -> object missing -> generate a fresh one
                    print(f"[SPACE MISS] segment '{seg}' text '{txt}' not found → generating new TTS clip")

                prev, nxt = ctx_map[seg]

                # ➜ wav16 (16-kHz) from wrapper
                wav16_path = tts.generate(seg, txt, prev, nxt)

                # ➜ down-sample to 8-kHz
                wav8_path = Path(wav16_path).with_suffix(".wav")
                _downsample_wav16(str(wav16_path), str(wav8_path))

                # ➜ add to ZIP
                zf.write(wav8_path, arcname=f"{seg}.wav")

                # ➜ cache in Spaces (synchronously)
                with open(wav8_path, "rb") as f:
                    vup.upload_verification(txt, f.read(), content_type="audio/wav")

                # tidy temp files
                os.unlink(wav16_path)
                os.unlink(wav8_path)

    except Exception:
        logging.getLogger(__name__).exception("TTS generation failed")
        return Response({"detail": "TTS generation failed"}, 500)

    # 5) ─── stream ZIP back ──────────────────────────────────────────
    buf.seek(0)
    resp = StreamingHttpResponse(buf, content_type="application/zip")
    resp["Content-Disposition"] = (
        'attachment; filename="verification_clips.zip"')
    return resp

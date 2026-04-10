"""Async uploader for verification audios & their associated text.

This helper works with DigitalOcean Spaces.  The audio is accepted as a
*bytes-like* object (e.g. `bytes`, `bytearray`, `io.BytesIO`), and saved under
``Asterisk/Verification/<sanitised_text>.wav`` where *sanitised_text* is the
lower-cased text with non-alphanumeric characters replaced by ``_``.

Typical usage
-------------
    from voiceapi.src.verification_uploader import async_upload_verification

    # inside an asyncio capable context
    url = await async_upload_verification("John Doe", wav_bytes)

    # or, from sync code
    import asyncio
    url = asyncio.run(async_upload_verification("John Doe", wav_bytes))

If an object with the same key already exists in the Space, the cached
(public-read) URL is returned immediately without re-uploading.
"""
from __future__ import annotations

import asyncio
import re, hashlib, unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Union, BinaryIO

from boto3 import session as _boto_session
from botocore.exceptions import ClientError

# ─── DigitalOcean Spaces config ──────────────────────────────────────────────
ACCESS_ID: str = "DO002FER8TXVU8UJJFCV"
SECRET_KEY: str = "0q0zbXHjRiTvefg7vleBK5js5eC2b2+EzmiAGcIEHsc"
SPACE_NAME: str = "sabkiapp"
REGION_NAME: str = "sgp1"
ENDPOINT_URL: str = "https://sgp1.digitaloceanspaces.com"

_VERIFICATION_PREFIX: str = "Asterisk/Verification"
_CONTENT_TYPE_DEFAULT: str = "audio/mpeg"

# ─── hashing helper (same as call_maker.py) ───────────────────────────

def _hash15(text: str) -> str:
    norm = unicodedata.normalize("NFC", text)
    return hashlib.sha1(norm.encode()).hexdigest()[:15]

# Limit the number of background workers; uploading is mostly I/O-bound.
_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="verification-uploader")


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_s3_client():
    """Create a boto3 S3 client for DigitalOcean Spaces."""
    sess = _boto_session.Session()
    return sess.client(
        "s3",
        region_name=REGION_NAME,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=ACCESS_ID,
        aws_secret_access_key=SECRET_KEY,
    )


def _key_for_text(text: str) -> str:
    """Return S3 key for *text* using 15-char SHA1 hash."""
    return f"{_VERIFICATION_PREFIX}/{_hash15(text)}.wav"


# ─── core sync implementation ───────────────────────────────────────────────

def _sync_upload_or_get_url(
    *,
    text: str,
    audio: Union[bytes, BinaryIO],
    content_type: str = _CONTENT_TYPE_DEFAULT,
) -> str:
    """Upload *audio* to Spaces (if missing) and return its public URL.

    The function blocks.  It is intended to be executed in a thread pool.
    """
    client = _make_s3_client()
    key = _key_for_text(text)

    # 1) Does the object already exist?  If yes, return its URL.
    try:
        client.head_object(Bucket=SPACE_NAME, Key=key)
        return f"{ENDPOINT_URL}/{SPACE_NAME}/{key}"
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "404":
            # Unexpected error → propagate.
            raise
        # else: not found ➜ will upload.

    # 2) Prepare body
    if hasattr(audio, "read"):
        body = audio  # type: ignore[arg-type]
    else:
        body = audio  # bytes-like

    # 3) Upload with public-read ACL.
    client.put_object(
        Bucket=SPACE_NAME,
        Key=key,
        Body=body,
        ACL="public-read",
        ContentType=content_type,
    )
    return f"{ENDPOINT_URL}/{SPACE_NAME}/{key}"


# ─── public async API ────────────────────────────────────────────────────────

async def async_upload_verification(
    text: str,
    audio: Union[bytes, BinaryIO],
    *,
    content_type: str = _CONTENT_TYPE_DEFAULT,
) -> str:
    """Asynchronously upload a verification *audio* for *text*.

    Returns the (public) HTTPS URL pointing to the object in Spaces.  If the
    object already exists, it is *not* re-uploaded.
    """
    loop = asyncio.get_running_loop()
    from functools import partial
    func = partial(_sync_upload_or_get_url, text=text, audio=audio, content_type=content_type)
    return await loop.run_in_executor(_executor, func)


# convenience: expose a sync wrapper for non-async codebases ---------------

def upload_verification(text: str, audio: Union[bytes, BinaryIO], *, content_type: str = _CONTENT_TYPE_DEFAULT) -> str:
    """Synchronous helper around :func:`async_upload_verification`.

    Not recommended for high-throughput scenarios because it spins an event
    loop per call, but handy in traditional Django views/tests.
    """
    return asyncio.run(async_upload_verification(text, audio, content_type=content_type))

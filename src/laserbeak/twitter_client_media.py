from __future__ import annotations

import time

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_MEDIA_METADATA_URL, TWITTER_UPLOAD_URL


class TwitterClientMediaMixin(TwitterClientBase):
    def _media_category_for_mime(self, mime_type: str) -> str | None:
        if mime_type.startswith("image/"):
            return "tweet_gif" if mime_type == "image/gif" else "tweet_image"
        if mime_type.startswith("video/"):
            return "tweet_video"
        return None

    def upload_media(self, *, data: bytes, mime_type: str, alt: str | None = None) -> dict:
        category = self._media_category_for_mime(mime_type)
        if not category:
            return {"success": False, "error": f"Unsupported media type: {mime_type}"}

        try:
            init_params = {
                "command": "INIT",
                "total_bytes": str(len(data)),
                "media_type": mime_type,
                "media_category": category,
            }
            init_resp = self._request("POST", TWITTER_UPLOAD_URL, headers=self._get_upload_headers(), data=init_params)
            if init_resp.status_code >= 400:
                return {"success": False, "error": f"HTTP {init_resp.status_code}: {init_resp.text[:200]}"}

            init_body = init_resp.json()
            media_id = (
                init_body.get("media_id_string")
                if isinstance(init_body.get("media_id_string"), str)
                else str(init_body.get("media_id"))
                if init_body.get("media_id") is not None
                else None
            )
            if not media_id:
                return {"success": False, "error": "Media upload INIT did not return media_id"}

            chunk_size = 5 * 1024 * 1024
            segment_index = 0
            for offset in range(0, len(data), chunk_size):
                chunk = data[offset : offset + chunk_size]
                files = {"media": ("media", chunk, mime_type)}
                form_data = {"command": "APPEND", "media_id": media_id, "segment_index": str(segment_index)}
                append_resp = self._request(
                    "POST",
                    TWITTER_UPLOAD_URL,
                    headers=self._get_upload_headers(),
                    data=form_data,
                    json_data=None,
                    files=files,
                )
                if append_resp.status_code == 200:
                    segment_index += 1
                    continue
                return {"success": False, "error": f"HTTP {append_resp.status_code}: {append_resp.text[:200]}"}

            finalize_params = {"command": "FINALIZE", "media_id": media_id}
            finalize_resp = self._request(
                "POST", TWITTER_UPLOAD_URL, headers=self._get_upload_headers(), data=finalize_params
            )
            if finalize_resp.status_code >= 400:
                return {"success": False, "error": f"HTTP {finalize_resp.status_code}: {finalize_resp.text[:200]}"}

            finalize_body = finalize_resp.json()
            info = finalize_body.get("processing_info") or {}
            if info.get("state") and info.get("state") != "succeeded":
                attempts = 0
                while attempts < 20:
                    if info.get("state") == "failed":
                        msg = (info.get("error") or {}).get("message") or (info.get("error") or {}).get("name")
                        return {"success": False, "error": msg or "Media processing failed"}
                    delay_secs = int(info.get("check_after_secs") or 2)
                    delay_secs = max(1, delay_secs)
                    time.sleep(delay_secs)

                    status_resp = self._request(
                        "GET",
                        f"{TWITTER_UPLOAD_URL}?command=STATUS&media_id={media_id}",
                        headers=self._get_upload_headers(),
                    )
                    if status_resp.status_code >= 400:
                        return {"success": False, "error": f"HTTP {status_resp.status_code}: {status_resp.text[:200]}"}

                    status_body = status_resp.json()
                    if not status_body.get("processing_info"):
                        break
                    info = status_body.get("processing_info")
                    if info.get("state") == "succeeded":
                        break
                    attempts += 1

            if alt and mime_type.startswith("image/"):
                meta_resp = self._request(
                    "POST",
                    TWITTER_MEDIA_METADATA_URL,
                    headers=self._get_json_headers(),
                    json_data={"media_id": media_id, "alt_text": {"text": alt}},
                )
                if meta_resp.status_code >= 400:
                    return {"success": False, "error": f"HTTP {meta_resp.status_code}: {meta_resp.text[:200]}"}

            return {"success": True, "mediaId": media_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

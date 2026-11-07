"""Instagram publishing via Instagram Login API (graph.instagram.com) - same flow as the `religious` repo.
No Facebook Page needed. Needs professional IG account + token with instagram_business_content_publish."""
import json, os, time, urllib.parse, urllib.request

G = "https://graph.instagram.com/v21.0"


def _post(path: str, **params) -> dict:
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{G}/{path}", data=data), timeout=60) as r:
        return json.load(r)


def _get(path: str, **params) -> dict:
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    with urllib.request.urlopen(f"{G}/{path}?{urllib.parse.urlencode(params)}", timeout=60) as r:
        return json.load(r)


def publish_image(image_url: str, caption: str) -> str:
    uid = os.environ["IG_USER_ID"]
    cid = _post(f"{uid}/media", image_url=image_url, caption=caption)["id"]
    for _ in range(10):
        if _get(cid, fields="status_code").get("status_code") == "FINISHED":
            break
        time.sleep(3)
    return _post(f"{uid}/media_publish", creation_id=cid)["id"]


def refresh_token() -> dict:
    """Long-lived token lasts ~60d; refresh (allowed after 24h old) returns a new 60d token."""
    return _get("refresh_access_token", grant_type="ig_refresh_token")

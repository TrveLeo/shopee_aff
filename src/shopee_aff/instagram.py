"""Instagram Graph API publishing. Needs IG business/creator account + FB page + long-lived token."""
import json, os, time, urllib.parse, urllib.request

G = "https://graph.facebook.com/v21.0"


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

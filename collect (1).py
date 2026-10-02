"""Collect Parlimen Malaysia posts + comments from IG, FB, Threads, X -> docs/data/posts.json"""
import os, json, re, hashlib, datetime as dt, requests

OUT = "docs/data/posts.json"
G = "https://graph.facebook.com/v21.0"
T = "https://graph.threads.net/v1.0"
env = lambda k: os.environ.get(k, "").strip()

POS = "terima kasih bagus syabas tahniah telus baik hebat mantap setuju sokong great thanks good excellent proud".split()
NEG = "kecewa teruk lemah gagal bohong janji rasuah malu tipu marah tak puas hati bodoh bad poor fail corrupt angry disappointed".split()
TOPICS = {"Bajet & Ekonomi": ["bajet", "budget", "ekonomi", "cukai"],
          "Sidang Dewan Rakyat": ["sidang", "dewan rakyat", "usul", "perbahasan"],
          "Jawatankuasa Pilihan Khas": ["jawatankuasa", "psc"],
          "Lawatan & Delegasi": ["delegasi", "lawatan", "kunjungan"],
          "Pendidikan Awam": ["pelajar", "sekolah", "pendidikan"]}

def sentiment(t):
    t = t.lower(); p = sum(w in t for w in POS); n = sum(w in t for w in NEG)
    return "pos" if p > n else "neg" if n > p else "neu"

def topic(t):
    t = (t or "").lower()
    return next((k for k, ws in TOPICS.items() if any(w in t for w in ws)), "Pengumuman Rasmi")

def post(pf, pid, text, url, ts, likes, shares, comments):
    cs = [{"id": hashlib.md5(f"{pf}{pid}{c.get('text','')}{c.get('time',ts)}".encode()).hexdigest()[:12],
           "text": c.get("text", ""), "time": c.get("time", ts), "s": None} for c in comments]
    return {"key": f"{pf}:{pid}", "platform": pf, "id": pid, "text": text or "", "url": url, "time": ts,
            "likes": likes, "shares": shares, "comments_count": max(len(cs), 0), "topic": topic(text), "comments": cs}

def get(url, **params):
    r = requests.get(url, params=params, timeout=30); r.raise_for_status(); return r.json()

def instagram():
    uid, tok = env("IG_USER_ID"), env("META_TOKEN")
    if not (uid and tok): return []
    d = get(f"{G}/{uid}/media", access_token=tok, limit=25,
            fields="id,caption,permalink,timestamp,like_count,comments_count,comments.limit(25){text,timestamp}")
    return [post("ig", m["id"], m.get("caption"), m.get("permalink"), m["timestamp"], m.get("like_count", 0), 0,
                 [{"text": c["text"], "time": c["timestamp"]} for c in m.get("comments", {}).get("data", [])]) for m in d.get("data", [])]

def facebook():
    pid, tok = env("FB_PAGE_ID"), env("META_TOKEN")  # use a Page access token
    if not (pid and tok): return []
    d = get(f"{G}/{pid}/posts", access_token=tok, limit=25,
            fields="id,message,permalink_url,created_time,shares,reactions.summary(true).limit(0),comments.limit(25){message,created_time}")
    return [post("fb", m["id"], m.get("message"), m.get("permalink_url"), m["created_time"],
                 m.get("reactions", {}).get("summary", {}).get("total_count", 0), m.get("shares", {}).get("count", 0),
                 [{"text": c["message"], "time": c["created_time"]} for c in m.get("comments", {}).get("data", [])]) for m in d.get("data", [])]

def threads():
    uid, tok = env("THREADS_USER_ID"), env("THREADS_TOKEN")
    if not (uid and tok): return []
    out = []
    for m in get(f"{T}/{uid}/threads", access_token=tok, limit=25, fields="id,text,permalink,timestamp").get("data", []):
        likes = shares = 0
        try:
            for i in get(f"{T}/{m['id']}/insights", access_token=tok, metric="likes,reposts").get("data", []):
                v = i["values"][0]["value"]; likes, shares = (v, shares) if i["name"] == "likes" else (likes, v)
        except Exception: pass
        rep = get(f"{T}/{m['id']}/replies", access_token=tok, fields="text,timestamp").get("data", [])
        out.append(post("th", m["id"], m.get("text"), m.get("permalink"), m["timestamp"], likes, shares,
                        [{"text": r.get("text", ""), "time": r["timestamp"]} for r in rep]))
    return out

def x_twitter():
    uid, tok = env("X_USER_ID"), env("X_BEARER_TOKEN")
    if not (uid and tok): return []
    h = {"Authorization": f"Bearer {tok}"}; out = []
    r = requests.get(f"https://api.twitter.com/2/users/{uid}/tweets", headers=h, timeout=30,
                     params={"max_results": 10, "tweet.fields": "created_at,public_metrics"}); r.raise_for_status()
    for t in r.json().get("data", []):
        m = t["public_metrics"]
        s = requests.get("https://api.twitter.com/2/tweets/search/recent", headers=h, timeout=30,
                         params={"query": f"conversation_id:{t['id']} is:reply", "max_results": 20, "tweet.fields": "created_at"})
        reps = s.json().get("data", []) if s.ok else []
        out.append(post("x", t["id"], t["text"], f"https://x.com/i/status/{t['id']}", t["created_at"], m["like_count"],
                        m["retweet_count"], [{"text": c["text"], "time": c["created_at"]} for c in reps]))
    return out

def claude_sentiment(texts):
    """Classify comments with Claude (handles Malay/English/slang/sarcasm). Returns None if no API key."""
    key = env("ANTHROPIC_API_KEY")
    if not (key and texts): return None
    out = []
    for i in range(0, len(texts), 40):
        chunk = texts[i:i + 40]
        prompt = ("Classify the sentiment of each public comment about the Parliament of Malaysia (Parlimen Malaysia). "
                  "Comments may be Bahasa Malaysia, English or mixed, with slang or sarcasm. Return ONLY a JSON array of "
                  "strings, one per comment in the same order, each exactly 'pos', 'neu' or 'neg'.\n\n" + json.dumps(chunk, ensure_ascii=False))
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": env("CLAUDE_MODEL") or "claude-haiku-4-5-20251001", "max_tokens": 1000,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        labels = json.loads(re.search(r"\[.*\]", r.json()["content"][0]["text"], re.S).group(0))
        if len(labels) != len(chunk): raise ValueError("label count mismatch")
        out += [l if l in ("pos", "neu", "neg") else "neu" for l in labels]
    return out

def telegram(msg):
    tok, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                           json={"chat_id": chat, "text": msg[:4000], "disable_web_page_preview": True})
        except Exception as e: print("telegram FAILED:", e)

PF = {"ig": "Instagram", "x": "X", "fb": "Facebook", "th": "Threads"}

if __name__ == "__main__":
    try: old = [p for p in json.load(open(OUT)).get("posts", []) if not p.get("demo")]
    except Exception: old = []
    db = {p["key"]: p for p in old}
    known = {c["id"]: c["s"] for p in old for c in p["comments"] if c.get("id") and c.get("s")}
    first_run = not old
    for fn in (instagram, facebook, threads, x_twitter):
        try:
            got = fn(); print(fn.__name__, len(got), "posts")
            for p in got: db[p["key"]] = p
        except Exception as e:
            print(fn.__name__, "FAILED:", e)  # one platform failing must not stop the rest

    # sentiment: reuse old scores, score only NEW comments (Claude if key set, else keyword fallback)
    new = []
    for p in db.values():
        for c in p["comments"]:
            if c.get("s") is None: c["s"] = known.get(c["id"])
            if c["s"] is None: new.append((p, c))
    labels = None
    try: labels = claude_sentiment([c["text"] for _, c in new]); print("claude scored", len(new))
    except Exception as e: print("Claude sentiment FAILED, using keyword fallback:", e)
    for i, (p, c) in enumerate(new): c["s"] = labels[i] if labels else sentiment(c["text"])

    # alerts (skipped on first run to avoid a flood of old items)
    if not first_run:
        old_keys = {p["key"] for p in old}
        if env("NOTIFY_NEW_POSTS") == "1":
            for p in db.values():
                if p["key"] not in old_keys:
                    telegram(f"🆕 Parlimen post on {PF[p['platform']]}\n{p['text'][:200]}\n{p['url']}")
        neg = [(p, c) for p, c in new if c["s"] == "neg"]
        min_neg, min_pct = int(env("ALERT_MIN_NEG") or 5), int(env("ALERT_NEG_PCT") or 40)
        if len(neg) >= min_neg and len(neg) * 100 / max(len(new), 1) >= min_pct:
            by = {}
            for p, c in neg: by.setdefault(p["key"], [p, 0]); by[p["key"]][1] += 1
            lines = [f"• {PF[p['platform']]}: {n} negatif - {p['text'][:60]} {p['url']}" for p, n in sorted(by.values(), key=lambda x: -x[1])[:5]]
            telegram(f"🚨 NEGATIVE SPIKE: {len(neg)} of {len(new)} new comments are negative\n" + "\n".join(lines))

    posts = sorted(db.values(), key=lambda p: p["time"], reverse=True)
    if not posts:  # nothing collected (no secrets set, or API errors): don't overwrite the data file with an empty one
        print("No posts collected. Check your secrets/tokens and the errors above. Data file left unchanged.")
        raise SystemExit(0)
    json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "posts": posts}, open(OUT, "w"), ensure_ascii=False)
    print("saved", len(posts), "posts;", len(new), "new comments")

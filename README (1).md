# Parlimen Malaysia – Social Media Monitor

Near-live dashboard for Instagram, X, Facebook and Threads: detects new posts, collects public comments, scores sentiment, and writes a monthly summary.

**How it works (no server needed)**
`GitHub Actions (every 15 min)` → `collector/collect.py` → `docs/data/posts.json` → `GitHub Pages dashboard` (re-reads data every 60 s).

## Setup
1. Create a GitHub repo and push this folder.
2. **Settings → Pages**: Source = *Deploy from a branch*, branch `main`, folder `/docs`.
3. **Settings → Secrets and variables → Actions**, add (only for platforms you use):

| Secret | What |
|---|---|
| `META_TOKEN`, `IG_USER_ID` | Instagram Business/Creator account via Meta Graph API |
| `META_TOKEN`, `FB_PAGE_ID` | Facebook Page access token (permissions: `pages_read_engagement`, `pages_read_user_content`) |
| `THREADS_TOKEN`, `THREADS_USER_ID` | Threads API token (`threads_basic`, `threads_read_replies`, `threads_manage_insights`) |
| `X_BEARER_TOKEN`, `X_USER_ID` | X API v2 (paid tier needed for reading replies) |

4. *(Optional)* **AI sentiment + Telegram alerts** – add these secrets:

| Secret | What |
|---|---|
| `ANTHROPIC_API_KEY` | Claude scores each *new* comment (Malay/English/slang/sarcasm). Without it, the keyword scorer is used. Uses Haiku (low cost); each comment is scored only once. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Create a bot with @BotFather, send it a message, get your chat id (e.g. via `https://api.telegram.org/bot<TOKEN>/getUpdates`). |

   Optional **variables** (Settings → Variables → Actions): `NOTIFY_NEW_POSTS=1` (alert on every new post), `ALERT_MIN_NEG` (default 5), `ALERT_NEG_PCT` (default 40). A spike alert fires when a run finds at least `ALERT_MIN_NEG` new negative comments making up at least `ALERT_NEG_PCT`% of new comments. No alerts on the very first run.

5. **Actions → Collect social media data → Run workflow** to test. Dashboard URL: `https://<user>.github.io/<repo>/`

## Important notes
- Meta/Threads tokens only read accounts you manage. Parlimen's IT/media team must generate them. Meta tokens expire (~60 days) and need refreshing.
- GitHub cron runs every 15 min at best and may be delayed. For true real-time, run `collect.py` on a small server/VPS or use Meta webhooks.
- Keep the repo **private** if you do not want comment data public (Pages on private repos needs a paid GitHub plan).
- Comment text is sent to Anthropic's API for scoring when `ANTHROPIC_API_KEY` is set. Check this is acceptable for your data policy.
- Comply with each platform's terms and Malaysia's PDPA when storing comments.

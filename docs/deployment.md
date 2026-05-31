# Deploying solar-sim on Ubuntu with Cloudflare Tunnel

End-to-end guide to running the multi-user app (`app/app.py`) on an
Ubuntu laptop, with students reaching it over HTTPS via Cloudflare
Tunnel. Written for a classroom pilot.

```
Browser → solar-sim.<your-domain> (Cloudflare) → Cloudflare Tunnel
       → http://127.0.0.1:8501  (Streamlit, behind systemd)
```

If you have already deployed `uni_dashboard` from the
`ubuntu-server-setup-guide.txt` recipe, you already have the laptop,
SSH access, the tunnel, and the `~/apps/` convention. This guide picks
up at "add a new app to the existing setup".

---

## Prerequisites on the server

A one-time check. Skip the items already done for previous apps.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# System libraries required by weasyprint (for the PDF download buttons).
# Without these, PDF buttons gracefully fall back to a "PDF unavailable"
# caption — the rest of the app still runs.
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0
```

---

## 1. Pull the code

```bash
cd ~/apps
git clone git@github.com:quantumjazz/solar-sim.git
cd solar-sim
```

If you keep solar-sim in a different repo layout (e.g. it sits inside
a parent repo), adjust the clone command. The rest of this guide
assumes the working directory is `~/apps/solar-sim`.

---

## 2. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Verify the engine and app test suites:

```bash
cd sim-engine && PYTHONPATH=src ../.venv/bin/python -m pytest && cd -
PYTHONPATH=sim-engine/src:app .venv/bin/python -m pytest app/
```

You should see 36 engine tests passing and 73 app tests collected
(72 pass, 1 PDF round-trip is now in scope because weasyprint is
installed). If the PDF test still skips, double-check the apt step
above and reinstall weasyprint.

---

## 3. Production environment file

```bash
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Fill in:

- `SOLAR_SIM_DB` — keep the default `/home/victor/apps/solar-sim/solar-sim.db`
  unless you have a reason to move it.
- `SOLAR_SIM_INSTRUCTOR_TOKEN` — generate a long random string, e.g.
  `python3 -c 'import secrets; print(secrets.token_urlsafe(24))'`. You
  will enter this once in the registration form to create your own
  instructor account; students never see the field.
- `SOLAR_SIM_PUBLIC_URL` — the URL students will visit, e.g.
  `https://solar-sim.visiometrica.com`. Used by the "Onboarding
  instructions for students" panel to pre-fill the copy-paste block.

Important: setting `SOLAR_SIM_INSTRUCTOR_TOKEN` also **disables the
dev-mode default admin seed** (`admin@solar-sim.local / tester`).
This is intentional — a publicly-reachable instance must never ship
with a known password. You'll create your own account in §6.

---

## 4. systemd unit

A template lives at `deploy/solar-sim.service`. Install it:

```bash
sudo cp deploy/solar-sim.service /etc/systemd/system/solar-sim.service
sudo systemctl daemon-reload
sudo systemctl enable --now solar-sim
sudo systemctl status solar-sim
```

If the status output shows `active (running)`, you're good. If it
shows a failure:

```bash
sudo journalctl -u solar-sim -n 80 --no-pager
```

Common causes:

- `User=victor` doesn't match your actual username — edit the unit.
- `WorkingDirectory` doesn't match where you cloned the repo — edit
  the unit.
- weasyprint import error — re-run the apt step in *Prerequisites*.

Confirm Streamlit is listening locally:

```bash
curl -I http://127.0.0.1:8501
```

You should get a `200` or `303` response from Streamlit.

---

## 5. Cloudflare Tunnel route

The existing `laptop-server` tunnel was set up for previous apps.
Add solar-sim to its ingress list:

```bash
sudo nano /etc/cloudflared/config.yml
```

Add a new entry **before** the catch-all `http_status:404`:

```yaml
ingress:
  - hostname: uni-dashboard.visiometrica.com
    service: http://127.0.0.1:8000

  - hostname: solar-sim.visiometrica.com   # ← add this block
    service: http://127.0.0.1:8501

  - service: http_status:404
```

Route DNS and restart the tunnel:

```bash
cloudflared tunnel route dns laptop-server solar-sim.visiometrica.com
sudo systemctl restart cloudflared
sudo systemctl status cloudflared
```

Within ~30 seconds, `https://solar-sim.visiometrica.com` should
serve the login page over HTTPS.

---

## 6. First-run: create your instructor account

Open the deployed URL in a browser. You'll see the **Log in /
Create an account** tabs. Because `SOLAR_SIM_INSTRUCTOR_TOKEN` is
set, the dev-admin caption is hidden and the database is empty.

1. Click **Create an account**.
2. Enter your display name and a username (or email).
3. Pick a strong password.
4. Select role **Instructor** — an "Instructor registration token"
   field appears.
5. Paste the value of `SOLAR_SIM_INSTRUCTOR_TOKEN`.
6. Click **Create account**.

You are now logged in as the instructor. Create a cohort, add team
names, and you're ready to onboard students.

---

## 7. Onboarding students

On the cohort detail page, **Teams & members** tab, expand
**Onboarding instructions for students**. The block is pre-filled
with `SOLAR_SIM_PUBLIC_URL` and the cohort name — copy it and send
to your students.

A student's journey:

1. Visits the URL, clicks **Create an account**.
2. Picks a short username (e.g. `alice`) or uses their email, plus a
   password.
3. Lands on a "waiting for assignment" screen. The screen auto-
   refreshes every ~3 seconds.
4. You select them from the **Assign a student to a team** dropdown
   and click **Assign**. Their screen flips to their team's
   dashboard within ~3 seconds, no manual reload needed.

---

## 8. Day-of operations

**Watch live logs:**
```bash
sudo journalctl -u solar-sim -f
```

**Restart the app** (after a `git pull` or env change):
```bash
sudo systemctl restart solar-sim
```

**Reset the database between pilot sessions:**
```bash
./scripts/reset-db.sh
```
This stops the service, backs up `solar-sim.db` to a timestamped
`.db.bak`, removes the live DB and WAL files, and restarts. The
first request afterwards re-creates the schema. You will need to
re-register your instructor account.

**Update the app from main:**
```bash
cd ~/apps/solar-sim
git fetch origin
git pull --ff-only origin main
.venv/bin/pip install -r requirements.txt
sudo systemctl restart solar-sim
```

---

## 9. Troubleshooting

**The browser shows a Cloudflare 502 / 530.** The tunnel reached the
server but Streamlit isn't responding. Check
`sudo systemctl status solar-sim` and the journal.

**WebSocket connection fails / page stuck on "Please wait…".**
Check the systemd unit has `--server.enableCORS=false` and
`--server.enableXsrfProtection=false`. Streamlit's defaults reject
the cross-origin WS upgrade Cloudflare delivers.

**"PDF unavailable on this server" caption** under the download
buttons. weasyprint or the pango/cairo system libraries didn't
install. Re-run the apt step in *Prerequisites* and reinstall
weasyprint inside the venv (`.venv/bin/pip install --force-reinstall
weasyprint`), then `sudo systemctl restart solar-sim`.

**Students can't log in after a reset.** A reset wipes everyone,
including your instructor account. Re-register yours (with the
token), then re-create the cohort and re-onboard.

**A student forgot their password.** No self-serve recovery; for a
pilot, ask them to register a second account, then move them onto
their original team (the old account can be left in place or deleted
from the `users` table by hand).

**Laptop went to sleep mid-session.** See the lid-close and
auto-suspend settings in `ubuntu-server-setup-guide.txt`.

---

## 10. Pilot checklist

A short pre-class run-through:

- [ ] Service is active: `systemctl status solar-sim`
- [ ] Tunnel is active: `systemctl status cloudflared`
- [ ] Database is in the state you expect (fresh, or with last
      session's data)
- [ ] You can log in as your instructor account
- [ ] You've created the cohort and team names
- [ ] You've shared `SOLAR_SIM_PUBLIC_URL` with students
- [ ] You have the laptop on power, lid open or
      `HandleLidSwitchExternalPower=ignore` set

# GyanSankalp

An online preparation platform for **Lok Sewa Aayog** (Nepal Public Service Commission) exams. Staff publish courses, break them into topics, and attach the study PDF for each topic. Every PDF is converted into page images and read in the browser, so a student never downloads the original file. Students sign up, request a course, and read what they have been approved for.

Courses carry a price in NPR. Payment is settled outside the app and an administrator approves the enrollment, which is what grants access — no payment gateway is wired in.

## How sign-in works

There are two independent systems, deliberately kept apart:

- **Students** sign in with Google, or with email and password after confirming their address through a mailed link.
- **Staff** have no password at all. They sign in with Google, then a single-use code is mailed to that same inbox, and only reading the mail completes the login. Staff accounts are seeded from a roster file — there is no public staff registration.

Admin sessions are signed with a different key from student sessions, so a leaked student-token secret cannot mint an admin token. Staff roles (`super_admin`, `content_manager`, `editor`) decide what each person can see and do, and every staff action is recorded in an audit log.

Uploaded PDFs are converted by a separate worker process, never inside the request that receives the upload. Page images are served only to a student enrolled in that course.

## Where it runs

| | URL | Host |
| --- | --- | --- |
| Website | https://gyansankalp.pages.dev | Cloudflare Pages |
| API | https://gyansankalp-api.onrender.com | Render (free) |
| Conversion worker | https://gyansankalp-worker.onrender.com | Render (free) |
| Database and file storage | — | Supabase (Singapore, free) |

Everything is on free tiers, which shapes two behaviours worth knowing: both Render services sleep after 15 idle minutes, so the first request after a gap takes 30–60 seconds, and the worker is woken by the admin's browser when a PDF needs converting rather than being kept running around the clock.

Running with `APP_ENV=production` refuses to start on a configuration it considers unsafe — a short or shared JWT secret, a database connection without TLS, an `http` CORS origin, or documentation endpoints switched on.

## Running it locally

You need Python 3.13 or newer, Node 22 and Docker.

**1. Start Postgres and object storage**

```bash
docker compose up -d
```

**2. Set up the API**

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in the values it explains at the top of each block. The ones that stop the app from booting:

- `DATABASE_URL` — the port in `compose.yml` is `5433`, not `5432`.
- `JWT_SECRET` and `ADMIN_JWT_SECRET` — any two different long strings:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- `S3_ACCESS_KEY` / `S3_SECRET_KEY` — the MinIO credentials from `compose.yml`.

Then create the schema and your first staff account:

```bash
alembic upgrade head
python -m app.scripts.seed_staff   # reads STAFF_ROSTER from .env
uvicorn app.main:app --reload      # http://localhost:8000, docs at /docs
```

**3. Start the conversion worker** in a second terminal:

```bash
cd Backend && python -m app.worker
```

**4. Set up the website** in a third terminal:

```bash
cd web
npm install
```

Create `web/.env` with two lines — `VITE_API_URL=http://localhost:8000` and `VITE_GOOGLE_CLIENT_ID=...`, the client id from Google Cloud Console (an OAuth client of type *Web application*; add `http://localhost:5173` under Authorized JavaScript origins). Then:

```bash
npm run dev    # http://localhost:5173
```

**Google sign-in and real email are optional locally, but sign-in needs one of them.** Without `VITE_GOOGLE_CLIENT_ID` the Google buttons are not rendered, and without `GOOGLE_CLIENT_ID` the API refuses Google sign-in outright — so a fresh clone with neither can only browse. Staff have no password fallback, which means signing in as staff requires the client id.

Email is the part you can skip: with no SMTP sender configured, verification links and staff codes are printed to the API's console log instead of being sent, so a staff login can be completed locally without a mail account. In `production` that fallback is switched off and the guard refuses to boot without a sender.

**Tests**

```bash
cd Backend && pytest
```

They run against the `DATABASE_URL` in `.env` and delete rows, so they point themselves at a throwaway database and skip if they do not get one: any database whose name contains `test`. Create it once and point the run at it, using the development Postgres credentials from `compose.yml`:

```bash
docker compose exec db psql -U postgres -c "CREATE DATABASE gyansankalp_test"
DATABASE_URL=postgresql+psycopg://postgres:<local-dev-password>@localhost:5433/gyansankalp_test pytest
```

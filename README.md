# 🎃 Halloween Quiz Certificate Generator API

A Flask API that generates a Halloween-themed certificate from your uploaded
template image. It draws the **name**, **score**, and **current date of issue**
onto the template using Pillow — ready to deploy on **Vercel** as a serverless
Python function.

![Sample certificate](sample_output.png)

## Features

- ✅ Uses your uploaded Halloween template (`assets/certificate_template.png`, 2784×1504)
- ✅ Inputs: `name` + `score` (two parameters, as requested)
- ✅ Auto date of issue — today's date in Asia/Kolkata, e.g. `15 November 2026`
- ✅ Halloween theme: Creepster title, gold script name, orange score badge
- ✅ Returns PNG (default) or lightweight JPG (`?format=jpg`)
- ✅ CORS enabled, works from any frontend
- ✅ Vercel-ready (`vercel.json` + `api/index.py`)

## Project structure

```
halloween-certificate-api/
├── api/
│   └── index.py              # Flask app (Vercel entrypoint)
├── app.py                    # Local dev entrypoint
├── assets/
│   ├── certificate_template.png   # Your uploaded template
│   └── fonts/                     # Creepster, Cinzel, Great Vibes, Poppins
├── vercel.json               # Functions config only (NO rewrites — see deploy note)
├── requirements.txt
└── README.md
```

## API endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/` | Landing page with a live generate form |
| GET | `/health` | Health check → `{"status":"ok"}` |
| GET | `/certificate?name=Aarav&score=14` | Certificate image (PNG) |
| GET | `/certificate/Aarav/14` | Same, via path params |
| POST | `/certificate` | JSON body `{"name":"Aarav","score":14}` → image |
| GET/POST | `/api/certificate...` | Alias (same handlers) |

### Parameters

| Param | Required | Description |
|---|---|---|
| `name` | ✅ | Participant name, e.g. `Aarav Sharma` |
| `score` | ✅ | Score — `14`, `14/15`, `8/10` all work (quiz range **0–15**) |
| `total` | optional | Total when score is a plain number (default `15`) |
| `date` | optional | Override date of issue, e.g. `31 October 2026` |
| `format` | optional | `png` (default), `jpg`, or `json` (base64 response) |
| `download` | optional | `true` → download as file instead of inline preview |

### Examples

```bash
# 1) Browser / img tag — PNG
https://YOUR-PROJECT.vercel.app/certificate?name=Aarav%20Sharma&score=14

# 2) Lightweight JPG (recommended for web)
https://YOUR-PROJECT.vercel.app/certificate?name=Aarav%20Sharma&score=14&format=jpg

# 3) Path style
https://YOUR-PROJECT.vercel.app/certificate/Aarav%20Sharma/14

# 4) Download as file
https://YOUR-PROJECT.vercel.app/certificate?name=Aarav&score=14&download=true

# 5) POST JSON (returns image)
curl -X POST https://YOUR-PROJECT.vercel.app/certificate \
  -H "Content-Type: application/json" \
  -d '{"name":"Aarav Sharma","score":14}' --output certificate.png

# 6) POST JSON → base64 (for apps that store the image)
curl -X POST https://YOUR-PROJECT.vercel.app/certificate \
  -H "Content-Type: application/json" \
  -d '{"name":"Aarav Sharma","score":14,"format":"json"}'

# 7) Override total (default is 15)
https://YOUR-PROJECT.vercel.app/certificate?name=Aarav&score=8&total=10  # override if needed
```

### Frontend usage (JavaScript)

```html
<img id="cert" alt="Certificate">

<script>
  const name = "Aarav Sharma";
  const score = 14;
  document.getElementById("cert").src =
    `/certificate?name=${encodeURIComponent(name)}&score=${score}&format=jpg`;
</script>
```

Or fetch as a blob and trigger a download:

```js
const res = await fetch(`/certificate?name=${encodeURIComponent(name)}&score=${score}`);
const blob = await res.blob();
const a = document.createElement("a");
a.href = URL.createObjectURL(blob);
a.download = "Halloween_Quiz_Certificate.png";
a.click();
```

## Run locally

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

## Deploy on Vercel

**Option A — Vercel CLI**

```bash
npm i -g vercel
vercel login
vercel        # follow prompts; framework: Other, build: none
vercel --prod
```

**Option B — GitHub + Vercel dashboard**

1. Push this folder to a GitHub repo.
2. Go to [vercel.com/new](https://vercel.com/new) → import the repo.
3. Framework preset: **Flask** (important — not "Other").
4. Deploy — Vercel auto-detects the Flask app in `api/index.py` / `app.py`
   and routes every request to it with its original path.

> ⚠️ Do **not** add a catch-all rewrite (`/(.*)` → `/api/index.py`) to
> `vercel.json`. Vercel's Flask integration already routes all requests to
> Flask; a rewrite makes Flask receive `PATH_INFO=/api/index.py` for every
> request, which has no route — so every URL returns Flask's 404 page.
> The included `vercel.json` intentionally has **no rewrites**, only
> `functions` config to bundle `assets/**` (template + fonts) and set
> `maxDuration`.

> No environment variables are needed. Pillow and Flask are installed
> automatically from `requirements.txt`.

## Customisation

- **Template:** replace `assets/certificate_template.png` with any image
  (keep the same filename). Layout positions are relative to image size,
  so other aspect ratios still work.
- **Fonts:** add/replace files in `assets/fonts/` and update `FONT_FILES`
  in `api/index.py`.
- **Text positions/colours:** edit `generate_certificate()` in `api/index.py`.
- **Date format:** change `current_date_str()` (currently `%d %B %Y`,
  Asia/Kolkata timezone).

## Notes

- PNG output uses fast compression (`compress_level=1`) so it stays within
  Vercel's serverless time limits — use `format=jpg` for the smallest files.
- Long names automatically shrink to fit the certificate width.
- Score validation: scores outside **0–15** return `400 {"error": "Score must be between 0 and 15", "score_range": "0-15"}`.
- Missing `name`/`score` returns `400 {"error": "Missing required parameter: ..."}`.

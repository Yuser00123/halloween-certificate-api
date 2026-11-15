"""
Halloween Quiz Certificate Generator API
=========================================
Flask app designed for Vercel (serverless) + local development.

Endpoints
---------
GET  /                                  -> Landing page with live form
GET  /health                            -> {"status": "ok"}
GET  /certificate?name=John&score=13    -> PNG certificate image (score range 0-15)
GET  /certificate/<name>/<score>        -> PNG certificate image (path params)
POST /certificate                       -> JSON {"name": "...", "score": ...} -> PNG
GET  /api/certificate?...               -> alias of /certificate (Vercel friendly)

Optional query params
---------------------
download=true   -> force file download instead of inline preview
format=json     -> return JSON with base64 data URI instead of image
total=15        -> total score used when score is a plain number (default 15; quiz range is 0-15)
date=15 November 2026 -> override date of issue (defaults to today, Asia/Kolkata)

Template: assets/certificate_template.png (your uploaded Halloween image)
Fonts:    assets/fonts/*.ttf (Creepster, Cinzel, Great Vibes, Poppins)
"""

import base64
import io
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, Response, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths (work both locally and on Vercel where this file lives in /api)
# ---------------------------------------------------------------------------
THIS_DIR = Path(__file__).resolve().parent          # .../api
BASE_DIR = THIS_DIR.parent                           # project root
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

TEMPLATE_CANDIDATES = [
    ASSETS_DIR / "certificate_template.png",
    THIS_DIR / "certificate_template.png",
    Path.cwd() / "assets" / "certificate_template.png",
    Path("/home/user/halloween-certificate-api/assets/certificate_template.png"),
]

FONT_FILES = {
    "creepster": FONTS_DIR / "Creepster-Regular.ttf",
    "cinzel": FONTS_DIR / "Cinzel-Bold.ttf",
    "script": FONTS_DIR / "GreatVibes-Regular.ttf",
    "poppins": FONTS_DIR / "Poppins-Regular.ttf",
    "poppins_bold": FONTS_DIR / "Poppins-Bold.ttf",
    "poppins_semi": FONTS_DIR / "Poppins-SemiBold.ttf",
    "montserrat": FONTS_DIR / "Montserrat-Regular.ttf",
}

# Fallback system fonts if bundled fonts are missing
FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "certificate_template.png not found. Place it in assets/certificate_template.png"
    )


def get_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a bundled font, falling back to DejaVu if needed."""
    path = FONT_FILES.get(kind)
    if path and path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    for fb in FALLBACK_FONTS:
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size)
            except Exception:
                continue
    return ImageFont.load_default()


def fit_font(kind: str, text: str, max_width: int, start_size: int, min_size: int = 28):
    """Shrink font until text fits max_width."""
    size = start_size
    while size > min_size:
        font = get_font(kind, size)
        # textlength needs a dummy draw; use font.getlength
        try:
            w = font.getlength(text)
        except Exception:
            w = size * len(text) * 0.6
        if w <= max_width:
            return font, size
        size -= 4
    return get_font(kind, min_size), min_size


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[float, float]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered(draw, cx, y, text, font, fill, shadow=True, shadow_offset=3):
    """Draw text centered at (cx, y) with optional soft shadow/glow."""
    w, h = text_size(draw, text, font)
    x = cx - w / 2
    if shadow:
        # dark shadow for readability on the light fog background
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=(10, 8, 35, 220))
        draw.text((x - shadow_offset, y + shadow_offset), text, font=font, fill=(10, 8, 35, 140))
    draw.text((x, y), text, font=font, fill=fill)
    return w, h


def draw_spaced_centered(draw, cx, y, text, font, fill, spacing=10, shadow=True):
    """Draw letter-spaced text centered at cx."""
    # measure total width
    widths = []
    total = 0
    for ch in text:
        try:
            w = font.getlength(ch)
        except Exception:
            w = 20
        widths.append(w)
        total += w
    total += spacing * (len(text) - 1)
    x = cx - total / 2
    if shadow:
        sx = x
        for ch, w in zip(text, widths):
            draw.text((sx + 2, y + 2), ch, font=font, fill=(10, 8, 35, 200))
            sx += w + spacing
    sx = x
    for ch, w in zip(text, widths):
        draw.text((sx, y), ch, font=font, fill=fill)
        sx += w + spacing
    return total


def current_date_str() -> str:
    """Today's date in Asia/Kolkata (user timezone), e.g. '15 November 2026'."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now = datetime.now()
    return now.strftime("%d %B %Y")


DEFAULT_TOTAL = 15  # Halloween Quiz score range is 0-15


def validate_score(score_raw, total_raw=None):
    """Return an error string if score is outside the 0-15 range, else None."""
    total_val = 15.0
    if total_raw is not None and str(total_raw).strip() != "":
        try:
            total_val = float(str(total_raw).strip())
        except ValueError:
            return "Invalid total: must be a number (default 15)"
    s = str(score_raw).strip()
    try:
        if "/" in s:
            num_s, den_s = s.split("/", 1)
            num, den = float(num_s.strip()), float(den_s.strip())
            if den != total_val:
                return f"Score total must be {int(total_val) if total_val.is_integer() else total_val} (range 0-{int(total_val) if total_val.is_integer() else total_val}), got {den_s.strip()}"
            if not (0 <= num <= den):
                return f"Score must be between 0 and {int(den) if den.is_integer() else den}"
        elif "%" in s:
            num = float(s.rstrip("%").strip())
            if not (0 <= num <= 100):
                return "Score percentage must be between 0% and 100%"
        else:
            num = float(s)
            if not (0 <= num <= total_val):
                return f"Score must be between 0 and {int(total_val) if total_val.is_integer() else total_val}"
    except ValueError:
        return "Invalid score: must be a number between 0 and 15 (e.g. 13 or 13/15)"
    return None


def format_score(score_raw, total_raw=None) -> str:
    """
    Normalise score for display.
    - '13/15', '13 / 15'           -> kept as-is (cleaned)
    - plain number 13               -> '13 / 15' (or / total if given)
    - plain number with total=10    -> '8 / 10'
    """
    s = str(score_raw).strip()
    if "/" in s or "%" in s:
        return s.replace(" ", "")
    # plain number (int or float)
    try:
        num = float(s)
        num_str = str(int(num)) if num.is_integer() else str(num)
    except ValueError:
        return s  # non-numeric score, show as-is
    total = str(total_raw).strip() if total_raw else str(DEFAULT_TOTAL)
    # If score is clearly out of range, don't force /15
    try:
        if float(total) < float(num):
            return num_str
    except Exception:
        pass
    return f"{num_str} / {total}"


def generate_certificate(name: str, score_raw, total=None, date_str=None) -> Image.Image:
    """Render name + score + date onto the Halloween template."""
    template_path = find_template()
    img = Image.open(template_path).convert("RGBA")
    W, H = img.size
    cx = W // 2

    # --- subtle dark panel behind the main text block for readability ---
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    panel_x0, panel_x1 = int(W * 0.18), int(W * 0.82)
    panel_y0, panel_y1 = int(H * 0.125), int(H * 0.78)
    odraw.rounded_rectangle(
        [panel_x0, panel_y0, panel_x1, panel_y1],
        radius=48,
        fill=(18, 10, 45, 92),          # deep purple, translucent
        outline=(255, 150, 50, 70),
        width=3,
    )
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    ORANGE = (255, 138, 30, 255)
    ORANGE_LIGHT = (255, 190, 80, 255)
    GOLD = (255, 209, 102, 255)
    WHITE = (255, 255, 255, 255)
    CREAM = (255, 244, 214, 255)
    MUTED = (214, 220, 255, 255)

    # --- Title: HALLOWEEN QUIZ (Creepster, spooky display) ---
    title_font, _ = fit_font("creepster", "HALLOWEEN QUIZ", int(W * 0.62), int(H * 0.115), 60)
    # orange glow: draw blurred-ish by multiple offsets
    tw, th = text_size(draw, "HALLOWEEN QUIZ", title_font)
    tx, ty = cx - tw / 2, H * 0.145
    for dx, dy, col in [(0, 6, (120, 30, 0, 160)), (0, 3, (255, 90, 0, 160))]:
        draw.text((tx + dx, ty + dy), "HALLOWEEN QUIZ", font=title_font, fill=col)
    draw.text((tx, ty), "HALLOWEEN QUIZ", font=title_font, fill=ORANGE)

    # --- Subtitle: CERTIFICATE OF ACHIEVEMENT (letter-spaced) ---
    sub_font = get_font("cinzel", int(H * 0.034))
    sub_y = H * 0.265
    draw_spaced_centered(draw, cx, sub_y, "CERTIFICATE OF ACHIEVEMENT", sub_font, WHITE, spacing=8)
    # decorative lines either side of subtitle
    line_y = sub_y + int(H * 0.028)
    line_len = int(W * 0.10)
    gap = int(W * 0.225)
    draw.line([(cx - gap - line_len, line_y), (cx - gap, line_y)], fill=ORANGE_LIGHT, width=3)
    draw.line([(cx + gap, line_y), (cx + gap + line_len, line_y)], fill=ORANGE_LIGHT, width=3)
    # small diamond in centre below subtitle
    dy = line_y + 14
    draw.polygon([(cx, dy - 7), (cx + 7, dy), (cx, dy + 7), (cx - 7, dy)], fill=ORANGE)

    # --- "This certificate is proudly presented to" ---
    presented_font = get_font("poppins", int(H * 0.026))
    draw_centered(draw, cx, H * 0.345, "This certificate is proudly presented to", presented_font, MUTED)

    # --- Name (script font, large, gold) ---
    name_font, _ = fit_font("script", name, int(W * 0.60), int(H * 0.095), 44)
    nw, nh = text_size(draw, name, name_font)
    name_y = H * 0.395
    # glow
    draw.text((cx - nw / 2 + 3, name_y + 4), name, font=name_font, fill=(10, 8, 35, 220))
    draw.text((cx - nw / 2, name_y), name, font=name_font, fill=GOLD)
    # (underline flourish removed — it cut through script names like "aarav")

    # --- "for successfully completing the Halloween Quiz" ---
    desc_font = get_font("poppins", int(H * 0.027))
    draw_centered(
        draw, cx, H * 0.545,
        "for successfully completing the Halloween Quiz",
        desc_font, CREAM,
    )

    # --- Score badge ---
    score_display = format_score(score_raw, total)
    badge_text = f"SCORE:  {score_display}"
    badge_font = get_font("poppins_bold", int(H * 0.034))
    bw, bh = text_size(draw, badge_text, badge_font)
    pad_x, pad_y = 46, 22
    badge_w, badge_h = bw + pad_x * 2, bh + pad_y * 2
    badge_y = H * 0.615
    bx0, by0 = cx - badge_w / 2, badge_y
    bx1, by1 = cx + badge_w / 2, badge_y + badge_h
    draw.rounded_rectangle(
        [bx0, by0, bx1, by1], radius=badge_h // 2,
        fill=(30, 12, 60, 200), outline=ORANGE, width=4,
    )
    draw_centered(draw, cx, by0 + pad_y - 4, badge_text, badge_font, ORANGE_LIGHT)

    # --- Date of Issue (bottom centre, below panel) ---
    date_display = date_str or current_date_str()
    date_font = get_font("poppins_semi", int(H * 0.026))
    date_label = f"Date of Issue:  {date_display}"
    dw, dh = text_size(draw, date_label, date_font)
    date_y = H * 0.815
    # small pill behind date for readability over foliage
    dpad_x, dpad_y = 30, 14
    draw.rounded_rectangle(
        [cx - dw / 2 - dpad_x, date_y - dpad_y, cx + dw / 2 + dpad_x, date_y + dh + dpad_y],
        radius=24, fill=(12, 8, 38, 170), outline=(255, 190, 80, 90), width=2,
    )
    draw_centered(draw, cx, date_y, date_label, date_font, WHITE)

    # --- tiny footer ---
    foot_font = get_font("poppins", int(H * 0.016))
    draw_centered(draw, cx, H * 0.885, "~  Happy Halloween  ~", foot_font, MUTED)

    return img.convert("RGB")


def certificate_response(name, score, total=None, date_str=None, download=False, as_json=False, fmt="png"):
    """Build the Flask response (image or JSON) for a certificate request."""
    if not name or not str(name).strip():
        return jsonify({"error": "Missing required parameter: name"}), 400
    if score is None or str(score).strip() == "":
        return jsonify({"error": "Missing required parameter: score"}), 400

    score_error = validate_score(score, total)
    if score_error:
        return jsonify({"error": score_error, "score_range": "0-15"}), 400

    name = str(name).strip()[:80]
    fmt = str(fmt or "png").lower()
    if fmt in ("jpg", "jpeg"):
        fmt = "jpeg"
    elif fmt != "png":
        fmt = "png"
    if as_json:
        fmt = "jpeg"  # keep base64 JSON payload small (~800 KB vs ~12 MB for PNG)
    try:
        img = generate_certificate(name, score, total=total, date_str=date_str)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:  # pragma: no cover
        return jsonify({"error": f"Failed to generate certificate: {e}"}), 500

    buf = io.BytesIO()
    if fmt == "jpeg":
        # JPEG is ~8x smaller and instant — ideal for web preview / Vercel
        img.save(buf, format="JPEG", quality=90, optimize=True)
        mime, ext = "image/jpeg", "jpg"
    else:
        # compress_level=1 keeps PNG fast on serverless (optimize=True takes ~10s!)
        img.save(buf, format="PNG", compress_level=1)
        mime, ext = "image/png", "png"
    buf.seek(0)

    if as_json:
        b64 = base64.b64encode(buf.getvalue()).decode()
        return jsonify({
            "name": name,
            "score": format_score(score, total),
            "date_of_issue": date_str or current_date_str(),
            "image_base64": b64,
            "data_uri": f"data:{mime};base64,{b64}",
        })

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ", "_")
    filename = f"Halloween_Quiz_Certificate_{safe_name}.{ext}"
    resp = send_file(
        buf,
        mimetype=mime,
        as_attachment=download,
        download_name=filename,
    )
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Certificate-Name"] = name
    return resp


def parse_inputs():
    """Accept inputs from query string, JSON body, or form data."""
    name = request.args.get("name")
    score = request.args.get("score")
    total = request.args.get("total")
    date_str = request.args.get("date")
    download = request.args.get("download", "").lower() in ("1", "true", "yes")
    fmt = request.args.get("format", "png").lower()
    as_json = fmt == "json"
    if fmt not in ("png", "jpg", "jpeg", "json"):
        fmt = "png"

    if request.is_json:
        data = request.get_json(silent=True) or {}
        name = name or data.get("name")
        score = score if score is not None else data.get("score")
        total = total or data.get("total")
        date_str = date_str or data.get("date")
        download = download or bool(data.get("download"))
        if data.get("format"):
            fmt = str(data.get("format")).lower()
            as_json = fmt == "json"
    elif request.form:
        name = name or request.form.get("name")
        score = score if score is not None else request.form.get("score")
        total = total or request.form.get("total")
        date_str = date_str or request.form.get("date")

    return name, score, total, date_str, download, as_json, fmt


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.after_request
def add_cors(resp: Response):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/", methods=["GET"])
def index():
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Halloween Quiz Certificate Generator</title>
<style>
 body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0b0620;color:#fff;
      min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
 .card{max-width:640px;width:100%;background:linear-gradient(160deg,#1b0f3a,#2a1458);border:1px solid #ff8a1e55;
       border-radius:20px;padding:28px;box-shadow:0 20px 60px #0009}
 h1{margin:0 0 6px;font-size:28px;color:#ff8a1e} p{color:#cfd6ff;line-height:1.5}
 label{display:block;margin:14px 0 6px;font-weight:600} input{width:100%;padding:12px;border-radius:10px;border:1px solid #ffffff33;background:#0b0620;color:#fff;font-size:16px;box-sizing:border-box}
 button{margin-top:18px;width:100%;padding:13px;border:0;border-radius:10px;background:#ff8a1e;color:#1b0f3a;font-weight:800;font-size:16px;cursor:pointer}
 button:hover{background:#ffa94d} img{max-width:100%;border-radius:12px;margin-top:18px;display:none}
 code{background:#0b0620;padding:2px 6px;border-radius:6px} .api{background:#0b0620;border:1px solid #ffffff22;border-radius:10px;padding:12px;overflow:auto;font-size:13px}
</style></head><body><div class="card">
<h1>🎃 Halloween Quiz Certificate Generator</h1>
<p>Enter a name and score to generate a certificate instantly.</p>
<form id="f">
<label>Name</label><input id="name" placeholder="e.g. Aarav Sharma" required>
<label>Score (0–15)</label><input id="score" placeholder="e.g. 13  or  13/15" required min="0" max="15">
<button>Generate Certificate</button></form>
<img id="out" alt="Certificate preview">
<p style="margin-top:18px">API usage:</p>
<div class="api">GET /certificate?name=Aarav&amp;score=13<br>GET /certificate/Aarav/13<br>POST /certificate  {"name":"Aarav","score":13}</div>
</div><script>
document.getElementById('f').onsubmit=e=>{e.preventDefault();
 const n=encodeURIComponent(document.getElementById('name').value);
 const s=encodeURIComponent(document.getElementById('score').value);
 const img=document.getElementById('out'); img.src='/certificate?name='+n+'&score='+s+'&format=jpg'; img.style.display='block';};
</script></body></html>"""
    return Response(html, mimetype="text/html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "halloween-certificate-api"})


@app.route("/certificate", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/certificate", methods=["GET", "POST", "OPTIONS"])
def certificate():
    if request.method == "OPTIONS":
        return Response(status=204)
    name, score, total, date_str, download, as_json, fmt = parse_inputs()
    return certificate_response(name, score, total, date_str, download, as_json, fmt)


@app.route("/certificate/<path:name>/<path:score>", methods=["GET"])
@app.route("/api/certificate/<path:name>/<path:score>", methods=["GET"])
def certificate_path(name, score):
    name = unquote(name)
    score = unquote(score)
    total = request.args.get("total")
    date_str = request.args.get("date")
    download = request.args.get("download", "").lower() in ("1", "true", "yes")
    fmt = request.args.get("format", "png").lower()
    as_json = fmt == "json"
    return certificate_response(name, score, total, date_str, download, as_json, fmt)


# Vercel serverless entrypoint
app_obj = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

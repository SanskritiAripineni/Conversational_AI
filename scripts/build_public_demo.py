"""Build the key-free public demo from the shared UI and supplied sample menu."""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=ROOT / "public-demo")
args = parser.parse_args()
output = args.output.resolve()
(output / "static").mkdir(parents=True, exist_ok=True)
html = (ROOT / "templates/index.html").read_text()
html = re.sub(r"\{\{ url_for\('static', filename='([^']+)'\) \}\}", r"./static/\1", html)
html = html.replace('href="/"', 'href="./"')
html = html.replace('  <script src="./static/app.js" defer></script>',
    '  <script src="./static/menu.js" defer></script>\n'
    '  <script src="./static/demo-engine.js" defer></script>\n'
    '  <script src="./static/app.js" defer></script>')
html = html.replace('A conversational ordering prototype.</span>',
    'Built by Sanskriti Aripineni at the <a href="https://llmsoftware.com" target="_blank" rel="noopener noreferrer">LLMSoftware.com</a> hackathon.</span>')
html = html.replace('<p class="hero-note">Three cuisines. One cart. Zero back-and-forth.</p>',
    '<p class="hero-note">LLMSoftware.com hackathon · AI for real restaurant workflows.</p>')
html = html.replace('<meta name="description" content="One conversation. Every craving. A multi-restaurant conversational ordering demo.">',
    '<meta name="description" content="Try 334 Food Now: many menus, one conversation. A restaurant ordering prototype built at the LLMSoftware.com hackathon.">\n'
    '<meta name="robots" content="index,follow">')
(output / "index.html").write_text(html)
for name in ("app.js", "style.css", "favicon.svg", "demo-engine.js"):
    shutil.copy2(ROOT / "static" / name, output / "static" / name)
sample = json.loads((ROOT / "menus.sample.json").read_text())
menus = {restaurant: {item["name"]: item for item in dishes} for restaurant, dishes in sample.items()}
(output / "static/menu.js").write_text("'use strict';\nwindow.FoodNowMenu = " + json.dumps(menus, indent=2) + ";\n")
print(f"Built public demo at {output}")

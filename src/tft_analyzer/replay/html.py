from __future__ import annotations

import html
import json
from pathlib import Path


def build_replay_html(match_dir: Path) -> Path:
    match_dir = Path(match_dir)
    index_path = match_dir / "evidence" / "evidence_index.jsonl"
    if not index_path.exists():
        raise FileNotFoundError(f"Evidence index not found: {index_path}")

    records = []
    with index_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    frames = []
    for rec in records:
        ev = rec["evidence"]
        frames.append({
            "sequence": rec["sequence"],
            "timestamp_s": ev["timestamp_s"],
            "reason": rec["reason"],
            "score": rec.get("scene_change_score"),
            "uri": ev["uri"].replace("\\", "/"),
        })

    payload = json.dumps(frames, ensure_ascii=False).replace("</", "<\\/")
    match_name = html.escape(match_dir.name)

    document = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TFT Analyzer Replay - {match_name}</title>
<style>
body {{ margin: 0; font-family: system-ui, sans-serif; background: #111; color: #eee; }}
main {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
.viewer {{ display: grid; gap: 12px; }}
img {{ width: 100%; max-height: 78vh; object-fit: contain; background: #000; }}
.controls {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
input[type=range] {{ flex: 1 1 500px; }}
.meta {{ font-family: ui-monospace, monospace; }}
button {{ padding: 7px 12px; }}
</style>
</head>
<body>
<main>
<h1>TFT Analyzer Replay</h1>
<div class="viewer">
  <img id="frame" alt="recorded frame">
  <div class="controls">
    <button id="prev">&larr; Previous</button>
    <button id="next">Next &rarr;</button>
    <input id="slider" type="range" min="0" max="{max(len(frames)-1, 0)}" value="0">
  </div>
  <div class="meta" id="meta"></div>
</div>
<script>
const frames = {payload};
let index = 0;
function render() {{
  if (!frames.length) {{
    document.getElementById("meta").textContent = "No frames recorded.";
    return;
  }}
  index = Math.max(0, Math.min(index, frames.length - 1));
  const f = frames[index];
  document.getElementById("frame").src = f.uri;
  document.getElementById("slider").value = index;
  document.getElementById("meta").textContent =
    `#${{f.sequence}} | ${{f.timestamp_s.toFixed(3)}} s | ${{f.reason}} | change=${{f.score ?? "n/a"}}`;
}}
document.getElementById("prev").onclick = () => {{ index--; render(); }};
document.getElementById("next").onclick = () => {{ index++; render(); }};
document.getElementById("slider").oninput = e => {{ index = Number(e.target.value); render(); }};
document.addEventListener("keydown", e => {{
  if (e.key === "ArrowLeft") {{ index--; render(); }}
  if (e.key === "ArrowRight") {{ index++; render(); }}
}});
render();
</script>
</main>
</body>
</html>'''
    out = match_dir / "replay.html"
    out.write_text(document, encoding="utf-8")
    return out

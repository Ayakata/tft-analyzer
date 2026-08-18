from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

import yaml


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class BoardGeometryEditorSettings:
    producer_version: str = "board-geometry-editor-0.1.0"
    host: str = "127.0.0.1"
    port: int = 8766
    open_browser: bool = True


def _pair(value, *, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain [x, y]")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{name} values must be numbers")
        number = float(item)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{name} values must be in [0, 1]")
        result.append(number)
    return result


def _integer(value, *, name: str, minimum: int = 1, maximum: int = 500) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = int(round(float(value)))
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return result


def _integer_rows(value, *, name: str, rows: int) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != rows:
        raise ValueError(f"{name} must contain {rows} row values")
    return [
        _integer(item, name=f"{name}[{index}]")
        for index, item in enumerate(value)
    ]


def _geometry_from_config(config_path: Path) -> dict[str, object]:
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError(f"Config must contain a YAML mapping: {config_path}")

    board = (
        config.get("perception", {})
        .get("board_bench", {})
    )
    rows = int(board.get("board_rows", 4))
    cols = int(board.get("board_cols", 7))
    bench_slots = int(board.get("bench_slots", 9))

    def points(name: str, default):
        values = board.get(name, default)
        return [
            _pair(point, name=f"{name}[{index}]")
            for index, point in enumerate(values)
        ]

    def row_values(name: str, default):
        return _integer_rows(
            board.get(name, default),
            name=name,
            rows=rows,
        )

    geometry = {
        "board_rows": rows,
        "board_cols": cols,
        "bench_slots": bench_slots,
        "board_row_left": points(
            "board_row_left",
            [[.293, .414], [.319, .478], [.278, .549], [.304, .625]],
        ),
        "board_row_right": points(
            "board_row_right",
            [[.651, .414], [.688, .478], [.663, .549], [.701, .625]],
        ),
        "board_half_width_px_at_1920_by_row": row_values(
            "board_half_width_px_at_1920_by_row", [50, 56, 62, 68]
        ),
        "board_up_px_at_1080_by_row": row_values(
            "board_up_px_at_1080_by_row", [68, 72, 78, 84]
        ),
        "board_down_px_at_1080_by_row": row_values(
            "board_down_px_at_1080_by_row", [26, 28, 30, 32]
        ),
        "board_hex_half_width_px_at_1920_by_row": row_values(
            "board_hex_half_width_px_at_1920_by_row", [52, 55, 58, 61]
        ),
        "board_hex_half_height_px_at_1080_by_row": row_values(
            "board_hex_half_height_px_at_1080_by_row", [38, 41, 45, 48]
        ),
        "bench_left": _pair(board.get("bench_left", [.230, .745]), name="bench_left"),
        "bench_right": _pair(board.get("bench_right", [.715, .745]), name="bench_right"),
        "bench_half_width_px_at_1920": _integer(
            board.get("bench_half_width_px_at_1920", 60),
            name="bench_half_width_px_at_1920",
        ),
        "bench_up_px_at_1080": _integer(
            board.get("bench_up_px_at_1080", 142),
            name="bench_up_px_at_1080",
        ),
        "bench_down_px_at_1080": _integer(
            board.get("bench_down_px_at_1080", 12),
            name="bench_down_px_at_1080",
        ),
        "bench_footprint_half_width_px_at_1920": _integer(
            board.get("bench_footprint_half_width_px_at_1920", 36),
            name="bench_footprint_half_width_px_at_1920",
        ),
        "bench_footprint_up_px_at_1080": _integer(
            board.get("bench_footprint_up_px_at_1080", 64),
            name="bench_footprint_up_px_at_1080",
        ),
        "bench_footprint_down_px_at_1080": _integer(
            board.get("bench_footprint_down_px_at_1080", 16),
            name="bench_footprint_down_px_at_1080",
        ),
    }
    return geometry


def _validate_geometry(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("geometry must be an object")
    rows = _integer(value.get("board_rows"), name="board_rows", maximum=12)
    cols = _integer(value.get("board_cols"), name="board_cols", minimum=2, maximum=12)
    bench_slots = _integer(
        value.get("bench_slots"), name="bench_slots", minimum=2, maximum=16
    )

    def points(name: str) -> list[list[float]]:
        raw = value.get(name)
        if not isinstance(raw, (list, tuple)) or len(raw) != rows:
            raise ValueError(f"{name} must contain {rows} points")
        return [
            _pair(point, name=f"{name}[{index}]")
            for index, point in enumerate(raw)
        ]

    result = {
        "board_rows": rows,
        "board_cols": cols,
        "bench_slots": bench_slots,
        "board_row_left": points("board_row_left"),
        "board_row_right": points("board_row_right"),
        "board_half_width_px_at_1920_by_row": _integer_rows(
            value.get("board_half_width_px_at_1920_by_row"),
            name="board_half_width_px_at_1920_by_row",
            rows=rows,
        ),
        "board_up_px_at_1080_by_row": _integer_rows(
            value.get("board_up_px_at_1080_by_row"),
            name="board_up_px_at_1080_by_row",
            rows=rows,
        ),
        "board_down_px_at_1080_by_row": _integer_rows(
            value.get("board_down_px_at_1080_by_row"),
            name="board_down_px_at_1080_by_row",
            rows=rows,
        ),
        "board_hex_half_width_px_at_1920_by_row": _integer_rows(
            value.get("board_hex_half_width_px_at_1920_by_row"),
            name="board_hex_half_width_px_at_1920_by_row",
            rows=rows,
        ),
        "board_hex_half_height_px_at_1080_by_row": _integer_rows(
            value.get("board_hex_half_height_px_at_1080_by_row"),
            name="board_hex_half_height_px_at_1080_by_row",
            rows=rows,
        ),
        "bench_left": _pair(value.get("bench_left"), name="bench_left"),
        "bench_right": _pair(value.get("bench_right"), name="bench_right"),
    }
    for name in (
        "bench_half_width_px_at_1920",
        "bench_up_px_at_1080",
        "bench_down_px_at_1080",
        "bench_footprint_half_width_px_at_1920",
        "bench_footprint_up_px_at_1080",
        "bench_footprint_down_px_at_1080",
    ):
        result[name] = _integer(value.get(name), name=name)
    return result


def load_board_geometry_draft(path: Path | str) -> dict[str, object]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_geometry(payload.get("geometry"))


class BoardGeometryDraftStore:
    def __init__(
        self,
        match_dir: Path | str,
        *,
        config_path: Path | str,
        draft_path: Path | str | None = None,
        initial_frame: str | None = None,
        producer_version: str = "board-geometry-editor-0.1.0",
    ) -> None:
        self.match_dir = Path(match_dir).resolve()
        self.frames_dir = (self.match_dir / "evidence" / "frames").resolve()
        self.config_path = Path(config_path).resolve()
        self.producer_version = producer_version
        if not self.match_dir.is_dir():
            raise FileNotFoundError(self.match_dir)
        if not self.frames_dir.is_dir():
            raise FileNotFoundError(self.frames_dir)
        if not self.config_path.is_file():
            raise FileNotFoundError(self.config_path)

        self.draft_path = (
            Path(draft_path).resolve()
            if draft_path is not None
            else (
                self.match_dir
                / "calibration"
                / self.producer_version
                / "draft.json"
            ).resolve()
        )
        self._frames = {
            path.name: path.resolve()
            for path in sorted(self.frames_dir.iterdir())
            if path.is_file() and path.suffix.casefold() in _IMAGE_SUFFIXES
        }
        if not self._frames:
            raise FileNotFoundError(f"No evidence frames in {self.frames_dir}")

        candidate = Path(initial_frame).name if initial_frame else None
        if candidate and candidate not in self._frames:
            raise FileNotFoundError(
                f"Initial frame is not part of this match: {initial_frame}"
            )
        self.initial_frame = candidate or next(iter(self._frames))
        self.config_geometry = _geometry_from_config(self.config_path)
        self.geometry = json.loads(json.dumps(self.config_geometry))
        self.draft_loaded = False
        self._lock = threading.Lock()
        self._load_existing_draft()

    @property
    def frame_names(self) -> list[str]:
        return list(self._frames)

    def frame_path(self, name: str) -> Path:
        try:
            return self._frames[name]
        except KeyError as exc:
            raise FileNotFoundError(f"Unknown match frame: {name}") from exc

    def _load_existing_draft(self) -> None:
        if not self.draft_path.is_file():
            return
        self.geometry = load_board_geometry_draft(self.draft_path)
        self.draft_loaded = True

    def state(self) -> dict[str, object]:
        return {
            "producer_version": self.producer_version,
            "match_dir": str(self.match_dir),
            "config_path": str(self.config_path),
            "draft_path": str(self.draft_path),
            "draft_loaded": self.draft_loaded,
            "frames": self.frame_names,
            "initial_frame": self.initial_frame,
            "geometry": self.geometry,
            "config_geometry": self.config_geometry,
        }

    def save(self, geometry: object, *, frame_name: str | None = None) -> dict[str, object]:
        validated = _validate_geometry(geometry)
        if frame_name is not None:
            self.frame_path(frame_name)
        payload = {
            "schema_version": 1,
            "producer_version": self.producer_version,
            "match_dir": str(self.match_dir),
            "source_config_path": str(self.config_path),
            "reference_width": 1920,
            "reference_height": 1080,
            "preview_frame": frame_name or self.initial_frame,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "geometry": validated,
        }
        with self._lock:
            self.draft_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.draft_path.with_suffix(self.draft_path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(self.draft_path)
            self.geometry = validated
            self.draft_loaded = True
        return {
            "saved": True,
            "draft_path": str(self.draft_path),
            "saved_at_utc": payload["saved_at_utc"],
            "geometry": validated,
        }


_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TFT — редактор зон поля</title>
<style>
:root{color-scheme:dark;--bg:#0c1118;--panel:#141c27;--line:#2c3a4d;--text:#e7edf6;--muted:#9aabc0;--cyan:#33e4c2;--amber:#ffb429;--blue:#61a9ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,Segoe UI,sans-serif}
header{display:flex;gap:12px;align-items:center;padding:10px 14px;background:#111925;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
h1{font-size:16px;margin:0 12px 0 0;white-space:nowrap}select,button,input{background:#0e1621;color:var(--text);border:1px solid #3a4a60;border-radius:7px;padding:7px}
button{cursor:pointer}button.primary{background:#136c5d;border-color:#24a68f}button:hover{border-color:#7e94af}
#status{margin-left:auto;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
main{display:grid;grid-template-columns:minmax(600px,1fr) 350px;min-height:calc(100vh - 54px)}
.stage{padding:12px;min-width:0}.canvas-wrap{background:#05080c;border:1px solid var(--line);border-radius:9px;overflow:auto;max-height:calc(100vh - 80px)}
canvas#board{display:block;width:100%;height:auto;touch-action:none;cursor:crosshair}.side{border-left:1px solid var(--line);background:var(--panel);padding:12px;overflow:auto;max-height:calc(100vh - 54px)}
.card{border:1px solid var(--line);border-radius:9px;padding:11px;margin-bottom:10px;background:#101722}.card h2{font-size:14px;margin:0 0 8px}
.hint{color:var(--muted);font-size:12px}.row{display:grid;grid-template-columns:1fr 92px;gap:7px;align-items:center;margin:6px 0}.row input{width:100%}
.toggles{display:flex;gap:12px;flex-wrap:wrap}.toggles label{display:flex;gap:5px;align-items:center}.selected{color:var(--cyan);font-weight:700}
#crop{width:100%;height:180px;background:#080c12;border:1px solid var(--line);image-rendering:auto}
.legend{display:grid;grid-template-columns:14px 1fr;gap:5px 8px;align-items:center}.swatch{height:3px}.cyan{background:var(--cyan)}.amber{background:var(--amber)}.blue{background:var(--blue)}
@media(max-width:1000px){main{grid-template-columns:1fr}.side{border-left:0;border-top:1px solid var(--line);max-height:none}.canvas-wrap{max-height:none}}
</style>
</head>
<body>
<header>
  <h1>TFT Geometry Editor</h1>
  <select id="frame"></select>
  <button id="save" class="primary">Сохранить черновик</button>
  <button id="reset">Сбросить к config</button>
  <span id="status">Загрузка…</span>
</header>
<main>
  <section class="stage"><div class="canvas-wrap"><canvas id="board"></canvas></div></section>
  <aside class="side">
    <div class="card">
      <h2>Как править</h2>
      <div class="hint">Перетаскивай точки L/R, чтобы менять линию центров. Перетаскивание рамки сдвигает всю строку. У выбранной рамки боковые/верхний/нижний маркеры меняют размер для всей строки.</div>
    </div>
    <div class="card">
      <h2>Слои</h2>
      <div class="toggles">
        <label><input type="checkbox" id="showContext" checked> context</label>
        <label><input type="checkbox" id="showFootprint" checked> footprint</label>
        <label><input type="checkbox" id="showLabels" checked> подписи</label>
      </div>
      <div class="row"><label for="editLayer">Редактировать</label><select id="editLayer"><option value="context">Context crop</option><option value="footprint">Footprint</option></select></div>
    </div>
    <div class="card">
      <h2>Выбрано: <span id="selected" class="selected">—</span></h2>
      <div id="controls"></div>
    </div>
    <div class="card"><h2>Предпросмотр context-crop</h2><canvas id="crop"></canvas></div>
    <div class="card legend">
      <span class="swatch cyan"></span><span>context — crop для identity</span>
      <span class="swatch amber"></span><span>footprint — зона occupancy</span>
      <span class="swatch blue"></span><span>L/R — якоря перспективной линии</span>
    </div>
    <div class="card hint">Черновик сохраняется отдельно от <code>configs/default.yaml</code>. После проверки мы применим только выбранные значения.</div>
  </aside>
</main>
<script>
const $=id=>document.getElementById(id);
const canvas=$("board"),ctx=canvas.getContext("2d"),crop=$("crop"),cropCtx=crop.getContext("2d");
const state={server:null,g:null,original:null,img:new Image(),selected:{kind:"board",row:0,index:0},drag:null,boxes:[],handles:[]};
const clone=v=>JSON.parse(JSON.stringify(v));
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function setStatus(text,error=false){$("status").textContent=text;$("status").style.color=error?"#ff7f8b":"var(--muted)"}
function centers(){
  const g=state.g,w=canvas.width,h=canvas.height,out=[];
  for(let r=0;r<g.board_rows;r++)for(let c=0;c<g.board_cols;c++){
    const t=c/(g.board_cols-1),l=g.board_row_left[r],q=g.board_row_right[r];
    out.push({kind:"board",row:r,index:c,x:(l[0]+(q[0]-l[0])*t)*w,y:(l[1]+(q[1]-l[1])*t)*h});
  }
  for(let i=0;i<g.bench_slots;i++){
    const t=i/(g.bench_slots-1),l=g.bench_left,q=g.bench_right;
    out.push({kind:"bench",row:0,index:i,x:(l[0]+(q[0]-l[0])*t)*w,y:(l[1]+(q[1]-l[1])*t)*h});
  }
  return out;
}
function geometryFor(cell,layer){
  const g=state.g,sx=canvas.width/1920,sy=canvas.height/1080;
  if(cell.kind==="board"){
    if(layer==="context")return {hw:g.board_half_width_px_at_1920_by_row[cell.row]*sx,up:g.board_up_px_at_1080_by_row[cell.row]*sy,down:g.board_down_px_at_1080_by_row[cell.row]*sy};
    return {hw:g.board_hex_half_width_px_at_1920_by_row[cell.row]*sx,up:g.board_hex_half_height_px_at_1080_by_row[cell.row]*sy,down:g.board_hex_half_height_px_at_1080_by_row[cell.row]*sy};
  }
  if(layer==="context")return {hw:g.bench_half_width_px_at_1920*sx,up:g.bench_up_px_at_1080*sy,down:g.bench_down_px_at_1080*sy};
  return {hw:g.bench_footprint_half_width_px_at_1920*sx,up:g.bench_footprint_up_px_at_1080*sy,down:g.bench_footprint_down_px_at_1080*sy};
}
function rectFor(cell,layer){const z=geometryFor(cell,layer);return {x:cell.x-z.hw,y:cell.y-z.up,w:z.hw*2,h:z.up+z.down,cx:cell.x,cy:cell.y,...z}}
function isSelected(cell){const s=state.selected;return s.kind===cell.kind&&s.row===cell.row&&s.index===cell.index}
function drawHex(cell,z,color,width=2){const sh=z.hw*.5;ctx.beginPath();ctx.moveTo(cell.x-sh,cell.y-z.up);ctx.lineTo(cell.x+sh,cell.y-z.up);ctx.lineTo(cell.x+z.hw,cell.y);ctx.lineTo(cell.x+sh,cell.y+z.down);ctx.lineTo(cell.x-sh,cell.y+z.down);ctx.lineTo(cell.x-z.hw,cell.y);ctx.closePath();ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke()}
function drawHandle(x,y,type){ctx.fillStyle="#61a9ff";ctx.strokeStyle="#06101d";ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();ctx.stroke();state.handles.push({x,y,type})}
function draw(){
  if(!state.img.complete||!state.g)return;
  ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(state.img,0,0,canvas.width,canvas.height);state.boxes=[];state.handles=[];
  const cells=centers();
  for(const cell of cells){
    const selected=isSelected(cell),cr=rectFor(cell,"context"),fr=rectFor(cell,"footprint");state.boxes.push({cell,rect:cr});
    if($("showContext").checked){ctx.strokeStyle=selected?"#dffff8":"#33e4c2";ctx.lineWidth=selected?3:1.5;ctx.strokeRect(cr.x,cr.y,cr.w,cr.h)}
    if($("showFootprint").checked){if(cell.kind==="board")drawHex(cell,fr,"#ffb429",selected?3:1.5);else{ctx.strokeStyle="#ffb429";ctx.lineWidth=selected?3:1.5;ctx.strokeRect(fr.x,fr.y,fr.w,fr.h)}}
    if($("showLabels").checked){ctx.fillStyle="#e9fbff";ctx.font="12px Segoe UI";ctx.fillText(cell.kind==="board"?`r${cell.row}c${cell.index}`:`b${cell.index}`,cr.x+3,cr.y+13)}
  }
  const g=state.g,w=canvas.width,h=canvas.height;
  for(let r=0;r<g.board_rows;r++){drawHandle(g.board_row_left[r][0]*w,g.board_row_left[r][1]*h,{mode:"anchor",kind:"board",row:r,side:"left"});drawHandle(g.board_row_right[r][0]*w,g.board_row_right[r][1]*h,{mode:"anchor",kind:"board",row:r,side:"right"})}
  drawHandle(g.bench_left[0]*w,g.bench_left[1]*h,{mode:"anchor",kind:"bench",side:"left"});drawHandle(g.bench_right[0]*w,g.bench_right[1]*h,{mode:"anchor",kind:"bench",side:"right"});
  const selected=cells.find(isSelected);if(selected){const rr=rectFor(selected,$("editLayer").value);drawHandle(rr.x,rr.cy,{mode:"resize",edge:"left"});drawHandle(rr.x+rr.w,rr.cy,{mode:"resize",edge:"right"});drawHandle(rr.cx,rr.y,{mode:"resize",edge:"top"});drawHandle(rr.cx,rr.y+rr.h,{mode:"resize",edge:"bottom"});drawCrop(selected)}
}
function drawCrop(cell){const r=rectFor(cell,"context"),x=clamp(r.x,0,canvas.width),y=clamp(r.y,0,canvas.height),right=clamp(r.x+r.w,0,canvas.width),bottom=clamp(r.y+r.h,0,canvas.height);crop.width=330;crop.height=180;cropCtx.fillStyle="#080c12";cropCtx.fillRect(0,0,crop.width,crop.height);const sw=right-x,sh=bottom-y;if(sw<=0||sh<=0)return;const scale=Math.min(crop.width/sw,crop.height/sh);const dw=sw*scale,dh=sh*scale;cropCtx.drawImage(state.img,x,y,sw,sh,(crop.width-dw)/2,(crop.height-dh)/2,dw,dh)}
function pointer(ev){const r=canvas.getBoundingClientRect();return{x:(ev.clientX-r.left)*canvas.width/r.width,y:(ev.clientY-r.top)*canvas.height/r.height}}
function nearestHandle(p){return state.handles.find(h=>Math.hypot(h.x-p.x,h.y-p.y)<=12)}
function nearestSelectedEdge(p){
  const selected=centers().find(isSelected);if(!selected)return null;
  const r=rectFor(selected,$("editLayer").value),tolerance=12;
  const candidates=[];
  if(p.y>=r.y-tolerance&&p.y<=r.y+r.h+tolerance){candidates.push({distance:Math.abs(p.x-r.x),edge:"left"},{distance:Math.abs(p.x-(r.x+r.w)),edge:"right"})}
  if(p.x>=r.x-tolerance&&p.x<=r.x+r.w+tolerance){candidates.push({distance:Math.abs(p.y-r.y),edge:"top"},{distance:Math.abs(p.y-(r.y+r.h)),edge:"bottom"})}
  candidates.sort((a,b)=>a.distance-b.distance);const hit=candidates[0];return hit&&hit.distance<=tolerance?{type:{mode:"resize",edge:hit.edge}}:null
}
function cellAt(p){for(let i=state.boxes.length-1;i>=0;i--){const b=state.boxes[i],r=b.rect;if(p.x>=r.x&&p.x<=r.x+r.w&&p.y>=r.y&&p.y<=r.y+r.h)return b.cell}return null}
function groupAnchors(cell){return cell.kind==="board"?[state.g.board_row_left[cell.row],state.g.board_row_right[cell.row]]:[state.g.bench_left,state.g.bench_right]}
canvas.addEventListener("pointerdown",ev=>{const p=pointer(ev),h=nearestHandle(p)||nearestSelectedEdge(p);if(h){state.drag={...h.type,start:p,geometry:clone(state.g)};canvas.setPointerCapture(ev.pointerId);return}const cell=cellAt(p);if(cell){state.selected={kind:cell.kind,row:cell.row,index:cell.index};state.drag={mode:"move",cell,start:p,geometry:clone(state.g)};renderControls();draw();canvas.setPointerCapture(ev.pointerId)}});
canvas.addEventListener("pointermove",ev=>{if(!state.drag)return;const p=pointer(ev),d=state.drag,g0=state.drag.geometry,w=canvas.width,h=canvas.height;if(d.mode==="anchor"){const point=d.kind==="board"?(d.side==="left"?state.g.board_row_left[d.row]:state.g.board_row_right[d.row]):(d.side==="left"?state.g.bench_left:state.g.bench_right);point[0]=clamp(p.x/w,0,1);point[1]=clamp(p.y/h,0,1)}else if(d.mode==="move"){const dx=(p.x-d.start.x)/w,dy=(p.y-d.start.y)/h;if(d.cell.kind==="board"){for(const side of ["board_row_left","board_row_right"]){state.g[side][d.cell.row][0]=clamp(g0[side][d.cell.row][0]+dx,0,1);state.g[side][d.cell.row][1]=clamp(g0[side][d.cell.row][1]+dy,0,1)}}else{for(const side of ["bench_left","bench_right"]){state.g[side][0]=clamp(g0[side][0]+dx,0,1);state.g[side][1]=clamp(g0[side][1]+dy,0,1)}}}else if(d.mode==="resize"){resizeSelected(p,d.edge)}renderControls();draw()});
canvas.addEventListener("pointerup",()=>state.drag=null);canvas.addEventListener("pointercancel",()=>state.drag=null);
function resizeSelected(p,edge){const s=state.selected,c=centers().find(isSelected);if(!c)return;const layer=$("editLayer").value,refX=1920/canvas.width,refY=1080/canvas.height,v=edge==="left"||edge==="right"?Math.max(8,Math.round(Math.abs(p.x-c.x)*refX)):edge==="top"?Math.max(8,Math.round((c.y-p.y)*refY)):Math.max(6,Math.round((p.y-c.y)*refY));const g=state.g;if(s.kind==="board"){if(layer==="context"){if(edge==="left"||edge==="right")g.board_half_width_px_at_1920_by_row[s.row]=v;else if(edge==="top")g.board_up_px_at_1080_by_row[s.row]=v;else g.board_down_px_at_1080_by_row[s.row]=v}else{if(edge==="left"||edge==="right")g.board_hex_half_width_px_at_1920_by_row[s.row]=v;else g.board_hex_half_height_px_at_1080_by_row[s.row]=v}}else{const prefix=layer==="context"?"bench":"bench_footprint";if(edge==="left"||edge==="right")g[`${prefix}_half_width_px_at_1920`]=v;else if(edge==="top")g[`${prefix}_up_px_at_1080`]=v;else g[`${prefix}_down_px_at_1080`]=v}}
function inputRow(label,value,onchange,step="1"){const wrap=document.createElement("div");wrap.className="row";const lab=document.createElement("label");lab.textContent=label;const input=document.createElement("input");input.type="number";input.step=step;input.value=value;input.addEventListener("change",()=>{onchange(Number(input.value));draw()});wrap.append(lab,input);return wrap}
function renderControls(){const box=$("controls");box.innerHTML="";const s=state.selected,g=state.g;if(!g)return;$("selected").textContent=s.kind==="board"?`поле, строка ${s.row}, ячейка ${s.index}`:`скамейка, слот ${s.index}`;const add=(...args)=>box.appendChild(inputRow(...args));if(s.kind==="board"){const r=s.row;add("L x",g.board_row_left[r][0],v=>g.board_row_left[r][0]=clamp(v,0,1),"0.001");add("L y",g.board_row_left[r][1],v=>g.board_row_left[r][1]=clamp(v,0,1),"0.001");add("R x",g.board_row_right[r][0],v=>g.board_row_right[r][0]=clamp(v,0,1),"0.001");add("R y",g.board_row_right[r][1],v=>g.board_row_right[r][1]=clamp(v,0,1),"0.001");add("Context half-width",g.board_half_width_px_at_1920_by_row[r],v=>g.board_half_width_px_at_1920_by_row[r]=v);add("Context up",g.board_up_px_at_1080_by_row[r],v=>g.board_up_px_at_1080_by_row[r]=v);add("Context down",g.board_down_px_at_1080_by_row[r],v=>g.board_down_px_at_1080_by_row[r]=v);add("Hex half-width",g.board_hex_half_width_px_at_1920_by_row[r],v=>g.board_hex_half_width_px_at_1920_by_row[r]=v);add("Hex half-height",g.board_hex_half_height_px_at_1080_by_row[r],v=>g.board_hex_half_height_px_at_1080_by_row[r]=v)}else{add("L x",g.bench_left[0],v=>g.bench_left[0]=clamp(v,0,1),"0.001");add("L y",g.bench_left[1],v=>g.bench_left[1]=clamp(v,0,1),"0.001");add("R x",g.bench_right[0],v=>g.bench_right[0]=clamp(v,0,1),"0.001");add("R y",g.bench_right[1],v=>g.bench_right[1]=clamp(v,0,1),"0.001");for(const [label,key] of [["Context half-width","bench_half_width_px_at_1920"],["Context up","bench_up_px_at_1080"],["Context down","bench_down_px_at_1080"],["Footprint half-width","bench_footprint_half_width_px_at_1920"],["Footprint up","bench_footprint_up_px_at_1080"],["Footprint down","bench_footprint_down_px_at_1080"]])add(label,g[key],v=>g[key]=v)}}
async function loadFrame(){setStatus("Загрузка кадра…");state.img.onload=()=>{canvas.width=state.img.naturalWidth;canvas.height=state.img.naturalHeight;renderControls();draw();setStatus(state.server.draft_loaded?"Загружен сохранённый черновик":"Геометрия из config")};state.img.src=`/frame?name=${encodeURIComponent($("frame").value)}&t=${Date.now()}`}
async function init(){const res=await fetch("/api/state"),data=await res.json();state.server=data;state.g=clone(data.geometry);state.original=clone(data.config_geometry);for(const name of data.frames){const o=document.createElement("option");o.value=name;o.textContent=name;$("frame").appendChild(o)}$("frame").value=data.initial_frame;loadFrame()}
$("frame").addEventListener("change",loadFrame);for(const id of ["showContext","showFootprint","showLabels","editLayer"])$(id).addEventListener("change",draw);
$("reset").addEventListener("click",()=>{state.g=clone(state.original);renderControls();draw();setStatus("Сброшено к значениям config; черновик на диске не изменён")});
$("save").addEventListener("click",async()=>{try{setStatus("Сохранение…");const res=await fetch("/api/draft",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({geometry:state.g,frame_name:$("frame").value})});const data=await res.json();if(!res.ok)throw new Error(data.error||"Save failed");setStatus(`Сохранено: ${data.draft_path}`)}catch(err){setStatus(err.message,true)}});
init().catch(err=>setStatus(err.message,true));
</script>
</body>
</html>"""


def make_board_geometry_editor_handler(store: BoardGeometryDraftStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def _send(self, body: bytes, *, content_type: str, status=HTTPStatus.OK):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value: object, *, status=HTTPStatus.OK):
            self._send(
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
                status=status,
            )

        def do_GET(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send(
                        _HTML.encode("utf-8"),
                        content_type="text/html; charset=utf-8",
                    )
                    return
                if parsed.path == "/api/state":
                    self._json(store.state())
                    return
                if parsed.path == "/frame":
                    name = (parse_qs(parsed.query).get("name") or [""])[0]
                    path = store.frame_path(name)
                    self._send(
                        path.read_bytes(),
                        content_type=(
                            mimetypes.guess_type(path.name)[0]
                            or "application/octet-stream"
                        ),
                    )
                    return
                self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            except FileNotFoundError as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._json(
                    {"error": f"{type(exc).__name__}: {exc}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/api/draft":
                self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = store.save(
                    payload.get("geometry"),
                    frame_name=payload.get("frame_name"),
                )
                self._json(result)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._json(
                    {"error": f"{type(exc).__name__}: {exc}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

    return Handler


def create_board_geometry_editor_server(
    store: BoardGeometryDraftStore,
    *,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port),
        make_board_geometry_editor_handler(store),
    )


def run_board_geometry_editor(
    match_dir: Path | str,
    settings: BoardGeometryEditorSettings,
    *,
    config_path: Path | str,
    draft_path: Path | str | None = None,
    initial_frame: str | None = None,
) -> None:
    store = BoardGeometryDraftStore(
        match_dir,
        config_path=config_path,
        draft_path=draft_path,
        initial_frame=initial_frame,
        producer_version=settings.producer_version,
    )
    server = create_board_geometry_editor_server(
        store,
        host=settings.host,
        port=settings.port,
    )
    actual_host, actual_port = server.server_address[:2]
    url_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
    url = f"http://{url_host}:{actual_port}/"
    print(f"[INFO] Editor:      {settings.producer_version}")
    print(f"[INFO] Match:       {store.match_dir}")
    print(f"[INFO] Frames:      {len(store.frame_names)}")
    print(f"[INFO] Initial:     {store.initial_frame}")
    print(f"[INFO] Config:      {store.config_path}")
    print(f"[INFO] Draft:       {store.draft_path}")
    print(f"[OK] Open:         {url}")
    print("[INFO] Stop:        Ctrl+C")
    if settings.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

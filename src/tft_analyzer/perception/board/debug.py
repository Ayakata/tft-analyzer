from __future__ import annotations
import json
from pathlib import Path
from PIL import Image, ImageDraw
from .recognizer import BoardBenchRecognizer

COLORS={'occupied':(70,230,110),'empty':(90,180,255),'uncertain':(255,190,60)}
def _dim(c,f=.55): return tuple(round(v*f) for v in c)
def _feat(f): return {k:float(getattr(f,k)) for k in f.__dataclass_fields__}

def build_board_debug(image_path:Path|str, output_dir:Path|str, recognizer:BoardBenchRecognizer)->dict[str,object]:
    image_path=Path(image_path); output_dir=Path(output_dir)
    board_dir=output_dir/'board_cells'; bench_dir=output_dir/'bench_slots'; bctx=output_dir/'board_context'; sctx=output_dir/'bench_context'
    for d in (board_dir,bench_dir,bctx,sctx): d.mkdir(parents=True,exist_ok=True)
    with Image.open(image_path) as src: image=src.convert('RGB')
    result=recognizer.recognize(image,match_id='debug',timestamp_s=0.0,evidence_id=f'debug-{image_path.stem}')
    w,h=image.size
    image.crop(recognizer.registry.resolve('board_region',w,h).box).save(output_dir/'board_region.png')
    image.crop(recognizer.registry.resolve('bench_region',w,h).box).save(output_dir/'bench_region.png')
    overlay=image.copy(); draw=ImageDraw.Draw(overlay)
    for c in result.board_cells:
        color=COLORS[c.status]
        draw.rectangle(c.context_box,outline=_dim(color),width=1)
        poly=recognizer.board_hex_polygon(c.row,c.center,w,h)
        draw.line(poly+(poly[0],),fill=color,width=3)
        cx,cy=c.center; draw.ellipse((cx-3,cy-3,cx+3,cy+3),fill=color)
        draw.text((c.context_box[0]+2,c.context_box[1]+2),f'{c.row},{c.col} {c.score:.2f}',fill=color)
        image.crop(c.footprint_box).save(board_dir/f'r{c.row}_c{c.col}_{c.status}_{c.score:.3f}.png')
        image.crop(c.context_box).save(bctx/f'r{c.row}_c{c.col}_context.png')
    for c in result.bench_slots:
        color=COLORS[c.status]
        draw.rectangle(c.context_box,outline=_dim(color),width=1); draw.rectangle(c.footprint_box,outline=color,width=3)
        cx,cy=c.center; draw.ellipse((cx-3,cy-3,cx+3,cy+3),fill=color)
        draw.text((c.context_box[0]+2,c.context_box[1]+2),f'b{c.slot_index} {c.score:.2f}',fill=color)
        image.crop(c.footprint_box).save(bench_dir/f'slot_{c.slot_index}_{c.status}_{c.score:.3f}.png')
        image.crop(c.context_box).save(sctx/f'slot_{c.slot_index}_context.png')
    overlay_path=output_dir/'overlay.png'; overlay.save(overlay_path)
    payload={'schema_version':2,'source_image':str(image_path),'profile_id':recognizer.registry.profile.profile_id,'sampling_mode':'footprint',
      'geometry':{
        'board_rows':[{
          'row':row,
          'context_half_width_px_at_1920':recognizer.board_box_geometry_at_reference(row)[0],
          'context_up_px_at_1080':recognizer.board_box_geometry_at_reference(row)[1],
          'context_down_px_at_1080':recognizer.board_box_geometry_at_reference(row)[2],
          'hex_half_width_px_at_1920':recognizer.board_hex_geometry_at_reference(row)[0],
          'hex_half_height_px_at_1080':recognizer.board_hex_geometry_at_reference(row)[1],
          'row_left':recognizer.settings.board_row_left[row],
          'row_right':recognizer.settings.board_row_right[row],
        } for row in range(recognizer.settings.board_rows)],
        'bench':{
          'left':recognizer.settings.bench_left,
          'right':recognizer.settings.bench_right,
          'context_half_width_px_at_1920':recognizer.settings.bench_half_width_px_at_1920,
          'context_up_px_at_1080':recognizer.settings.bench_up_px_at_1080,
          'context_down_px_at_1080':recognizer.settings.bench_down_px_at_1080,
          'footprint_half_width_px_at_1920':recognizer.settings.bench_footprint_half_width_px_at_1920,
          'footprint_up_px_at_1080':recognizer.settings.bench_footprint_up_px_at_1080,
          'footprint_down_px_at_1080':recognizer.settings.bench_footprint_down_px_at_1080,
        },
      },
      'board_present':result.board_present,'board_presence_score':result.board_presence_score,'bench_present':result.bench_present,'bench_presence_score':result.bench_presence_score,
      'board_occupied_count':result.board_occupied_count,'board_uncertain_count':result.board_uncertain_count,'bench_occupied_count':result.bench_occupied_count,'bench_uncertain_count':result.bench_uncertain_count,
      'board_cells':[{'row':c.row,'col':c.col,'center':c.center,'footprint_box':c.footprint_box,'context_box':c.context_box,'hex_polygon':recognizer.board_hex_polygon(c.row,c.center,w,h),'hex_points':recognizer.board_hex_polygon(c.row,c.center,w,h),'status':c.status,'occupied':c.occupied,'score':c.score,'confidence':c.confidence,'features':_feat(c.features)} for c in result.board_cells],
      'bench_slots':[{'slot_index':c.slot_index,'center':c.center,'footprint_box':c.footprint_box,'context_box':c.context_box,'status':c.status,'occupied':c.occupied,'score':c.score,'confidence':c.confidence,'features':_feat(c.features)} for c in result.bench_slots],
      'observations':[o.model_dump(mode='json') for o in result.observations]}
    result_path=output_dir/'result.json'; result_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'overlay':str(overlay_path),'result_path':str(result_path),'board_dir':str(board_dir),'bench_dir':str(bench_dir),'board_context_dir':str(bctx),'bench_context_dir':str(sctx),'result':result}

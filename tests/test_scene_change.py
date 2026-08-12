from io import BytesIO
from PIL import Image
from tft_analyzer.capture.scene_change import SceneChangeDetector


def png(value):
    image = Image.new("RGB", (320, 180), (value, value, value))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_scene_change_detector():
    detector = SceneChangeDetector(width=32, height=18, threshold=0.05)
    changed, score = detector.changed(png(0))
    assert changed and score == 1.0
    changed, score = detector.changed(png(0))
    assert not changed and score == 0.0
    changed, score = detector.changed(png(255))
    assert changed and score > 0.9

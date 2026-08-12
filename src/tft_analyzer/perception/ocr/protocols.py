from typing import Protocol

from PIL import Image

from .models import OCRText


class OCREngine(Protocol):
    name: str

    def recognize_line(self, image: Image.Image) -> OCRText:
        ...

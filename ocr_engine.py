from PIL import Image

import winocr
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.globalization import Language


def available_languages():
    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


def _pick_language():
    preferred = ["zh-Hans-CN", "zh-Hans", "en-US", "en-GB", "en"]
    available = set(available_languages())
    for tag in preferred:
        if tag in available:
            return tag
    return None


def _join_cjk_spaces(text):
    result = []
    previous_cjk = False
    for char in text:
        is_cjk = "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf"
        if char == " " and previous_cjk:
            continue
        result.append(char)
        previous_cjk = is_cjk
    return "".join(result)


def ocr_image(image, lang=None):
    if lang is None:
        lang = _pick_language()
    if lang is None:
        raise RuntimeError("系统没有可用的 OCR 识别语言包")
    if image.mode != "RGB":
        image = image.convert("RGB")
    result = winocr.recognize_pil_sync(image, lang=lang)
    text = result.get("text") if isinstance(result, dict) else getattr(result, "text", None)
    if not text:
        lines = result.get("lines") if isinstance(result, dict) else getattr(result, "lines", None)
        text = "\n".join(line.get("text") if isinstance(line, dict) else getattr(line, "text", "")
                         for line in lines or [])
    return _join_cjk_spaces(text)


def ocr_file(path, lang=None):
    with Image.open(path) as image:
        image.load()
        return ocr_image(image, lang=lang)

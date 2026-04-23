from trafilatura import fetch_url, extract
from trafilatura.settings import Extractor
from mlx_audio.tts.generate import generate_audio
from langdetect import detect, lang_detect_exception

def rileva_lingua_veloce(testo: str) -> str:
    """
    Rileva se una stringa è in italiano, inglese o un'altra lingua.

    Args:
        testo: La stringa di testo da analizzare.

    Returns:
        "italiano", "inglese" o "altro".
    """
    try:
        lingua = detect(testo)
        if lingua == "it" or lingua == "en":
            return lingua
        else:
            return "other"
    except lang_detect_exception.LangDetectException:
        return "other"


options = Extractor(
    output_format="txt",
    with_metadata=False,
    comments=False,
    formatting=False,
    images=False,
    links=False,
    tables=False,
    precision=True,
)


def extract_readable_text_from_url(url):
    document = fetch_url(url)
    if document:
        text = extract(document, options=options)
        return text.strip()
    else:
        raise ValueError


def read_this(text):
    lang = rileva_lingua_veloce(text)

    if lang == "en":
        generate_audio(
            text=text,
            model_path="prince-canuma/Kokoro-82M",
            voice="af_heart",
            speed=1.1,
            lang_code="a",
            play=True,
            stream=True,
        )
    elif lang == "it":
        generate_audio(
            text=text,
            model_path="prince-canuma/Kokoro-82M",
            voice="im_nicola",
            speed=1.25,
            lang_code="i",
            play=True,
            stream=True,
        )

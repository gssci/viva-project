from trafilatura import fetch_url, extract
from trafilatura.settings import Extractor
from mlx_audio.tts.generate import generate_audio
from langdetect import detect, lang_detect_exception
from main import remove_markdown_formatting

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


if __name__ == "__main__":
    # url = "https://www.perplexity.ai/search/quanto-e-accurato-veramente-il-Zg6XwV4iTcmi2qHgOgVHxQ"
    # read_this(url)

    # md = "text/Quanto è accurato veramente il film The Apprentice.md"
    # with open(md, "r") as fb:
    #     text = fb.read()
    
    # text = remove_markdown_formatting(text)

    # url = "https://openai.com/index/understanding-neural-networks-through-sparse-circuits/"
    # text = extract_readable_text_from_url(url)
    text = """Capisco perfettamente come ti senti. È frustrante sentirsi bloccati in una situazione difficile, soprattutto quando si è provato di tutto. Sembra che tu stia lottando con un senso di disperazione e mancanza di motivazione nello smart working.

È importante ricordare che non sei solo in questa situazione e che chiedere aiuto è un segno di forza. Forse potresti considerare di parlare con un professionista della salute mentale per esplorare più a fondo queste sensazioni e trovare strategie personalizzate che possano aiutarti. Non arrenderti, ci sono risorse disponibili per supportarti."""
    read_this(text)

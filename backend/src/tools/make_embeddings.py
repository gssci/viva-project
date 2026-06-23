import json
import logging
import urllib.request
from typing import List, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration Parameters
VIVA_LLM_MODEL = "text-embedding-embeddinggemma-300m-qat"
VIVA_LLM_BASE_URL = "http://127.0.0.1:1234/v1"
VIVA_LLM_API_KEY = "lm-studio"


def get_embeddings(texts: Union[str, List[str]]) -> List[List[float]]:
    """Generates text embeddings using an OpenAI-compatible API.

    Args:
        texts: A single string or a list of strings to embed.

    Returns:
        A list of embedding vectors (lists of floats).
    """
    # Clean up URL to ensure it appends the correct endpoint
    base_url = VIVA_LLM_BASE_URL.rstrip("/")
    endpoint = f"{base_url}/embeddings"

    # Prepare payload (OpenAI spec accepts both str and list of str for "input")
    payload = {"input": texts, "model": VIVA_LLM_MODEL}
    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {VIVA_LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(endpoint, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))

            # Extract embeddings from the response array
            embeddings = [item["embedding"] for item in result["data"]]

            # Log details about the retrieved embeddings
            logging.info(f"Successfully retrieved {len(embeddings)} embedding(s).")
            for i, emb in enumerate(embeddings):
                logging.info(
                    f"Embedding [{i}] length: {len(emb)} | First 5 dimensions: {emb[:5]}"
                )

            return embeddings

    except Exception as e:
        logging.error(f"Failed to generate embeddings: {e}")
        raise


# --- Example Usage ---
if __name__ == "__main__":
    # Example 1: Single String
    logging.info("Testing single string input:")
    get_embeddings("Your text goes here")

    # Example 2: Multiple Strings
    logging.info("\nTesting multiple strings input:")
    get_embeddings(["First sentence to embed", "Second sentence to embed"])
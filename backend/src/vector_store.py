import os
import logging
from typing import List
import chromadb
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from agent_tools import all_agent_tools

# Configuration Parameters
EMBEDDING_MODEL = os.getenv("VIVA_EMBEDDING_MODEL", "text-embedding-embeddinggemma-300m-qat")
LLM_BASE_URL = os.getenv("VIVA_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("VIVA_LLM_API_KEY", "lm-studio")

DEFAULT_DB_DIR = os.path.expanduser("~/.viva/vector_db")
VECTOR_DB_DIR = os.getenv("VIVA_VECTOR_DB_DIR", DEFAULT_DB_DIR)
COLLECTION_NAME = "viva_tools"

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """Manages the persistent Chroma DB instance, configured locally,
    and handles seeding it with tool definitions.
    """

    def __init__(self) -> None:
        self.db_dir = os.path.abspath(VECTOR_DB_DIR)
        logger.info(f"Initializing VectorStoreManager with DB path: {self.db_dir}")
        os.makedirs(self.db_dir, exist_ok=True)

        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            tiktoken_enabled=False,
            check_embedding_ctx_length=False,
        )
        self.client = chromadb.PersistentClient(path=self.db_dir)
        self._vector_store: Chroma | None = None

    def get_vector_store(self) -> Chroma:
        """Returns the langchain-wrapped Chroma vector store instance."""
        if self._vector_store is None:
            self._vector_store = Chroma(
                client=self.client,
                collection_name=COLLECTION_NAME,
                embedding_function=self.embeddings,
            )
        return self._vector_store

    async def initialize_vector_db(self) -> None:
        """Initializes the database with docstrings of all registered agent tools.
        Runs idempotently by using the tool name as the document ID.
        """
        logger.info("Initializing vector database with tool docstrings...")
        try:
            documents: List[Document] = []
            ids: List[str] = []

            for tool in all_agent_tools:
                # Extract the tool's docstring/description.
                description = (
                    getattr(tool, "description", "")
                    or getattr(tool, "func", {}).__doc__
                    or ""
                ).strip()

                if not description:
                    logger.warning(
                        f"Tool '{tool.name}' has no description/docstring. Skipping."
                    )
                    continue

                doc = Document(
                    page_content=description,
                    metadata={
                        "name": tool.name,
                        "description": description,
                    },
                )
                documents.append(doc)
                ids.append(tool.name)

            if not documents:
                logger.info("No tools with valid descriptions found for vector DB indexing.")
                return

            logger.info(f"Adding/Updating {len(documents)} tools in the vector DB...")
            vector_store = self.get_vector_store()

            # Perform indexing in executor to prevent blocking FastAPI's event loop
            import asyncio
            from functools import partial
            loop = asyncio.get_running_loop()
            func = partial(vector_store.add_documents, documents, ids=ids)
            await loop.run_in_executor(None, func)
            logger.info("Successfully updated vector database with tool docstrings.")

        except Exception as e:
            # Gracefully handle failures (like LM Studio being offline) so that the app starts up.
            logger.error(
                f"Failed to initialize vector database with tool docstrings: {e}. "
                "Ensure LM Studio is running and the embedding model is loaded."
            )


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    manager = VectorStoreManager()

    async def main():
        await manager.initialize_vector_db()
        db = manager.get_vector_store()
        query = "calendar events schedule"
        print(f"\nQuerying: '{query}'")
        try:
            results = db.similarity_search(query, k=3)
            print("\nResults:")
            for i, doc in enumerate(results):
                print(
                    f"[{i}] Tool: {doc.metadata.get('name')} | Description: {doc.page_content[:120]}..."
                )
        except Exception as e:
            print(f"Query failed: {e}")

    asyncio.run(main())

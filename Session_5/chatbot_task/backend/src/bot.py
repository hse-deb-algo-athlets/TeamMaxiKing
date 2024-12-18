import logging
import os
import re
from typing import List
from uuid import uuid4

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import DEFAULT_DATABASE, DEFAULT_TENANT, Settings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.documents.base import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableSerializable
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

# TODO: Implement the functions of the CustomChatBot Class. Use the knowledge and code from Session_4

class CustomChatBot:
    """
    A class representing a chatbot that uses a ChromaDB client for document retrieval
    and the ChatOllama model for generating answers.

    This chatbot uses a retrieval-augmented generation (RAG) pipeline where it retrieves
    relevant information from a custom document database (ChromaDB) and then generates
    concise answers using a language model (ChatOllama).
    """

    def __init__(self, index_data: bool) -> None:
        """
        Initialize the CustomChatBot class by setting up the ChromaDB client for document retrieval
        and the ChatOllama language model for answer generation.
        """
        # Initialize the embedding function for document retrieval
        self.embedding_function = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2", cache_folder="/embedding_model")
        
        # Initialize the ChromaDB client
        self.client = self._initialize_chroma_client()
        
        # Get or create the document collection in ChromaDB
        self.vector_db = self._initialize_vector_db()

        # Process pdf, embedd data and index to ChromaDB
        if index_data:
            self._index_data_to_vector_db()

        # Initialize the document retriever
        self.retriever = self.vector_db.as_retriever()

        # Initialize the large language model (LLM) from Ollama
        # TODO: ADD HERE YOUR CODE
        self.llm = ChatOllama(model="llama3.2", base_url="http://ollama:11434")
        # Set up the retrieval-augmented generation (RAG) pipeline
        self.qa_rag_chain = self._initialize_qa_rag_chain()

        self.questions = {}


    def _initialize_chroma_client(self) -> ClientAPI:
        """
        Initialize and return a ChromaDB HTTP client for document retrieval.

        Returns:
            chromadb.HttpClient: A client used to communicate with ChromaDB.
        """
        logger.info("Initialize chroma db client.")
        client = chromadb.HttpClient(
            host="chroma",
            port=8000,
            ssl=False,
            headers=None,
            settings=Settings(allow_reset=True, anonymized_telemetry=False),
            tenant=DEFAULT_TENANT,
            database=DEFAULT_DATABASE,
        )

        return client

    def _initialize_vector_db(self) -> Chroma:
        """
        Initialize and return a Chroma vector database using the HTTP client.

        Returns:
            Chroma: A vector database instance connected to the document collection in ChromaDB.
        """
        logger.info("Initialize chroma vector db.")

        collection_name = "Collection"
        collection = self.client.get_or_create_collection(collection_name)

        vector_db_from_client = Chroma(
            client=self.client,
            collection_name=collection_name,
            embedding_function=self.embedding_function
        )

        return vector_db_from_client
    
    #Collection Name anpassen falls ungültige Zeichen enthalten sind
    def _validate_and_adjust_collection_name(self, name: str) -> str:
        pdf_name = os.path.splitext(name)[0]
        adjusted_name = re.sub(r"[^a-zA-Z0-9_-]", "", pdf_name)
        
        if adjusted_name and not adjusted_name[0].isalnum():
            adjusted_name = re.sub(r"^[^a-zA-Z0-9]+", "", adjusted_name)
        if adjusted_name and not adjusted_name[-1].isalnum():
            adjusted_name = re.sub(r"[^a-zA-Z0-9]+$", "", adjusted_name)
        
        if len(adjusted_name) < 3:
            adjusted_name = adjusted_name.ljust(3, "x")
        elif len(adjusted_name) > 63:
            adjusted_name = adjusted_name[:63]
        
        return adjusted_name
    
    def set_vector_db_collection(self, collection: str):
        
        adjusted_collection_name = self._validate_and_adjust_collection_name(collection)
        logger.info(f"Setting new collection: {adjusted_collection_name}")

        self.client.get_or_create_collection(adjusted_collection_name)

        vector_db_from_client = Chroma(
            client=self.client,
            collection_name=adjusted_collection_name,
            embedding_function=self.embedding_function
        )

        self.vector_db = vector_db_from_client
        
        #RAG Chain neu initialisieren mit neuer Vector DB
        self.qa_rag_chain = self._initialize_qa_rag_chain()

    def get_current_collection(self):
        collection = self.vector_db._collection_name
        return collection

    def delete_collection(self, collection: str):
        try:
            self.client.delete_collection(name=collection)
            return f"Collection {collection} gelöscht"
        except Exception as e:
            logger.info("Collection existiert nicht")
            return f"Collection {collection} konnte nicht gelöscht werden: {e}"
        


    def get_vector_db_collections(self): 
        collections = self.client.list_collections()
        collection_names = [collection.name for collection in collections]
        return collection_names
    
        

    def _clean_document_text(self, chunk):
            # Remove surrogate pairs
            text = chunk.page_content
            text = re.sub(r'[\ud800-\udfff]', '', text)
            # Optionally remove non-ASCII characters (depends on your use case)
            #text = re.sub(r'[^\x00-\x7F]+', '', text)
            return Document(page_content=text, metadata=chunk.metadata)
    
    def index_file_to_vector_db(self, path: str):
        loader = PyPDFLoader(file_path=path)
        pages = loader.load()
        pages_chunked = RecursiveCharacterTextSplitter(
            chunk_size=3000,
            chunk_overlap=300
            ).split_documents(pages)
        pages_chunked_cleaned = [self._clean_document_text(chunk) for chunk in pages_chunked]

        for page in pages_chunked_cleaned:
            logger.info(page.page_content)
            logger.info("--------------------------------------------------")
        
        uuids = [str(uuid4()) for _ in range(len(pages_chunked_cleaned))]
        self.vector_db.add_documents(documents=pages_chunked_cleaned, id=uuids)

        logger.info(f"File {path} loaded")


    def _index_data_to_vector_db(self):
        pdf_doc = "src/AI_Book.pdf"

        # Create pdf data loader
        # ADD HERE YOUR CODE
        loader = PyPDFLoader(file_path=pdf_doc)

        # Load and split documents in chunks
        # ADD HERE YOUR CODE
        pages = loader.load()
        pages_chunked = RecursiveCharacterTextSplitter(
            #chunk_size=1024,
            #chunk_overlap=50
            ).split_documents(pages)
        
        pages_chunked_cleaned = [self._clean_document_text(chunk) for chunk in pages_chunked]

        uuids = [str(uuid4()) for _ in range(len(pages_chunked_cleaned[:50]))]
        self.vector_db.add_documents(documents=pages_chunked_cleaned[:50], id=uuids)
        
        logger.info("AI Book loaded")



    def _qa_generation_chain(self, chunk: str):
        """
        Pipeline um Fragen auf Chunk eines Embeddings zu generieren. Frage muss richtig formatiert werden für die Auswertung
        """

        promt_template = """
        Du bist ein Assistent, der Fragen und Single-Choice-Antworten basierend auf einem gegebenen Text erstellt.
        Struktur:
        1. Generiere eine Frage, die den Inhalt des Texts testet.
        2. Gib drei mögliche Antworten (A, B, C), wobei nur eine korrekt ist.
        3. Markiere, welche Antwort korrekt ist.
        
        Befolge das folgende Format exakt wie geschrieben, verwende keine zusätzliche Formatierung. 
        
        Format:
        Frage: [Deine generierte Frage]
        A) [Antwort 1]
        B) [Antwort 2]
        C) [Antwort 3]
        Korrekte Antwort: [z.B. A]

        Hier ist der gegebene Text:
        {context}
        """
        promt = ChatPromptTemplate.from_template(promt_template)

        qa_chain = (
            {"context" : RunnablePassthrough()}
            | promt
            | self.llm
            | StrOutputParser()
        )
        
        output = qa_chain.invoke({"context":chunk})
        return output
    
    def _parse_output(self, output):
        pattern = r"Frage: (.*?)\nA\) (.*?)\nB\) (.*?)\nC\) (.*?)\nKorrekte Antwort: (.*?)$"
        match = re.search(pattern, output, re.DOTALL)
        if match:
            return {
                "Frage": match.group(1),
                "Antworten": {
                    "A": match.group(2),
                    "B": match.group(3),
                    "C": match.group(4),
                },
                "Korrekte_Antwort": match.group(5),
            }
        return None
    
    def generate_questions(self):
        curr_collection_name = self.get_current_collection()
        collection = self.client.get_collection(name=curr_collection_name)
        
        docs = collection.get()['documents'] or []
        for i, doc in enumerate(docs):
            logger.info(f"Generiere Frage {i} für: {doc}")
            result = self._qa_generation_chain(doc)
            logger.info(result)
            
            output = self._parse_output(result)
            if output:
                self.questions[i] = output

        return self.questions

    def _initialize_qa_rag_chain(self) -> RunnableSerializable:
        """
        Set up the retrieval-augmented generation (RAG) pipeline for answering questions.
        
        The pipeline consists of:
        - Retrieving relevant documents from ChromaDB.
        - Formatting the retrieved documents for input into the language model (LLM).
        - Using the LLM to generate concise answers.
        
        Returns:
            dict: The RAG pipeline configuration.
        """
        prompt_template = """
        Du bist ein Assistent um Fragen zu beantworten. Benutze die folgenden Informationen aus dem Kontext um die Frage zu beantworten. Wenn du dir nicht sicher bist, sag dass du es nicht weißt. Benutze eine angemessene Anzahl an Sätzen um die Frage zu beantorten, antworte detailiert.  
        Kontext:
        <context>
        {context}
        </context>


        {question}"""

        rag_prompt = ChatPromptTemplate.from_template(prompt_template)
        retriever = self.vector_db.as_retriever(
            #search_type="similarity_score_threshold",
            search_kwargs={"k": 5}
            #search_kwargs={"score_threshold": 0.2}
            )



        qa_rag_chain = (
            {"context": retriever | self._format_docs, "question": RunnablePassthrough()}
            | rag_prompt
            | self.llm
            | StrOutputParser()
        )
        return qa_rag_chain
    def _format_docs(self, docs: List[Document]) -> str:
        """
        Helper function to format the retrieved documents into a single string.
        
        Args:
            docs (List[Document]): A list of documents retrieved by ChromaDB.

        Returns:
            str: A string containing the concatenated content of all retrieved documents.
        """

        for i, doc in enumerate(docs):
            logger.info(f"Dokument {i+1}: {doc.page_content}, Metadaten: {doc.metadata}")

        return "\n\n".join(doc.page_content for doc in docs)

    async def astream(self, question: str):
        """
        Handle a user query asynchronously by running the question through the RAG pipeline and stream the answer.

        Args:
            question (str): The user's question as a string.

        Yields:
            str: The generated answer from the model, streamed chunk by chunk.
        """
        logger.info("Streaming RAG chain response.")
        try:
            async for chunk in self.qa_rag_chain.astream(question):
                logger.debug(f"Yielding chunk: {chunk}")
                yield chunk
        except Exception as e:
            logger.error(f"Error in stream_answer: {e}", exc_info=True)
            raise
        finally:
            logger.info("Stream complete")
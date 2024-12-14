import logging
import os
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import (FastAPI, File, HTTPException, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.bot import CustomChatBot

INDEX_DATA = bool(int(os.environ["INDEX_DATA"]))
#INDEX_DATA = False

# Set up logger
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager to ensure CustomChatBot is initialized and cleaned up correctly.
    """
    logger.info("Creating instance of custom chatbot.")
    logger.info(f"Index data to vector store: {INDEX_DATA}")
    app.state.chatbot = CustomChatBot(index_data=INDEX_DATA)
    try:
        yield
    finally:
        logger.info("Cleaning up chatbot instance.")
        del app.state.chatbot 

# Create FastAPI app and configure CORS
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust to restrict domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CollectionRequest(BaseModel):
    collection_name: str



# Dateiupload
@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):    
    upload_dir = "pdfs"
    try:
        os.makedirs(upload_dir, exist_ok=True)

        filename = file.filename or "default.pdf"
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        
        app.state.chatbot.set_vector_db_collection(filename)

        if True:
            logger.debug("Lade Datei in Vector DB...")
            app.state.chatbot.index_file_to_vector_db(file_path)
        return JSONResponse(content={"message": f"Datei '{filename}' erfolgreich hochgeladen!"})
    
    except Exception as e:
         return JSONResponse(status_code=500, content={"message": "Fehler beim Hochladen", "error": str(e)})
    
@app.get("/get_collections")
def get_collections():
    collections = app.state.chatbot.get_vector_db_collections()
    return collections


@app.get("/get_current_collection")
def get_current_collection():
    collection = app.state.chatbot.get_current_collection()
    return CollectionRequest(collection_name= collection)


@app.post("/set_collection")
def set_collection(request: CollectionRequest):
    # TODO Setzen der Collection die verwendet werden soll (VectorDB neu initialisieren mit neuer collection)
    collection_name = request.collection_name
    app.state.chatbot.set_vector_db_collection(collection_name)
    return {"message": f"Collection {collection_name} ausgewählt"}

@app.put("/delete_collection")
def delete_collection(collection_name: str):
    result = app.state.chatbot.delete_collection(collection_name)
    return result

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that handles communication with the client.
    """
    await websocket.accept()
    logger.info('Client connected.')

    try:
        while True:
            try:
                # Receive input from the WebSocket client
                input_data = await websocket.receive_text()
                logger.info(f"Received input: {input_data}")

                # Process the input using the chatbot's stream_answer method
                async for chunk in app.state.chatbot.astream(input_data):
                    chain_result = chunk
                    logger.info(f"Sending chunk: {chain_result}")
                    # Send the response chunk back to the client
                    await websocket.send_text(chain_result)

                logger.info("Ende des Streams")
                await websocket.close()
                break

            except WebSocketDisconnect:
                # Graceful handling of WebSocket disconnection
                logger.info("Client disconnected.")
                break

            except Exception as e:
                # Handle unexpected errors during input processing
                logger.error(f"Error processing chatbot response: {str(e)}")
                logger.error(traceback.format_exc())
                await websocket.send_text(f"Error: {str(e)}")
                break

    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.info('WebSocket connection closed.')

if __name__ == "__main__":
    # Run the FastAPI app with uvicorn
    uvicorn.run("main:app", host="backend", port=5001, reload=True, log_level="debug")

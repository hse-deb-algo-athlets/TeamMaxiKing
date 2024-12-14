import logging

import gradio as gr
import requests
import websockets

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

base_url = "http://backend:5001/"

current_selected_collection = ""

def upload_pdf(path: str):
    if not path:
        gr.Warning(f"Keine Datei ausgewählt")
        return update_dropdown()
    
    logger.info(f"Dateipfad: {path}")
    
    url = base_url + "upload_pdf"

    with open(path, "rb") as f:
        logger.info("Datei geladen")
        files = {"file": f}
        response = requests.post(url, files=files)

    logger.info(response.text)

    if response.status_code == 200:
        gr.Info(response.json()['message'])
        #TODO Geuploadete Collection auswählen im Dropdown
        
        return  update_dropdown()
    else:
        gr.Warning(response.json()['message'])
        return update_dropdown()
    
def get_collections():
    """
    Abfragen der Collections die in der ChromaDB gespeichert sind
    """

    try:
        url = base_url + "get_collections"
        response = requests.get(url)
        response.raise_for_status()

        collections = response.json()
        logger.debug(collections)
        return collections
    except Exception as e:
        gr.Warning(f"Fehler beim Collections laden: {e}")

def set_collection(selected_collection: str):
    """
    Setzen der Collection die für die RAG Chain verwendet werden soll
    """
    try:
        url = base_url + "set_collection"
        
        data = {"collection_name": selected_collection}

        response = requests.post(url, json=data)
        response.raise_for_status()
        logger.info(f"Collection {selected_collection} ausgewählt")
    except:
        gr.Warning(f"Fehler beim Setzen von {selected_collection}")
        
def update_dropdown(selected_collection=None):
    """
    Aktualisiere das Dropdown-Menü mit neuen Collections und optional einer vorausgewählten Collection.
    """
    new_choices = get_collections()
    selected_value = selected_collection if selected_collection else (new_choices[0] if new_choices else None)
    return gr.Dropdown(choices=new_choices, value=selected_value)

# WebSocket chat function (asynchronous generator)
async def websocket_chat(message: str):
    uri = "ws://backend:5001/ws"
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Sending message to WebSocket: {message}")
            await websocket.send(message)

            while True:
                try:
                    chunk = await websocket.recv()
                    logger.info(f"Received chunk: {chunk}")
                    yield chunk  # Stream chunk to Gradio
                except websockets.exceptions.ConnectionClosed:
                    logger.info("WebSocket connection closed by the server.")
                    break  # Verbindung geschlossen, Stream beenden
                except Exception as e:
                    logger.error(f"Error receiving chunk: {str(e)}")
                    yield f"Error: {str(e)}"
                    break

    except Exception as e:
        logger.error(f"Error during WebSocket communication: {str(e)}")
        yield f"Error: {str(e)}"

# Chat function to update the chatbot message history
async def chat(message: str, history=[]):
    if not message.strip():
        yield "Please enter a valid question."
        return

    try:        
        # Stream chunks from WebSocket and append them incrementally
        bot_message = ""
        async for chunk in websocket_chat(message):
            bot_message += str(chunk)  # Accumulate chunks
            yield bot_message  # Yield updated history incrementally for display

    except Exception as e:
        message = f"Error: {e}"
        yield message

# Launch Gradio Chat Interface
with gr.Blocks() as demo:
    collections = get_collections()
    gr.Markdown("### MaxiKing Chatbot")
    
    with gr.Row():
        with gr.Column(scale=2):
            gr.ChatInterface(
                fn=chat,
                chatbot=gr.Chatbot(height=400),  # Adjusted height for better usability
                #textbox=gr.Textbox(placeholder="Ask me questions about your script...", container=False, scale=7),
                #title="Chatbot",
                #description="Ask me questions about your lecture.",
                #theme="soft",
                examples=["What is supervised learning?", "What is deep learning?", "What is a linear regression?"],
            )
        with gr.Column():
            dropdown = gr.Dropdown(label="Collection",
                                   info="Collection für Kontext auswählen",
                                   choices=collections,
                                   value=collections[0] if collections else None,
                                   interactive=True)
            upload_button = gr.UploadButton("Datei hinzufügen", file_types=[".pdf"], file_count="single")
        
        upload_button.upload(upload_pdf, inputs=upload_button, outputs=dropdown)
        dropdown.change(set_collection, inputs=dropdown)
    demo.load(update_dropdown, outputs=dropdown)
demo.launch(debug=True)



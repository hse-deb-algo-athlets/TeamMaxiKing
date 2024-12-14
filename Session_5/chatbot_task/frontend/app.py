import logging

import gradio as gr
import requests
import websockets

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_pdf(path: str):
    if not path:
        return "Bitte Datei auswählen"
    
    logger.info(f"Dateipfad: {path}")
    url = "http://backend:5001/upload_pdf"

    with open(path, "rb") as f:
        logger.info("Datei geladen")
        files = {"file": f}
        response = requests.post(url, files=files)

    logger.info(response.text)

    if response.status_code == 200:
        return f"Datei wurde übertragen: {response.json()['message']}"
    else:
        return f"Fehler bei der Übertragung: {response.status_code}, {response.text}"

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
            dropdown = gr.Dropdown([
                "Datei 1",
                "Datei 2",
                "Datei 3"
            ], label="Collection", info="Collection für Kontext auswählen")
            upload_button = gr.UploadButton("Datei hinzufügen", file_types=[".pdf"], file_count="single")
        upload_button.upload(upload_pdf, inputs=upload_button)
demo.launch(debug=True)
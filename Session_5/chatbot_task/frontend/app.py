import json
import logging

import gradio as gr
import pandas as pd
import requests
import websockets

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

base_url = "http://backend:5001/"

current_selected_collection = ""

current_question_index = 0
questions = []
correct_answers = []
correct_count = 0
wrong_count = 0


def upload_pdf(path: str):
    if not path:
        gr.Warning(f"Keine Datei ausgewählt")   
    
    logger.info(f"Dateipfad: {path}")
    
    url = base_url + "upload_pdf"

    with open(path, "rb") as f:
        logger.info("Datei geladen")
        files = {"file": f}
        response = requests.post(url, files=files)

    logger.info(response.text)

    if response.status_code == 200:
        gr.Info(response.json().get('message', 'Upload erfolgreich'))
        #TODO Geuploadete Collection auswählen im Dropdown
        return  update_dropdown()
    else:
        gr.Warning(response.json().get('message', 'Fehler beim Upload'))
    
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
        return []

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
    except Exception as e:
        gr.Warning(f"Fehler beim Setzen von {selected_collection}: {e} ")

def delete_collection(selected_collection:str):
    try:
        url = base_url + "delete_collection"
        
        data = {"collection_name": selected_collection}

        response = requests.put(url, json=data)
        response.raise_for_status()
        logger.info(f"Collection {selected_collection} gelöscht")
        gr.Info(f"Collection {selected_collection} gelöscht")
        return True
    except Exception as e:
        gr.Warning(f"Fehler beim Löschen von {selected_collection}: {e}")
        return False


def generate_questions():
    """
    Generieren von Fragen basierend auf der momentan ausgewählten Collection    
    """
    try:
        url = base_url + "generate_questions"
        response = requests.post(url)
        response.raise_for_status()

        data = response.json()
        if isinstance(data, str):  # Falls Backend String liefert, dekodieren
            data = json.loads(data)
        return data

    except Exception as e:
        gr.Warning(f"Fehler bei der Generierung von Fragen: {e}")

def update_dropdown(selected_collection=None):
    """
    Aktualisiere das Dropdown-Menü mit neuen Collections und optional einer vorausgewählten Collection.
    """
    if selected_collection == None:
        curr_collection = requests.get(base_url + "get_current_collection")
        name = curr_collection.json()['collection_name']
        selected_collection = name
        
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
        yield f"Fehler: {e}"

def handle_question_generation():
    """Lädt die Fragen und setzt den Index zurück."""
    global questions, correct_answers, current_question_index

    # Fragen vom Backend abrufen
    data = generate_questions()
    if not data or not isinstance(data, list):  # Prüfen, ob Daten vorhanden und eine Liste sind
        gr.Warning("Keine Fragen generiert oder ungültiges Format erhalten.")
        questions = []  # Leere Liste als Fallback
        correct_answers = []
        return ("Keine Frage", "", "", "", "", "")

    # Fragen und Antworten initialisieren
    questions = data
    correct_answers = [q.get("Korrekte_Antwort", "") for q in questions]  # Verhindert KeyError
    current_question_index = 0

    # Erste Frage anzeigen
    return show_question(0)

def show_question(index):
    """Zeigt die Frage und Antworten für den gegebenen Index."""
    if not questions or index >= len(questions):  # Sicherstellen, dass Fragen vorhanden sind
        return ("Keine weiteren Fragen.", "", "", "", "", "")

    # Aktuelle Frage extrahieren
    question = questions[index]
    return (
        question.get("Frage", "Keine Frage verfügbar"),  # Default-Werte, falls Keys fehlen
        question.get("Antworten", {}).get("A", ""),
        question.get("Antworten", {}).get("B", ""),
        question.get("Antworten", {}).get("C", ""),
        question.get("Erklärung", ""),
        ""
    )

def check_answer(answer: str):
    """Überprüft die Antwort und zeigt Feedback an."""
    global current_question_index, correct_count, wrong_count, stats

    is_last_question = current_question_index == len(questions) - 1

    correct = correct_answers[current_question_index].split(" ")[0]
    frage = questions[current_question_index].get("Frage", "Keine Frage verfügbar") 
    logger.info(f"Antwort: {answer}, Korrekt: {correct}")
    is_correct = answer == correct

    # Ergebnis anzeigen
    if is_correct:
        gr.Info("Korrekt!")
        correct_count += 1
    else:
        gr.Warning(f"Falsch! Die richtige Antwort wäre: {correct}:{frage}")
        wrong_count += 1


# Fortschreiten zur nächsten Frage oder Abschluss anzeigen
    if is_last_question:
        return ("Alle Fragen beantwortet!", "", "", "", "", "")  # Klarer Abschluss

    # Index erst nach Überprüfung erhöhen
    current_question_index += 1
    return show_question(current_question_index)

def update_stat():
    global correct_count, wrong_count
    stats = pd.DataFrame({
        "Bewertung": ["Korrekt", "Falsch"],
        "Anzahl": [correct_count, wrong_count]
    })
    return stats
        
# Launch Gradio Chat Interface
with gr.Blocks() as demo:
    collections = get_collections() or []
    collections_state =gr.State(collections) #State um Collections zu speichern, bei Änderung wird Verwaltung neu gerendert

    logger.info(f"Collections: {collections}, collection state {collections_state}")

    gr.Markdown("### MaxiKing Chatbot")
    with gr.Tab("Chatbot"):
        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.ChatInterface(
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
            
            upload_button.upload(upload_pdf, inputs=upload_button, outputs=[dropdown, collections_state])
            dropdown.change(set_collection, inputs=dropdown)
    with gr.Tab("Quiz"):
    # Button zum Generieren von Fragen
        gen_questions_button = gr.Button("Fragen generieren")

    # Spalte für generierte Fragen
        with gr.Column():
            question_output = gr.Textbox(label="Frage:", interactive=False)
            

        # Antworten
            with gr.Row():
                answer_button_A = gr.Button(value="A)")
                answer_button_B = gr.Button(value="B)")
                answer_button_C = gr.Button(value="C)")

        # Erklärung ausklappbar
            with gr.Accordion("Erklärung anzeigen", open=False):
                    explanation_output = gr.Textbox(label="Erklärung:", interactive=False)

    # Aktionen zuweisen
        gen_questions_button.click(
            handle_question_generation,
            outputs=[question_output, answer_button_A, answer_button_B, answer_button_C, explanation_output]
        )

        answer_button_A.click(lambda: check_answer("A)"), outputs=[
            question_output, answer_button_A, answer_button_B, answer_button_C, explanation_output
        ])
        answer_button_B.click(lambda: check_answer("B)"), outputs=[
            question_output, answer_button_A, answer_button_B, answer_button_C, explanation_output
        ])
        answer_button_C.click(lambda: check_answer("C)"), outputs=[
            question_output, answer_button_A, answer_button_B, answer_button_C, explanation_output
        ])

       

    with gr.Tab("Statistik"):
            with gr.Row():
                # BarPlot-Komponente zur Darstellung der Statistiken
                stat_chart = gr.BarPlot(
                    value=pd.DataFrame({"Bewertung": [], "Anzahl": []}),  # Leerer Startwert
                    x="Bewertung",
                    y="Anzahl",
                    color="Bewertung",
                    title="Statistik",
                    color_map={"Korrekt": "#75ff33", "Falsch": "#FF5733"}
                )

            # Button zum Aktualisieren der Statistik
            update_stat_button = gr.Button("Statistik aktualisieren")
            update_stat_button.click(update_stat, outputs=stat_chart)

    with gr.Tab("Verwaltung"):
        #Automatisches generieren der Buttons zum Löschen von Collections
        #TODO: Beim Upload einer neuen Datei State ändern, dass Tab neu gerendert wird
        @gr.render(inputs=collections_state)
        def render_collections(collections):
            for collection in collections:
                #Für jede Collection einen Button erstellen
                with gr.Row():
                    gr.Textbox(f"Collection {collection}", show_label=False, container=False)
                    delete_btn = gr.Button("Löschen", scale=0, variant="stop")
                    
                    def delete(collection = collection):       
                        #Überprüfung ob Collection ohne Fehler gelöscht wurde, nur dann diese aus der Ansicht entfernen
                        if delete_collection(str(collection)): 
                            collections.remove(collection) #Collection aus State löschen damit neu gerendert wird

                        dropdown = update_dropdown()    #Dropdown aktualiseren
                        return collections, dropdown
                         
                    delete_btn.click(delete, None, [collections_state, dropdown])
    
    demo.load(update_dropdown, outputs=dropdown)
    demo.load(get_collections, outputs=collections_state)
demo.launch(debug=True)

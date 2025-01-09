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


def upload_pdf(path: str):
    if not path:
        gr.Warning(f"Keine Datei ausgewählt")

    url = base_url + "upload_pdf"

    with open(path, "rb") as f:
        logger.info("Datei geladen")
        files = {"file": f}
        response = requests.post(url, files=files)

    if response.status_code == 200:
        gr.Info(response.json().get('message', 'Upload erfolgreich'))
        # TODO Geuploadete Collection auswählen im Dropdown

        return update_dropdown(), get_collections()
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


def delete_collection(selected_collection: str):
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


def generate_questions() -> dict:
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
        return {}


def update_dropdown(selected_collection=None):
    """
    Aktualisiere das Dropdown-Menü mit neuen Collections und optional einer vorausgewählten Collection.
    """
    if selected_collection == None:
        curr_collection = requests.get(base_url + "get_current_collection")
        name = curr_collection.json()['collection_name']
        selected_collection = name

    new_choices = get_collections()
    selected_value = selected_collection if selected_collection else (
        new_choices[0] if new_choices else None)
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
    data = generate_questions()
    return data


def show_question(questions: dict):

    if not questions:
        return ("Alle Fragen beantwortet!", " - ", " - ", " - ", " - ", " - ")
    else:
        first_key = list(questions.keys())[0]
        current_question = questions[first_key]

        frage = current_question["Frage"]
        answer_A = current_question["Antworten"]["A"]
        answer_B = current_question["Antworten"]["B"]
        answer_C = current_question["Antworten"]["C"]
        erklärung = current_question["Erklärung"]

        return frage, answer_A, answer_B, answer_C, erklärung


def select_next_question(questions: dict) -> dict:
    if not questions:
        return {}
    else:
        first_key = list(questions.keys())[0]
        del questions[first_key]
        return questions


def check_answer(selected_answer: str, questions: dict, stats: pd.DataFrame):
    if not questions:
        gr.Info("Alle Fragen beantwortet!")

    else:
        first_key = list(questions.keys())[0]
        current_question = questions[first_key]
        # Ersten Buchstaben nehmen der Antwort, falls noch mehr dabei steht
        correct_answer = current_question["Korrekte_Antwort"][0]
        correct_answer_text = current_question["Antworten"][correct_answer]

        if selected_answer in correct_answer:
            gr.Info("Richtig!")
            stats.loc[stats["Bewertung"] == "Richtig", "Anzahl"] += 1

        else:
            gr.Warning(
                f"Falsch! Die Richtige Antwort wäre {correct_answer}: {correct_answer_text}")
            stats.loc[stats["Bewertung"] == "Falsch", "Anzahl"] += 1
        return select_next_question(questions), update_stat_chart(stats)
    return questions, stats


def update_stat_chart(stats):
    return gr.BarPlot(
        value=stats,
        x="Bewertung",
        y="Anzahl",
        color="Bewertung",
        title="Statistik",
        color_map={"Richtig": "#75ff33", "Falsch": "#FF5733"}
    )


# Launch Gradio Chat Interface
with gr.Blocks() as demo:
    collections = get_collections() or []
    questions = gr.State({})
    stats = gr.State(pd.DataFrame(
        {"Bewertung": ["Richtig", "Falsch"], "Anzahl": [0, 0]}))

    # State um Collections zu speichern, bei Änderung wird Verwaltung neu gerendert
    collections_state = gr.State(collections)

    gr.Markdown("### MaxiKing Chatbot")
    with gr.Tab("Chatbot"):
        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.ChatInterface(
                    fn=chat,
                    # Adjusted height for better usability
                    chatbot=gr.Chatbot(height=600),
                    # textbox=gr.Textbox(placeholder="Ask me questions about your script...", container=False, scale=7),
                    # title="Chatbot",
                    # description="Ask me questions about your lecture.",
                    # theme="soft",
                    examples=["What is supervised learning?",
                              "What is deep learning?", "What is a linear regression?"],
                )
            with gr.Column():
                dropdown = gr.Dropdown(label="Collection",
                                       info="Collection für Kontext auswählen",
                                       choices=collections,
                                       value=collections[0] if collections else None,
                                       interactive=True)
                upload_button = gr.UploadButton("Datei hinzufügen", file_types=[
                                                ".pdf"], file_count="single")

            upload_button.upload(upload_pdf, inputs=upload_button, outputs=[
                                 dropdown, collections_state])
            dropdown.change(set_collection, inputs=dropdown)
    with gr.Tab("Quiz"):
        # Button zum Generieren von Fragen
        gen_questions_button = gr.Button("Fragen generieren")

    # Spalte für generierte Fragen
        with gr.Column():
            question_output = gr.Textbox(label="Frage:", interactive=False)

        # Antworten
            with gr.Row():
                answer_button_A = gr.Button(value="A")
                answer_button_B = gr.Button(value="B")
                answer_button_C = gr.Button(value="C")

        # Erklärung ausklappbar
            with gr.Accordion("Erklärung anzeigen", open=False):
                explanation_output = gr.Textbox(
                    label="Erklärung:", interactive=False)

    # Aktionen zuweisen
        gen_questions_button.click(
            handle_question_generation,
            outputs=questions
        )

        questions.change(show_question, inputs=questions, outputs=[
                         question_output, answer_button_A, answer_button_B, answer_button_C, explanation_output])

    with gr.Tab("Statistik"):
        with gr.Row(variant="panel", equal_height= 1):
            stat_chart = gr.BarPlot(
                value=stats.value,
                x="Bewertung",
                y="Anzahl",
                color="Bewertung",
                title="Gesamt-Statistik",
                color_map={"Richtig": "#75ff33", "Falsch": "#FF5733"}
            )
        with gr.Row():
            stat_chart2 = gr.BarPlot(
                value=stats.value,
                x="Bewertung",
                y="Anzahl",
                color="Bewertung",
                title="Statistik 1",
                color_map={"Richtig": "#75ff33", "Falsch": "#FF5733"}
            )
        with gr.Row():
            stat_chart3 = gr.BarPlot(
                value=stats.value,
                x="Bewertung",
                y="Anzahl",
                color="Bewertung",
                title="Statistik 2",
                color_map={"Richtig": "#75ff33", "Falsch": "#FF5733"}
            )

        answer_button_A.click(check_answer, inputs=[gr.State(
            "A"), questions, stats], outputs=[questions, stat_chart])
        answer_button_B.click(check_answer, inputs=[gr.State(
            "B"), questions, stats], outputs=[questions, stat_chart])
        answer_button_C.click(check_answer, inputs=[gr.State(
            "C"), questions, stats], outputs=[questions, stat_chart])

    with gr.Tab("Verwaltung"):
        # Automatisches generieren der Buttons zum Löschen von Collections
        @gr.render(inputs=collections_state)
        def render_collections(collections):
            for collection in collections:
                # Für jede Collection einen Button erstellen
                with gr.Row():
                    gr.Textbox(f"Collection {collection}",
                               show_label=False, container=False)
                    delete_btn = gr.Button("Löschen", scale=0, variant="stop")

                    def delete(collection=collection):
                        # Überprüfung ob Collection ohne Fehler gelöscht wurde, nur dann diese aus der Ansicht entfernen
                        if delete_collection(str(collection)):
                            # Collection aus State löschen damit neu gerendert wird
                            collections.remove(collection)

                        dropdown = update_dropdown()  # Dropdown aktualiseren
                        return collections, dropdown

                    delete_btn.click(
                        delete, None, [collections_state, dropdown])

    demo.load(update_dropdown, outputs=dropdown)
    demo.load(get_collections, outputs=collections_state)
demo.launch(debug=True)

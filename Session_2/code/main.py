import uvicorn
from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel
import json


app = FastAPI()

class Item(BaseModel):
    name: str
    price: float
    is_offer: Union[bool, None] = None

class User(BaseModel):
    name: str
    studiengang: str
    semester: int

class Statistik(BaseModel):
    fach: str
    fortschritt: float  #0-100%
    fragen_korrekt: int
    fragen_falsch: int
    fragen_gesamt: int

fächer = {
    "Mathe 2": Statistik(fach="Mathe 2", fortschritt=23, fragen_gesamt=50, fragen_falsch=30, fragen_korrekt= 10),
    "Elektronik": Statistik(fach="Elektronik", fortschritt=70, fragen_gesamt=60, fragen_falsch=12, fragen_korrekt= 50), 
}

fächer_json = {key: value.model_dump() for key, value in fächer.items()}
json_string = json.dumps(fächer_json, indent=4)


items = {}

user = User(name="", studiengang="", semester=0)

@app.get("/get_stat")
def get_stat(fach_name: str):
    if fach_name in fächer:
        fach = fächer[fach_name]
        return fach
    else:
        return fächer

@app.put("/create_user")
def create_user(name: str, studiengang: str, semester: int):
    #user = User(name=name, studiengang=studiengang, semester=semester)
    user.name = name
    user.studiengang = studiengang
    user.semester = semester
    return {"name": user.name, "studiengang": user.studiengang, "semester": user.semester}

@app.get("/get_user")
def get_user():
    return {"name": user.name, "studiengang": user.studiengang, "semester": user.semester}


@app.get("/")
def read_root():
    return {"Hello" : "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q":q}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    items[item_id] = item
    return {"item_name": item.name, "item_id": item_id}

@app.get("/getitem")
def get_item(item_id: int):
    if item_id in items:
        item = items[item_id]
        return {"item_name": item.name, "item_price": item.price, "is_offer": item.is_offer}
    else:
        return {"Error": "Invalid ID"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")





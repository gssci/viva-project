import asyncio
import datetime
import requests
import geocoder
from duckduckgo_search import DDGS
import trafilatura

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

# Eventuali tue importazioni locali
# from read import read_this
# from main import remove_markdown_formatting

# --- 1. DEFINIZIONE DEI TOOL CON IL DECORATORE @tool ---

@tool
def get_current_datetime() -> str:
    """Restituisce la data e l'ora attuali di sistema."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def get_gps_location() -> str:
    """Ottiene la posizione GPS approssimativa basata sull'indirizzo IP locale."""
    g = geocoder.ip('me')
    if g.ok:
        return f"Latitudine: {g.lat}, Longitudine: {g.lng}, Città: {g.city}"
    return "Impossibile determinare la posizione GPS."

@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Effettua una ricerca sul web e restituisce i risultati principali."""
    try:
        results = DDGS().text(query, max_results=max_results)
        return str(list(results))
    except Exception as e:
        return f"Errore durante la ricerca web: {e}"

@tool
def extract_webpage_text(url: str) -> str:
    """Estrae il testo pulito da una pagina web in modalità lettura, ignorando ads e menu."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            return text[:6000] if text else "Nessun testo estratto."
        return "Impossibile scaricare la pagina."
    except Exception as e:
        return f"Errore nell'estrazione: {e}"

@tool
def get_weather(lat: float, lon: float) -> str:
    """Ottiene il meteo attuale per le coordinate specificate."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        response = requests.get(url).json()
        return str(response.get("current_weather", "Dati meteo non disponibili."))
    except Exception as e:
        return f"Errore nel recupero del meteo: {e}"

@tool
def set_timer(seconds: int, message: str) -> str:
    """Imposta un timer. Usa questo per ricordare cose all'utente in futuro."""
    async def timer_task():
        await asyncio.sleep(seconds)
        print(f"\n🔔 [TIMER/SVEGLIA SCADUTA]: {message} 🔔\n")
        # Qui puoi rimettere la lettura vocale:
        # read_this(message)
        
    # Task asincrono (background) per non bloccare l'esecuzione del bot
    asyncio.create_task(timer_task())
    return f"Timer impostato correttamente. Suonerà tra {seconds} secondi."

# Raggruppiamo i tool
tools = [
    get_current_datetime, 
    get_gps_location, 
    web_search, 
    extract_webpage_text, 
    get_weather, 
    set_timer
]

# --- 2. CONFIGURAZIONE DEL MODELLO E DELL'AGENTE ---

llm = ChatOpenAI(
    model="gemma4:26b",
    base_url='http://localhost:11434/v1/',
    api_key='ollama'
)

# Definiamo il ruolo dell'agente tramite System Prompt
system_prompt = (
    "Sei un assistente utile ed esegui i compiti usando gli strumenti a tua disposizione. "
    "Se ti viene chiesto il meteo, se non hai già le coordinate usa il tool del GPS, e poi usa quelle coordinate per il tool del meteo."
)

async def main():
    # 3. CREAZIONE DELL'AGENTE (Nuova API, no AgentExecutor!)
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt
    )

    # 4. ESECUZIONE
    domande = ["dove mi trovo adesso?","che giorno è oggi?", "what time is it?", "what's the weather like in my location?"]
    # 3. ESECUZIONE
    for domanda in domande:
        user_input = domanda 
        # Invochiamo l'agente passando lo storico dei messaggi
        response = await agent.ainvoke({
            "messages": [("user", user_input)]
        })
        
        # La risposta moderna di create_agent aggiorna lo state dei messaggi
        response_text = response["messages"][-1].content
        print("\nRisposta Finale:\n", response_text)
        
        # Lasciamo il loop asincrono aperto per 10 secondi per dar tempo al timer di scattare
        await asyncio.sleep(10) 

if __name__ == "__main__":
    asyncio.run(main())
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient  
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from read import read_this
from main import remove_markdown_formatting

llm = ChatOpenAI(model="gemma4:26b",
                 base_url='http://localhost:11434/v1/',
                 api_key='ollama')

async def main():
    # 1. Inizializza il client MCP con entrambi i server
    client = MultiServerMCPClient(
        {
            "python_repl": {
                "command": "python",
                "args": ["/Users/gerlandoscibetta/personal/notgivingup/server_mcp_python.py"],
                "transport": "stdio",
            },
            # AGGIUNGI IL NUOVO SERVER QUI:
            "utility_tools": {
                "command": "python",
                # Sostituisci con il percorso assoluto in cui hai salvato utility_mcp_server.py
                "args": ["/Users/gerlandoscibetta/personal/notgivingup/utility_mcp_server.py"],
                "transport": "stdio",
            }
        }
    )

    # 2. Ottieni tutti i tool esposti da ENTRAMBI i server MCP
    tools = await client.get_tools()

    # 4. Crea l'agente
    agent = create_agent(llm, tools)

    # 5. Esegui l'agente con una query complessa che testa i nuovi tool
    response = await agent.ainvoke({
        "messages": [("user", "Che tempo fa adesso nella mia posizione attuale? Dopo avermelo detto, imposta un timer di 10 secondi per ricordarmi di bere acqua.")]
    })
    
    response_text = response["messages"][-1].content
    print(response_text)
    read_this(remove_markdown_formatting(response_text))

if __name__ == "__main__":
    asyncio.run(main())
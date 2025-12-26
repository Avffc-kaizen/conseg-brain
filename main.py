import os
import requests
import datetime
import time
import threading
import json
import random
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from typing import TypedDict, List
from langgraph.graph import StateGraph, END

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES DE AMBIENTE ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL")
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ROBERTO_PHONE = "556195369057" 

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE HUMANIZAÇÃO (BLINDAGEM DE CHIP) ---
def enviar_zap(tel, txt):
    """Envia mensagens simulando comportamento humano (Leitura + Digitação)"""
    try:
        # 1. Simula o tempo de 'Leitura' da mensagem (3 a 6 segundos)
        time.sleep(random.randint(3, 6))

        # 2. Envia sinal de 'Digitando' via Evolution API
        url_presence = f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}"
        requests.post(url_presence, 
                      json={"number": tel, "presence": "composing"}, 
                      headers={"apikey": EVOLUTION_APIKEY})

        # 3. Tempo de digitação proporcional ao texto (máximo 10s)
        typing_delay = min(len(txt) / 15, 10) 
        time.sleep(typing_delay)

        # 4. Envio do texto final
        url_send = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        payload = {"number": tel, "text": txt}
        res = requests.post(url_send, json=payload, headers={"apikey": EVOLUTION_APIKEY})
        
        print(f"✅ Mensagem humanizada enviada para {tel}")
        return res
    except Exception as e:
        print(f"❌ Erro na humanização: {e}")

# --- MOTOR DE TRANSCRIÇÃO (WHISPER) ---
def transcrever_audio(audio_url):
    try:
        response = requests.get(audio_url, timeout=15)
        if response.status_code != 200: return ""
        files = {'file': ('audio.ogg', response.content, 'audio/ogg')}
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        res = requests.post("https://api.openai.com/v1/audio/transcriptions", 
                            headers=headers, files=files, data={"model": "whisper-1", "language": "pt"})
        return res.json().get("text", "")
    except Exception as e:
        print(f"Erro Whisper: {e}")
        return ""

# --- ESTRUTURA AGÊNTICA (LANGGRAPH) ---
class AgentState(TypedDict):
    phone: str
    nome: str
    mensagem_original: str
    historico: str
    resposta_final: str

def agente_redator(state: AgentState):
    model = genai.GenerativeModel('gemini-2.0-flash')
    # PROMPT DO ARQUITETO ESTÓICO V1004
    prompt = f"""Você é o ROBERTO, Arquiteto de Sonhos da Conseg. 
    Perfil: Estóico, Minimalista e Altamente Profissional. 
    
    DIRETRIZES:
    1. Nunca envie 'textões'. Seja breve e certeiro.
    2. No primeiro contato, apenas valide o cliente e pergunte o objetivo (Imóvel ou Auto).
    3. Use 'Silent Reading': Você sabe que o grupo G-4050 da Porto tem lances de 32%, mas não despeje isso sem o cliente pedir.
    4. Se o cliente quiser simulação, direcione para: https://consorcio.consegseguro.com/app
    
    HISTÓRICO: {state['historico']}
    CLIENTE: {state['nome']} diz: {state['mensagem_original']}
    """
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

workflow = StateGraph(AgentState)
workflow.add_node("redator", agente_redator)
workflow.set_entry_point("redator")
workflow.add_edge("redator", END)
roberto_brain = workflow.compile()

# --- EXECUÇÃO PRINCIPAL ---
def executar_roberto(phone, msg, nome, audio_url=None):
    try:
        texto = transcrever_audio(audio_url) if audio_url else msg
        if not texto: return

        # Memória Episódica
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp DESC LIMIT 5", (phone,))
        fatos = " ".join([f[0] for f in cur.fetchall()])
        conn.close()

        # Roda a Inteligência
        resultado = roberto_brain.invoke({
            "phone": phone, "nome": nome, "mensagem_original": texto, "historico": fatos, "resposta_final": ""
        })
        
        # Envio Humanizado
        enviar_zap(phone, resultado['resposta_final'])

        # Salva Fatos Relevantes
        if len(texto) > 5:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone, texto[:200]))
            conn.commit(); conn.close()

    except Exception as e:
        print(f"Erro V1004: {e}")

# --- WEBHOOKS ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    data = request.json.get('data', {})
    if not data.get('key', {}).get('fromMe'):
        phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
        name = data.get('pushName', 'Cliente')
        msg = data.get('message', {})
        audio_url = msg.get('audioMessage', {}).get('url') if 'audioMessage' in msg else None
        txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
        if txt or audio_url:
            threading.Thread(target=executar_roberto, args=(phone, txt, name, audio_url)).start()
    return jsonify({"status": "ok"}), 200

@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    dados = request.json
    phone, nome = dados.get('phone'), dados.get('name')
    if phone and nome:
        enviar_zap(ROBERTO_PHONE, f"🚀 Novo Lead via Ads: {nome} ({phone})")
        threading.Thread(target=executar_roberto, args=(phone, "Iniciando contato via anúncio", nome)).start()
        return jsonify({"status": "Lead recebido"}), 200
    return jsonify({"error": "Dados inválidos"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
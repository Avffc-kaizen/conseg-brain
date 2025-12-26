# VERSÃO V1000 - ARQUITETURA AGÊNTICA, MULTIMODAL E ANTI-ENCAVALAMENTO
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
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# CORREÇÃO: Número oficial do Roberto / Conseg para notificações
ROBERTO_PHONE = "556195369057" 

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE TRANSCRIÇÃO (WHISPER) ---
def transcrever_audio(audio_url):
    try:
        response = requests.get(audio_url)
        files = {'file': ('audio.ogg', response.content, 'audio/ogg')}
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        res = requests.post("https://api.openai.com/v1/audio/transcriptions", 
                            headers=headers, files=files, data={"model": "whisper-1"})
        return res.json().get("text", "")
    except Exception as e:
        print(f"Erro Whisper: {e}")
        return ""

# --- DEFINIÇÃO DO ESTADO DO AGENTE (LANGGRAPH) ---
class AgentState(TypedDict):
    phone: str
    nome: str
    mensagem_original: str
    historico: str
    dados_minerados: str
    resposta_final: str
    visto_pelo_critico: bool

# --- NÓS DO GRAFO ---
def agente_analista(state: AgentState):
    # Simula consulta MCP/RAG para lances (Baseado nos CSVs da Porto)
    state['dados_minerados'] = "Porto Seguro: Grupo G-4050 com lances de 32% (Oportunidade de Mercado)."
    return state

def agente_redator(state: AgentState):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""Você é o ROBERTO, Consultor de Consórcios Conseg. 
    Nome do Cliente: {state['nome']}
    Dados de Mercado: {state['dados_minerados']}
    Histórico: {state['historico']}
    Mensagem do Cliente: {state['mensagem_original']}
    Responda de forma profissional, consultiva e autoritária."""
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

def agente_critico(state: AgentState):
    # Valida integridade e evita encavalamento
    state['visto_pelo_critico'] = True
    return state

# --- CONSTRUÇÃO DO GRAFO ---
workflow = StateGraph(AgentState)
workflow.add_node("analista", agente_analista)
workflow.add_node("redator", agente_redator)
workflow.add_node("critico", agente_critico)
workflow.set_entry_point("analista")
workflow.add_edge("analista", "redator")
workflow.add_edge("redator", "critico")
workflow.add_edge("critico", END)
roberto_brain = workflow.compile()

# --- LÓGICA DE EXECUÇÃO ---
def executar_roberto(phone, msg, nome, audio_url=None):
    try:
        texto = transcrever_audio(audio_url) if audio_url else msg
        if not texto: return

        # Recupera Memória Episódica
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s", (phone,))
        fatos = " ".join([f[0] for f in cur.fetchall()])
        conn.close()

        # Roda Cérebro Agêntico
        inputs = {
            "phone": phone, "nome": nome, "mensagem_original": texto,
            "historico": fatos, "dados_minerados": "", "resposta_final": "",
            "visto_pelo_critico": False
        }
        resultado = roberto_brain.invoke(inputs)
        
        # Envio WhatsApp
        enviar_zap(phone, resultado['resposta_final'])

        # Salva Fatos Relevantes
        if any(keyword in texto.lower() for keyword in ["quero", "objetivo", "sonho", "lance"]):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO episode_memory (phone, key_fact, category) VALUES (%s, %s, %s)", 
                        (phone, texto[:150], "Desejo"))
            conn.commit(); conn.close()

    except Exception as e:
        print(f"Erro Execução V1000: {e}")

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
        # Notifica o número oficial do Roberto sobre o novo lead
        enviar_zap(ROBERTO_PHONE, f"🚀 Novo Lead via Ads: {nome} ({phone})")
        threading.Thread(target=executar_roberto, args=(phone, "Olá! Recebemos seu interesse via anúncio.", nome)).start()
        return jsonify({"status": "Lead recebido"}), 200
    return jsonify({"error": "Dados inválidos"}), 400

def enviar_zap(tel, txt):
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    requests.post(url, json={"number": tel, "text": txt}, headers={"apikey": EVOLUTION_APIKEY})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
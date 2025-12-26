# VERSAO V78.1 - FOCO EM CONVERSÃO E FERRAMENTA DE CÁLCULO
import os
import requests
import datetime
import time
import threading
import json
import random
import re
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# --- LINKS ESTRATÉGICOS ---
LINK_FERRAMENTA = "https://consorcio.consegseguro.com/app"
LINK_AGENDA = "https://calendar.app.google/HxFwGyHA4zihQE27A"

# --- CONFIGURAÇÕES DE AMBIENTE ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL") 
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") 

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE RESPOSTA SUPREMO ---
SYSTEM_PROMPT = f"""
Você é o ROBERTO, Mentor de Crédito Sênior da ConsegSeguro.
Seu objetivo é guiar o cliente para a nossa ferramenta oficial de cálculo ou para a agenda.

ESTRUTURA DE RESPOSTA:
1. DIAGNÓSTICO: Entenda a dor do cliente (juros, prazo, FGTS).
2. ESTRATÉGIA: Explique a solução técnica. Se o cliente quer simulação, use: {LINK_FERRAMENTA}.
3. ORIENTAÇÃO: Direcione para a ação (Agendar ou Calcular).

MATERIAIS DE APOIO:
- Cite que você possui banners, vídeos e tabelas de grupos novos (ex: MAPFRE e PORTO) para auxiliar na decisão.
"""

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Recuperação de Memória (RAG)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 10", (phone,))
        historico = "".join([f"{r}: {c}\n" for r, c in reversed(cur.fetchall())])
        conn.close()

        chat = model.start_chat()
        prompt_completo = f"{SYSTEM_PROMPT}\n\nHISTÓRICO:\n{historico}\nCLIENTE: {msg_usuario}"
        response = chat.send_message(prompt_completo)
        texto_final = response.text.strip()

        # Humanização (Pausa antes de enviar)
        time.sleep((len(texto_final) / 45) + random.uniform(3, 5))

        # Envio WhatsApp
        url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        requests.post(url, json={"number": phone, "text": texto_final}, headers={"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"})
        
        # Persistência
        cx = get_db_connection(); cr = cx.cursor(); now = datetime.datetime.now()
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "user", msg_usuario, now))
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "model", texto_final, now))
        cx.commit(); cx.close()

    except Exception as e:
        print(f"Erro V78.1: {e}")

# --- ROTAS OPERACIONAIS ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    b = request.json
    if b.get('event') == 'messages.upsert':
        data = b.get('data', {})
        if not data.get('key', {}).get('fromMe'):
            phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
            name = data.get('pushName', 'Cliente')
            msg = data.get('message', {})
            txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
            if txt: threading.Thread(target=responder_chat_inteligente, args=(phone, txt, name)).start()
    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "ROBERTO V78.1 - FECHADOR DE PROPOSTAS ONLINE"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
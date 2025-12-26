# VERSAO V76.1 - INFRAESTRUTURA COMPLETA ATIVA
import os
import requests
import datetime
import time
import threading
import json
import random
import re
import psycopg2
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL") 
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") 
LINK_AGENDA = "https://calendar.app.google/HxFwGyHA4zihQE27A"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- ROTA DE DASHBOARD (A NOVIDADE) ---
@app.route('/relatorio', methods=['GET'])
def gerar_relatorio():
    """Gera uma visão simplificada da temperatura dos leads"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca leads e conta interações para definir temperatura
        cur.execute("""
            SELECT l.nome, l.phone, l.status, l.ofertou_agenda, 
            (SELECT COUNT(*) FROM messages m WHERE m.phone = l.phone) as total_msg
            FROM leads l 
            ORDER BY total_msg DESC LIMIT 50
        """)
        leads = cur.fetchall()
        conn.close()

        html = """
        <html>
        <head><title>Roberto BI - Inteligência de Vendas</title>
        <style>
            body { font-family: sans-serif; background: #f4f7f6; padding: 20px; }
            .card { background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #ccc; }
            .quente { border-left-color: #e74c3c; } /* Vermelho para Quente */
            .morno { border-left-color: #f1c40f; } /* Amarelo para Morno */
            .frio { border-left-color: #3498db; } /* Azul para Frio */
            .tag { font-size: 0.8em; padding: 3px 8px; border-radius: 4px; color: white; }
            .tag-agenda { background: #27ae60; }
        </style>
        </head>
        <body>
            <h1>🌡️ Temperatura dos Leads - Roberto V76</h1>
            {% for lead in leads %}
                <div class="card {% if lead[4] > 8 %}quente{% elif lead[4] > 3 %}morno{% else %}frio{% endif %}">
                    <strong>{{ lead[0] }}</strong> ({{ lead[1] }})<br>
                    Status: {{ lead[2] }} | Interações: {{ lead[4] }}
                    {% if lead[3] %}<span class="tag tag-agenda">Agenda Ofertada</span>{% endif %}
                </div>
            {% endfor %}
        </body>
        </html>
        """
        return render_template_string(html, leads=leads)
    except Exception as e:
        return str(e), 500

# --- MANTENDO O MOTOR SUPREMO ---
def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 10", (phone,))
        contexto_historico = "".join([f"{r}: {c}\n" for r, c in reversed(cur.fetchall())])
        conn.close()

        chat = model.start_chat()
        # Prompt focado em Arquiteto de Sonhos
        prompt = f"Você é o Roberto, Mentor Sênior. Use o Protocolo: Diagnóstico, Estratégia, Orientação. Link: {LINK_AGENDA}"
        response = chat.send_message(f"{prompt}\n\nHistórico:\n{contexto_historico}\nCliente: {msg_usuario}")
        texto_final = response.text.strip()

        # Delay e Envio
        time.sleep((len(texto_final) / 45) + random.uniform(3, 5))
        
        # Registro no banco
        cx = get_db_connection(); cr = cx.cursor(); now = datetime.datetime.now()
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "user", msg_usuario, now))
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "model", texto_final, now))
        cr.execute("UPDATE leads SET last_interaction = %s, ofertou_agenda = %s WHERE phone = %s", (now, LINK_AGENDA in texto_final, phone))
        cx.commit(); cx.close()

        # WhatsApp
        url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        requests.post(url, json={"number": phone, "text": texto_final}, headers={"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"})
    except: pass

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
    return jsonify({"status": "ROBERTO V76 - DASHBOARD BI ATIVO"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
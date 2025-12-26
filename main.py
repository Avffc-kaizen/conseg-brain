# VERSAO V79 - VARREDURA DE CRÉDITO E FECHAMENTO ESTRATÉGICO
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

# --- CONFIGURAÇÕES DE INFRAESTRUTURA ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL") 
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") 

# LINKS E CONTATOS
LINK_FERRAMENTA = "https://consorcio.consegseguro.com/app"
SEU_TELEFONE = "5561999949724" # Destino dos dados do fechamento

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE RESPOSTA: O PROTOCOLO DE VARREDURA ---
SYSTEM_PROMPT = f"""
VOCÊ É O ROBERTO: O Analista Supremo da ConsegSeguro.
Sua postura é de um Especialista em Alavancagem Patrimonial.

PROTOCOLO "VARREDURA DE CRÉDITO":
1. DIAGNÓSTICO: Identifique o valor e o objetivo do cliente.
2. AÇÃO DE VARREDURA: Simule que você está cruzando dados:
   - "Acesse a ferramenta de cálculo para grupos em andamento."
   - "Verifique as tabelas de grupos novos no Drive (MAPFRE/PORTO)."
   - "Compare com a taxa média de juros bancários atual (CET de ~12% a.a)."
3. ENTREGA DO RAIO-X: Apresente o resumo: Crédito, Parcela, Lance Recomendado e a Economia Real sobre o banco.
4. FECHAMENTO: Se o cliente aceitar, solicite os dados e informe que enviará para o setor de emissão.

LINK DA FERRAMENTA PARA CONSULTA: {LINK_FERRAMENTA}
"""

def enviar_zap(telefone, texto):
    clean_phone = "".join(filter(str.isdigit, str(telefone)))
    if len(clean_phone) == 12 and clean_phone.startswith("55"):
        clean_phone = f"{clean_phone[:4]}9{clean_phone[4:]}"
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
    requests.post(url, json={"number": clean_phone, "text": texto}, headers=headers)

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Recuperação de Contexto (RAG)
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 15", (phone,))
        historico = "".join([f"{r}: {c}\n" for r, c in reversed(cur.fetchall())])
        conn.close()

        chat = model.start_chat()
        prompt_final = f"{SYSTEM_PROMPT}\n\nHISTÓRICO:\n{historico}\nCLIENTE {nome_cliente}: {msg_usuario}\n\n(Importante: Demonstre que a varredura foi feita e use tons de fechamento)."
        response = chat.send_message(prompt_final)
        texto_final = response.text.strip()

        # Humanização
        time.sleep((len(texto_final) / 45) + random.uniform(4, 7))

        # LOGICA DE FECHAMENTO: Enviar para o SEU Telefone
        palavras_fechamento = ["fechar", "quero esse", "comprar", "aceito", "pode fazer"]
        if any(x in msg_usuario.lower() for x in palavras_fechamento):
            notificacao = (f"🚨 *NOVO FECHAMENTO - ROBERTO V79*\n\n"
                           f"Cliente: {nome_cliente}\n"
                           f"WhatsApp: {phone}\n"
                           f"Detalhes: O cliente aceitou a proposta após a varredura.\n\n"
                           f"📋 *DOCUMENTOS NECESSÁRIOS:* RG, CPF, Comprovante de Residência e Renda.")
            enviar_zap(SEU_TELEFONE, notificacao)

        # Envio para o Cliente
        enviar_zap(phone, texto_final)
        
        # Registro
        cx = get_db_connection(); cr = cx.cursor(); now = datetime.datetime.now()
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "user", msg_usuario, now))
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "model", texto_final, now))
        cx.commit(); cx.close()

    except Exception as e:
        print(f"Erro V79: {e}")

# --- ROTAS ---
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
    return jsonify({"status": "ROBERTO V79 - ANALISTA SUPREMO ATIVO"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
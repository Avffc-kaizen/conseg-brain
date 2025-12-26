# VERSÃO V1000 - ARQUITETURA AGÊNTICA MULTIMODAL
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

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES DE AMBIENTE ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL")
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Chave para o Whisper
DATABASE_URL = os.getenv("DATABASE_URL")
SEU_TELEFONE = "5561999949724"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE TRANSCRIÇÃO (WHISPER) ---
def transcrever_audio(audio_url):
    """Baixa o áudio da Evolution e transcreve via OpenAI Whisper"""
    try:
        # 1. Download do arquivo (Buffer em memória)
        response = requests.get(audio_url)
        files = {'file': ('audio.ogg', response.content, 'audio/ogg')}
        
        # 2. Envio para OpenAI
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        res = requests.post("https://api.openai.com/v1/audio/transcriptions", 
                            headers=headers, files=files, data={"model": "whisper-1"})
        return res.json().get("text", "")
    except Exception as e:
        print(f"Erro Whisper: {e}")
        return ""

# --- LÓGICA DE MEMÓRIA E SESSÃO ---
def recuperar_estado_sessao(phone):
    """Garante o isolamento de dados por cliente (Fim do encavalamento)"""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT state FROM sessions WHERE phone = %s", (phone,))
    result = cur.fetchone()
    if not result:
        cur.execute("INSERT INTO sessions (phone, state) VALUES (%s, %s)", (phone, json.dumps({})))
        conn.commit()
        return {}
    conn.close()
    return result[0]

# --- PROCESSAMENTO PRINCIPAL ---
def responder_v1000(phone, msg_origem, nome_cliente, audio_url=None):
    try:
        # Se houver áudio, transcreve primeiro
        texto_usuario = transcrever_audio(audio_url) if audio_url else msg_origem
        
        if not texto_usuario: return

        # Recupera memória episódica (Fatos do cliente)
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s", (phone,))
        fatos = " ".join([f[0] for f in cur.fetchall()])
        
        # Gerar resposta com Gemini (Usando RAG e Dados de Mineração)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"Você é o ROBERTO. Cliente: {nome_cliente}. Fatos conhecidos: {fatos}. Mensagem: {texto_usuario}"
        response = model.generate_content(prompt)
        texto_final = response.text.strip()

        # Enviar resposta (Pode ser estendido para ElevenLabs no futuro)
        enviar_zap(phone, texto_final)
        
        # Salva na memória episódica se detectar um fato relevante
        if "quero" in texto_usuario or "meu sonho" in texto_usuario:
            cur.execute("INSERT INTO episode_memory (phone, key_fact, category) VALUES (%s, %s, %s)", 
                        (phone, texto_usuario[:100], "Desejo"))
        
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Erro V1000: {e}")

# --- WEBHOOK ATUALIZADO ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    b = request.json
    if b.get('event') == 'messages.upsert':
        data = b.get('data', {})
        if not data.get('key', {}).get('fromMe'):
            phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
            name = data.get('pushName', 'Cliente')
            msg = data.get('message', {})
            
            # Identifica áudio ou texto
            audio_url = None
            if 'audioMessage' in msg:
                audio_url = msg['audioMessage'].get('url')
            
            txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
            
            if txt or audio_url:
                threading.Thread(target=responder_v1000, args=(phone, txt, name, audio_url)).start()
                
    return jsonify({"status": "ok"}), 200

def enviar_zap(tel, txt):
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    requests.post(url, json={"number": tel, "text": txt}, headers={"apikey": EVOLUTION_APIKEY})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
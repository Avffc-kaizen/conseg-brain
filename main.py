import os
import requests
import time
import threading
import random
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from typing import TypedDict
from langgraph.graph import StateGraph, END

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL")
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ANDRE_PESSOAL = "5561999949724"

# URLs
BANNER_DOSSIE = "https://consegseguro.com.br/wp-content/uploads/2024/dossie-pronto.png" 

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- FUNÇÕES AUXILIARES ---
def enviar_zap(tel, txt):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean
        
        tempo_digitacao = min(len(txt) / 15, 5) 
        time.sleep(random.randint(2, 4))
        
        requests.post(f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}", 
                      json={"number": tel_clean, "presence": "composing"}, 
                      headers={"apikey": EVOLUTION_APIKEY})
        
        time.sleep(tempo_digitacao)
        
        requests.post(f"{EVOLUTION_URL}/message/sendText/{INSTANCE}", 
                      json={"number": tel_clean, "text": txt}, 
                      headers={"apikey": EVOLUTION_APIKEY})
    except Exception as e: print(f"Erro zap: {e}")

def enviar_imagem(tel, image_url, legenda=""):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        requests.post(f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE}", 
                      json={"number": tel_clean, "media": image_url, "mediatype": "image", "caption": legenda}, 
                      headers={"apikey": EVOLUTION_APIKEY})
        time.sleep(2) 
    except: pass

def transcrever_audio_whisper(audio_url):
    try:
        audio_resp = requests.get(audio_url)
        filename = f"temp_{int(time.time())}.ogg"
        with open(filename, "wb") as f: f.write(audio_resp.content)
        with open(filename, "rb") as af:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            res = requests.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files={"file": af}, data={"model": "whisper-1", "language": "pt"})
        os.remove(filename)
        return res.json().get("text", "")
    except: return ""

# --- CÉREBRO V1019 (FAST TRACK - LEAD DO SITE) ---
def agente_redator(state):
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""Você é ROBERTO, Assistente Digital da Conseg.

    --- 🚨 DETECTOR DE LEAD DO SITE (CRÍTICO - LEIA ISTO) 🚨 ---
    Analise o HISTÓRICO e a MENSAGEM ATUAL.
    Se a mensagem contiver "DETALHES DA COTAÇÃO", "Vi a análise no site", ou dados técnicos como (Administradora, Valor da Carta, Parcela):
    
    1. 🚫 PROIBIDO PERGUNTAR O ÓBVIO: 
       - NÃO pergunte "Qual o valor?". (Está na mensagem!)
       - NÃO pergunte "Qual o objetivo?". (Está na mensagem!)
       - NÃO peça "Dados para simulação". (Já foi simulado!)

    2. ✅ AÇÃO "FAST TRACK" (FECHAMENTO):
       - Reconheça a proposta imediatamente: "Olá! Vi aqui sua simulação de [Valor] pela [Administradora]. Excelente escolha."
       - Se o cliente disser "Quero contratar", "Como funciona", ou "O que precisa":
         -> Vá direto para a DOCUMENTAÇÃO.
         -> Responda: "Para garantirmos essa condição, preciso emitir seu contrato. Pode me enviar foto do seu RG (ou CNH) e um Comprovante de Residência?"

    --- REGRAS GERAIS (Se NÃO for lead do site) ---
    - Filtro Kids: Se falar de Free Fire/Jogos -> Encerre ("Não atendemos").
    - Se for lead frio (apenas "Oi") -> Qualifique (Carro ou Imóvel?).
    - Identidade: Você é o Roberto, consultor digital.

    HISTÓRICO DA CONVERSA:
    {state['historico']}
    
    MENSAGEM ATUAL DO CLIENTE:
    "{state['mensagem_original']}"
    """
    
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

# --- EXECUTOR ---
def executar_roberto(phone, msg, nome, audio_url=None):
    phone_clean = ''.join(filter(str.isdigit, str(phone)))

    if phone_clean == ANDRE_PESSOAL and "/relatorio" in msg.lower():
        enviar_zap(ANDRE_PESSOAL, "📊 V1019: Modo Fast Track (Site) Ativo.")
        return

    # Processa Áudio
    texto_input = msg
    if audio_url:
        transcricao = transcrever_audio_whisper(audio_url)
        if transcricao: texto_input = f"[Áudio]: {transcricao}"
        else: return

    try:
        conn = get_db_connection(); cur = conn.cursor()
        # Aumentei o histórico para 8 mensagens para ele ler o "Textão" do site se estiver lá atrás
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp DESC LIMIT 8", (phone_clean,))
        rows = cur.fetchall()
        hist = " | ".join([r[0] for r in rows[::-1]])
        
        # Inteligência
        res = agente_redator({"nome": nome, "historico": hist, "mensagem_original": texto_input, "resposta_final": ""})
        resposta = res['resposta_final']

        # Envia imagem SÓ se for simulação NOVA gerada pelo ROBÔ (não a que veio do site)
        if "SIMULAÇÃO" in resposta and "DETALHES DA COTAÇÃO" not in hist:
            enviar_imagem(phone_clean, BANNER_DOSSIE)
        
        enviar_zap(phone_clean, resposta)

        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, f"Cliente: {texto_input}"))
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, f"Roberto: {resposta}"))
        conn.commit(); conn.close()
    except Exception as e: print(f"Erro: {e}")

@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    try:
        dados = request.get_json(force=True)
        if isinstance(dados, list): dados = dados[0]
        phone = ''.join(filter(str.isdigit, str(dados.get('phone') or dados.get('telefone'))))
        nome = (dados.get('name') or "Parceiro").split(' ')[0]

        def iniciar():
            # MODO AQUECIMENTO (Apenas "Oi")
            msg = f"Olá {nome}, tudo bem?"
            enviar_zap(phone, msg)
            
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone, f"Roberto: {msg}"))
            conn.commit(); conn.close()

        threading.Thread(target=iniciar).start()
        return jsonify({"status": "ok"}), 200
    except: return jsonify({"status": "erro"}), 400

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    data = request.json.get('data', {})
    if not data.get('key', {}).get('fromMe'):
        phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
        name = data.get('pushName', 'Cliente')
        msg = data.get('message', {})
        txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
        audio = msg.get('audioMessage', {}).get('url') or msg.get('voiceMessage', {}).get('url')
        
        if txt or audio:
            threading.Thread(target=executar_roberto, args=(phone, txt, name, audio)).start()
    return jsonify({"status": "ok"}), 200

@app.route('/')
def home(): return "Roberto V1019 - Fast Track Site", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
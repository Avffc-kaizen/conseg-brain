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

# Números de Controle
ROBERTO_NOTIFICA = "556195369057"  # Canal de alertas de novos leads
ANDRE_PESSOAL = "5561999949724"    # O Diretor (Relatórios e Fechamento)

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE HUMANIZAÇÃO (BLINDAGEM V1006) ---
def enviar_zap(tel, txt):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean

        # Delay de Leitura Humana
        time.sleep(random.randint(4, 8))

        # Status "Digitando..."
        url_presence = f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}"
        requests.post(url_presence, json={"number": tel_clean, "presence": "composing"}, headers={"apikey": EVOLUTION_APIKEY})

        # Tempo de digitação simulado
        time.sleep(min(len(txt) / 15, 10))

        # Envio da Mensagem
        url_send = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        res = requests.post(url_send, json={"number": tel_clean, "text": txt}, headers={"apikey": EVOLUTION_APIKEY})
        return res
    except Exception as e:
        print(f"Erro no envio: {e}")

# --- TRANSCRIÇÃO WHISPER (ÁUDIOS) ---
def transcrever_audio(audio_url):
    try:
        response = requests.get(audio_url, timeout=20)
        files = {'file': ('audio.ogg', response.content, 'audio/ogg')}
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        res = requests.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files=files, data={"model": "whisper-1", "language": "pt"})
        return res.json().get("text", "")
    except: return ""

# --- LÓGICA DE RELATÓRIO DO COMANDANTE ---
def gerar_relatorio_status():
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT phone) FROM episode_memory")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM episode_memory WHERE timestamp >= CURRENT_DATE")
        hoje = cur.fetchone()[0]
        conn.close()
        
        return (f"📊 *STATUS DA OPERAÇÃO CONSEG*\n\n"
                f"✅ Leads em Memória: {total}\n"
                f"🚀 Interações nas últimas 24h: {hoje}\n"
                f"🧠 Arquiteto Estóico: Online\n"
                f"🕒 Atualizado em: {datetime.datetime.now().strftime('%H:%M:%S')}")
    except: return "Erro ao processar base de dados."

# --- AGENTE ROBERTO V1006 (ESTRATÉGIA DE FECHAMENTO) ---
class AgentState(TypedDict):
    phone: str
    nome: str
    mensagem_original: str
    historico: str
    resposta_final: str

def agente_redator(state: AgentState):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""Você é o ROBERTO, Consultor de Elite da Conseg. 
    Seu objetivo é ser minimalista, estóico e conduzir o lead para o simulador.

    REGRAS DE OURO:
    1. Nunca use parágrafos longos. Seja direto.
    2. Direcionamento: Se o cliente quiser valores ou simulação, envie este link exato: https://consorcio.consegseguro.com/app
    3. Fechamento: Se o cliente escolheu um plano ou quer fechar, diga que o André (Diretor) já está ciente e peça para ele clicar no botão do WhatsApp no final do site ou chamar no +55 61 99994-9724.
    4. Memória: Use o histórico para mostrar que você lembra de detalhes anteriores.

    HISTÓRICO: {state['historico']}
    CLIENTE {state['nome']} DIZ: {state['mensagem_original']}"""
    
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

workflow = StateGraph(AgentState)
workflow.add_node("redator", agente_redator)
workflow.set_entry_point("redator")
workflow.add_edge("redator", END)
roberto_brain = workflow.compile()

# --- EXECUÇÃO ---
def executar_roberto(phone, msg, nome, audio_url=None):
    try:
        phone_clean = ''.join(filter(str.isdigit, str(phone)))
        
        # Reconhecimento do Chefe (André)
        if phone_clean == ANDRE_PESSOAL and msg.strip().lower() == "/relatorio":
            enviar_zap(ANDRE_PESSOAL, gerar_relatorio_status())
            return

        texto = transcrever_audio(audio_url) if audio_url else msg
        if not texto: return

        # Memória Infinita Neon
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp ASC", (phone_clean,))
        historico = " | ".join([f[0] for f in cur.fetchall()])
        
        # IA Decision Making
        res = roberto_brain.invoke({"phone": phone_clean, "nome": nome, "mensagem_original": texto, "historico": historico, "resposta_final": ""})
        
        # Envio e Registro
        enviar_zap(phone_clean, res['resposta_final'])
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, texto))
        conn.commit(); conn.close()
    except Exception as e: print(f"Erro crítico Roberto: {e}")

# --- WEBHOOKS ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    data = request.json.get('data', {})
    if not data.get('key', {}).get('fromMe'):
        phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
        name = data.get('pushName', 'Cliente')
        msg = data.get('message', {})
        txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
        audio = msg.get('audioMessage', {}).get('url')
        if txt or audio:
            threading.Thread(target=executar_roberto, args=(phone, txt, name, audio)).start()
    return jsonify({"status": "ok"}), 200

@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    try:
        dados = request.get_json(force=True)
        if isinstance(dados, list): dados = dados[0]
        phone = ''.join(filter(str.isdigit, str(dados.get('phone') or dados.get('telefone'))))
        nome = dados.get('name') or "Lead"
        
        # Notificação interna
        enviar_zap(ROBERTO_NOTIFICA, f"🚀 NOVO LEAD NA ESTEIRA: {nome} ({phone})")
        
        # Primeira abordagem
        threading.Thread(target=executar_roberto, args=(phone, f"Olá {nome}, vi que você tem interesse no consórcio da Conseg. Como posso ajudar?", nome)).start()
        return jsonify({"status": "sucesso"}), 200
    except: return jsonify({"status": "erro"}), 400

@app.route('/')
def home(): return "Roberto V1006 - Arquiteto Estóico Conseg Ativo", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
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
ROBERTO_NOTIFICA = "556195369057"
ANDRE_PESSOAL = "5561999949724"

# URLs de Banners (Substitua pelos links das suas imagens reais)
BANNER_IMOVEL = "https://seu-site.com.br/banners/imovel.png"
BANNER_VEICULO = "https://seu-site.com.br/banners/veiculo.png"
BANNER_GERAL = "https://seu-site.com.br/banners/investimento.png"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- MOTOR DE ENVIO (TEXTO E MÍDIA) ---
def enviar_zap(tel, txt):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean
        time.sleep(random.randint(4, 7))
        requests.post(f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}", 
                      json={"number": tel_clean, "presence": "composing"}, 
                      headers={"apikey": EVOLUTION_APIKEY})
        time.sleep(min(len(txt) / 15, 8))
        url_send = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        res = requests.post(url_send, json={"number": tel_clean, "text": txt}, headers={"apikey": EVOLUTION_APIKEY})
        return res
    except Exception as e:
        print(f"Erro envio texto: {e}")

def enviar_imagem(tel, image_url, legenda=""):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        url = f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE}"
        payload = {
            "number": tel_clean,
            "media": image_url,
            "mediatype": "image",
            "caption": legenda
        }
        res = requests.post(url, json=payload, headers={"apikey": EVOLUTION_APIKEY})
        print(f"📸 Banner enviado para {tel_clean}")
        return res
    except Exception as e:
        print(f"Erro envio imagem: {e}")

# --- TRANSCRIÇÃO WHISPER ---
def transcrever_audio(audio_url):
    try:
        response = requests.get(audio_url, timeout=20)
        files = {'file': ('audio.ogg', response.content, 'audio/ogg')}
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        res = requests.post("https://api.openai.com/v1/audio/transcriptions", 
                            headers=headers, files=files, data={"model": "whisper-1", "language": "pt"})
        return res.json().get("text", "")
    except: return ""

# --- AGENTE ROBERTO V1007 (O ESTRATEGISTA) ---
class AgentState(TypedDict):
    phone: str
    nome: str
    mensagem_original: str
    historico: str
    resposta_final: str

def agente_redator(state: AgentState):
    # Aqui ativamos o modelo com capacidade de busca (Search)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""Você é o ROBERTO, Consultor Estratégico da Conseg.
    Sua abordagem é EDUCATIVA e ESTÓICA. Você não é um vendedor comum, você é um mentor financeiro.

    DIRETRIZES:
    1. NÃO envie o link do simulador logo de cara. Primeiro gere valor.
    2. Use dados reais: Cite que o consórcio é a fuga inteligente dos juros bancários (Selic alta).
    3. Mencione que temos conteúdos exclusivos no blog que explicam como acelerar a contemplação.
    4. Se o cliente demonstrar interesse real, aí sim você sugere a simulação no site.
    5. Nunca use "textões". Seja curto e impactante.

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

# --- EXECUÇÃO CENTRAL ---
def executar_roberto(phone, msg, nome, audio_url=None):
    try:
        phone_clean = ''.join(filter(str.isdigit, str(phone)))
        
        # Comando de Relatório do Chefe
        if phone_clean == ANDRE_PESSOAL and msg.strip().lower() == "/relatorio":
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM episode_memory WHERE timestamp >= CURRENT_DATE")
            hoje = cur.fetchone()[0]
            conn.close()
            enviar_zap(ANDRE_PESSOAL, f"📊 Relatório Conseg: {hoje} interações hoje.")
            return

        texto = transcrever_audio(audio_url) if audio_url else msg
        if not texto: return

        # Memória Infinita
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp ASC", (phone_clean,))
        historico = " | ".join([f[0] for f in cur.fetchall()])
        
        # Inteligência
        res = roberto_brain.invoke({"phone": phone_clean, "nome": nome, "mensagem_original": texto, "historico": historico, "resposta_final": ""})
        
        # Envio e Registro
        enviar_zap(phone_clean, res['resposta_final'])
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, texto))
        conn.commit(); conn.close()
    except Exception as e: print(f"Erro Roberto: {e}")

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
        interesse = str(dados.get('ad_name', '')).lower()

        # Define qual banner enviar com base no interesse
        banner = BANNER_GERAL
        if "imovel" in interesse: banner = BANNER_IMOVEL
        elif "veiculo" in interesse or "carro" in interesse: banner = BANNER_VEICULO

        # 1. Envia Banner de Boas-vindas
        enviar_imagem(phone, banner, f"Olá {nome}, bem-vindo à Conseg!")
        
        # 2. Inicia Prospecção Consultiva (Sem link inicial)
        threading.Thread(target=executar_roberto, args=(phone, f"Vi que você tem interesse em {interesse}. O que você está buscando conquistar exatamente?", nome)).start()
        
        return jsonify({"status": "ok"}), 200
    except: return jsonify({"status": "erro"}), 400

@app.route('/')
def home(): return "Roberto V1007 - Estrategista de Conteúdo Ativo", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
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

# --- VARIÁVEIS DE AMBIENTE (Configuradas no Render) ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL")
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ROBERTO_PHONE = "556195369057" # Seu WhatsApp de alerta

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- SISTEMA DE HUMANIZAÇÃO E PROTEÇÃO DE CHIP (V1004/1005) ---
def enviar_zap(tel, txt):
    """Envia mensagens simulando comportamento humano real"""
    try:
        # Garante telefone limpo (somente números)
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean

        # 1. Delay de Leitura (3 a 7 seg)
        time.sleep(random.randint(3, 7))

        # 2. Ativa "Digitando..." na API
        url_presence = f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}"
        requests.post(url_presence, 
                      json={"number": tel_clean, "presence": "composing"}, 
                      headers={"apikey": EVOLUTION_APIKEY})

        # 3. Delay de Digitação proporcional (15 caracteres por segundo)
        typing_time = min(len(txt) / 15, 12)
        time.sleep(typing_time)

        # 4. Envio efetivo
        url_send = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        payload = {"number": tel_clean, "text": txt}
        res = requests.post(url_send, json=payload, headers={"apikey": EVOLUTION_APIKEY})
        
        print(f"✅ Roberto respondeu para {tel_clean}")
        return res
    except Exception as e:
        print(f"❌ Erro no envio humanizado: {e}")

# --- TRANSCRIÇÃO DE ÁUDIO (WHISPER) ---
def transcrever_audio(audio_url):
    try:
        response = requests.get(audio_url, timeout=20)
        if response.status_code != 200: return ""
        files = {'file': ('audio.ogg', response.content, 'audio/ogg')}
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        res = requests.post("https://api.openai.com/v1/audio/transcriptions", 
                            headers=headers, files=files, data={"model": "whisper-1", "language": "pt"})
        return res.json().get("text", "")
    except Exception as e:
        print(f"⚠️ Erro Whisper: {e}")
        return ""

# --- LÓGICA AGÊNTICA (LANGGRAPH) ---
class AgentState(TypedDict):
    phone: str
    nome: str
    mensagem_original: str
    historico: str
    resposta_final: str

def agente_redator(state: AgentState):
    model = genai.GenerativeModel('gemini-2.0-flash')
    # PROMPT SUPREMO V1005 - ESTÓICO E COM MEMÓRIA TOTAL
    prompt = f"""Você é o ROBERTO, Consultor Estratégico da Conseg.
    Sua missão é ser um Arquiteto de Sonhos através do consórcio.

    COMPORTAMENTO:
    - Persona: Estóico, minimalista, educado e altamente profissional.
    - Regra: Nunca mande mensagens longas (textões).
    - Memória: Você tem acesso a todo o histórico abaixo. Se o cliente já disse algo antes, use isso a seu favor para não ser repetitivo.
    - Call to Action: Para simulações detalhadas, direcione para: https://consorcio.consegseguro.com/app

    HISTÓRICO COMPLETO DA CONVERSA (MEMÓRIA INFINITA):
    {state['historico']}

    CLIENTE {state['nome']} DIZ AGORA: {state['mensagem_original']}
    """
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

workflow = StateGraph(AgentState)
workflow.add_node("redator", agente_redator)
workflow.set_entry_point("redator")
workflow.add_edge("redator", END)
roberto_brain = workflow.compile()

# --- FUNÇÃO CENTRAL DE EXECUÇÃO ---
def executar_roberto(phone, msg, nome, audio_url=None):
    try:
        phone_clean = ''.join(filter(str.isdigit, str(phone)))
        
        # 1. Transcrição se for áudio
        texto_usuario = transcrever_audio(audio_url) if audio_url else msg
        if not texto_usuario: return

        # 2. Busca Memória Infinita no Neon
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp ASC", (phone_clean,))
        historico_completo = " | ".join([f[0] for f in cur.fetchall()])
        conn.close()

        # 3. Gera Resposta com Gemini 2.0
        resultado = roberto_brain.invoke({
            "phone": phone_clean, 
            "nome": nome, 
            "mensagem_original": texto_usuario, 
            "historico": historico_completo, 
            "resposta_final": ""
        })
        
        # 4. Envio com Blindagem
        enviar_zap(phone_clean, resultado['resposta_final'])

        # 5. Salva na Memória
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, texto_usuario))
        conn.commit(); conn.close()

    except Exception as e:
        print(f"❌ Falha crítica Roberto V1005: {e}")

# --- ROTAS (WEBHOOKS) ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    try:
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
    except:
        return jsonify({"status": "error"}), 500

@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    try:
        dados = request.get_json(force=True)
        if isinstance(dados, list): dados = dados[0]
            
        phone = dados.get('phone') or dados.get('telefone')
        nome = dados.get('name') or dados.get('nome') or "Lead"
        
        if not phone: return jsonify({"error": "Sem telefone"}), 400
        phone_clean = ''.join(filter(str.isdigit, str(phone)))

        # Alerta para o consultor
        enviar_zap(ROBERTO_PHONE, f"🚀 NOVO LEAD ADS: {nome} ({phone_clean})")
        
        # Abordagem automática do Roberto
        threading.Thread(target=executar_roberto, args=(phone_clean, f"Olá {nome}, vi seu interesse no consórcio da Conseg!", nome)).start()
        
        return jsonify({"status": "Lead processado"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "Roberto V1005 (Conseg) Online - Memória Infinita Ativada", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
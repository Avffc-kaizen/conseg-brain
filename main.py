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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Essencial para o áudio
DATABASE_URL = os.getenv("DATABASE_URL")
ANDRE_PESSOAL = "5561999949724"

# URLs
BANNER_BOAS_VINDAS = "https://consegseguro.com.br/wp-content/uploads/2024/banner-investimento.jpg"
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

# --- TRANSCRIÇÃO DE ÁUDIO (WHISPER) ---
def transcrever_audio_whisper(audio_url):
    try:
        print(f"🎤 Baixando áudio: {audio_url}")
        audio_resp = requests.get(audio_url)
        
        # Salva temporariamente
        filename = f"temp_audio_{int(time.time())}.ogg"
        with open(filename, "wb") as f:
            f.write(audio_resp.content)
            
        # Envia para OpenAI
        with open(filename, "rb") as audio_file:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            data = {"model": "whisper-1", "language": "pt"}
            files = {"file": audio_file}
            
            response = requests.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files=files, data=data)
        
        os.remove(filename) # Limpa arquivo
        
        if response.status_code == 200:
            texto = response.json().get("text", "")
            print(f"📝 Transcrição: {texto}")
            return texto
        else:
            print(f"❌ Erro OpenAI: {response.text}")
            return ""
    except Exception as e:
        print(f"❌ Erro Transcrição: {e}")
        return ""

# --- CÉREBRO V1016 ---
def agente_redator(state):
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""Você é ROBERTO, consultor da Conseg.
    O cliente acabou de enviar esta mensagem: "{state['mensagem_original']}"

    --- REGRAS DE NEGÓCIO ---
    1. SERVIÇOS (5k a 30k): Se o valor for baixo, assuma CONSÓRCIO DE SERVIÇOS (Cirurgia, Viagem, Reforma).
       - Prazo: 36 a 48 meses.
    2. CARROS (30k a 100k): Prazo 80 meses.
    3. IMÓVEIS (+100k): Prazo 180 meses.
    4. EMPRÉSTIMO: Se pedirem empréstimo, explique que Consórcio é planejamento sem juros.

    --- SE FOR ÁUDIO ---
    O texto acima é a transcrição do áudio do cliente. Responda com naturalidade, como se tivesse ouvido.
    "Ouvi seu áudio aqui..." ou "Entendi o que você disse sobre..."

    HISTÓRICO: {state['historico']}
    """
    
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

# --- EXECUTOR ---
def executar_roberto(phone, msg, nome, audio_url=None):
    phone_clean = ''.join(filter(str.isdigit, str(phone)))

    # 1. BLOCO DE COMANDO DE CHEFE (PRIORIDADE MÁXIMA - SEM IA)
    if phone_clean == ANDRE_PESSOAL and "/relatorio" in msg.lower():
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(DISTINCT phone) FROM episode_memory")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM episode_memory WHERE timestamp >= CURRENT_DATE")
            hoje = cur.fetchone()[0]
            conn.close()
            
            relatorio = (f"📊 *STATUS V1016*\n"
                         f"✅ Base Total: {total}\n"
                         f"🗣️ Interações Hoje: {hoje}\n"
                         f"🎧 Módulo de Áudio: Ativo")
            enviar_zap(ANDRE_PESSOAL, relatorio)
            return
        except: 
            enviar_zap(ANDRE_PESSOAL, "Erro ao puxar dados do banco.")
            return

    # 2. PROCESSAMENTO DE ÁUDIO
    texto_final = msg
    if audio_url:
        transcricao = transcrever_audio_whisper(audio_url)
        if transcricao:
            texto_final = f"[ÁUDIO DO CLIENTE]: {transcricao}"
            # Avisa que está ouvindo (Opcional)
            requests.post(f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}", 
                          json={"number": phone_clean, "presence": "recording"}, 
                          headers={"apikey": EVOLUTION_APIKEY})
        else:
            enviar_zap(phone_clean, "Tive um problema para ouvir seu áudio. Pode escrever?")
            return

    # 3. INTELIGÊNCIA
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp DESC LIMIT 6", (phone_clean,))
        rows = cur.fetchall()
        hist = " | ".join([r[0] for r in rows[::-1]])
        
        res = agente_redator({"nome": nome, "historico": hist, "mensagem_original": texto_final, "resposta_final": ""})
        resposta_ia = res['resposta_final']

        if "SIMULAÇÃO" in resposta_ia:
            enviar_imagem(phone_clean, BANNER_DOSSIE)
        
        enviar_zap(phone_clean, resposta_ia)

        # Salva
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, f"Cliente: {texto_final}"))
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, f"Roberto: {resposta_ia}"))
        conn.commit(); conn.close()
    except Exception as e: print(f"Erro: {e}")

# --- WEBHOOKS ---
@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    try:
        dados = request.get_json(force=True)
        if isinstance(dados, list): dados = dados[0]
        phone = ''.join(filter(str.isdigit, str(dados.get('phone') or dados.get('telefone'))))
        nome = (dados.get('name') or "Parceiro").split(' ')[0]

        def iniciar():
            enviar_imagem(phone, BANNER_BOAS_VINDAS)
            time.sleep(3)
            msg = (f"Olá {nome}, tudo bem? Sou Roberto da Conseg. 👋\n\n"
                   f"Recebi seu cadastro. Para eu te ajudar: seu foco é **Carro**, **Imóvel** ou **Serviços** (Cirurgia/Reforma)?")
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
        
        # Extração de Texto ou Áudio
        txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
        audio_url = msg.get('audioMessage', {}).get('url') or msg.get('voiceMessage', {}).get('url') # Suporte a Voice Message
        
        if txt or audio_url:
            threading.Thread(target=executar_roberto, args=(phone, txt, name, audio_url)).start()
            
    return jsonify({"status": "ok"}), 200

@app.route('/')
def home(): return "Roberto V1016 - Ouvindo Tudo", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
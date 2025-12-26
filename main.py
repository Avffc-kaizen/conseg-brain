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

# --- CONFIGURAÇÕES ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL")
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ANDRE_PESSOAL = "5561999949724"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- FUNÇÕES DE ENVIO ---
def enviar_zap(tel, txt):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean
        
        # Simulação humana
        time.sleep(random.randint(2, 5))
        url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
        payload = {"number": tel_clean, "text": txt, "delay": 1200}
        requests.post(url, json=payload, headers=headers)
    except Exception as e: print(f"Erro envio texto: {e}")

def enviar_imagem(tel, image_url, legenda=""):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        url = f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE}"
        headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
        payload = {
            "number": tel_clean,
            "media": image_url,
            "mediatype": "image",
            "caption": legenda
        }
        res = requests.post(url, json=payload, headers=headers)
        return res
    except Exception as e: print(f"Erro imagem: {e}")

# --- IA DO ROBERTO ---
def agente_redator(state):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""Você é o ROBERTO, consultor da Conseg. 
    Linguagem: Brasileira, amigável, consultiva.
    Foco: Ajudar o cliente a planejar 2026 (Carro/Casa) sem juros.
    Histórico: {state['historico']}
    Mensagem do Cliente: {state['mensagem_original']}"""
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

# --- PROCESSAMENTO PRINCIPAL ---
def executar_roberto(phone, msg, nome):
    phone_clean = ''.join(filter(str.isdigit, str(phone)))
    
    # 1. BLOCO DE COMANDO DO CHEFE (PRIORIDADE TOTAL)
    if phone_clean == ANDRE_PESSOAL and "/relatorio" in msg.lower():
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM episode_memory WHERE timestamp >= CURRENT_DATE")
            hoje = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT phone) FROM episode_memory")
            total = cur.fetchone()[0]
            conn.close()
            
            relatorio = (f"📊 *RELATÓRIO DE OPERAÇÃO*\n\n"
                         f"✅ Total na Base: {total}\n"
                         f"🚀 Atendimentos Hoje: {hoje}\n"
                         f"🤖 Status: Roberto V1009 Online")
            enviar_zap(ANDRE_PESSOAL, relatorio)
            return
        except:
            enviar_zap(ANDRE_PESSOAL, "Erro ao acessar banco de dados.")
            return

    # 2. SE FOR O CHEFE FALANDO OUTRA COISA, NÃO RESPONDE (Evita loops)
    if phone_clean == ANDRE_PESSOAL: return

    # 3. LÓGICA PARA CLIENTES
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp ASC LIMIT 5", (phone_clean,))
        hist = " | ".join([f[0] for f in cur.fetchall()])
        
        # Chama IA
        res = agente_redator({"nome": nome, "historico": hist, "mensagem_original": msg, "resposta_final": ""})
        
        enviar_zap(phone_clean, res['resposta_final'])
        
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, msg))
        conn.commit(); conn.close()
    except Exception as e: print(f"Erro: {e}")

# --- WEBHOOKS ---
@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    dados = request.get_json(force=True)
    if isinstance(dados, list): dados = dados[0]
    
    phone = ''.join(filter(str.isdigit, str(dados.get('phone') or dados.get('telefone'))))
    nome = (dados.get('name') or "amigo").split(' ')[0]

    # LINK DO BANNER (Certifique-se que este link abre direto uma imagem)
    banner = "https://consegseguro.com.br/wp-content/uploads/2024/banner-investimento.jpg"
    
    # DISPARO EM SEQUÊNCIA
    def disparar_inicial():
        enviar_imagem(phone, banner)
        time.sleep(5)
        msg_inicial = (f"Olá {nome}! Tudo bem? 👋\n\n"
                       f"Vi seu interesse no consórcio da Conseg. Qual tipo de sonho você pretende realizar em 2026? O carro, a casa ou outro objetivo?\n\n"
                       f"Estou aqui para te ajudar na rota correta sem juros. 😊")
        enviar_zap(phone, msg_inicial)
    
    threading.Thread(target=disparar_inicial).start()
    return jsonify({"status": "ok"}), 200

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    data = request.json.get('data', {})
    if not data.get('key', {}).get('fromMe'):
        phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
        name = data.get('pushName', 'Cliente')
        msg = data.get('message', {})
        txt = msg.get('conversation') or msg.get('extendedTextMessage',{}).get('text')
        if txt:
            threading.Thread(target=executar_roberto, args=(phone, txt, name)).start()
    return jsonify({"status": "ok"}), 200

@app.route('/')
def home(): return "Roberto V1009 Ativo", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
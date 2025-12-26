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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
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
        # Delay humano natural
        time.sleep(random.randint(3, 6))
        requests.post(f"{EVOLUTION_URL}/chat/chatPresence/{INSTANCE}", 
                      json={"number": tel_clean, "presence": "composing"}, 
                      headers={"apikey": EVOLUTION_APIKEY})
        time.sleep(min(len(txt) / 15, 6))
        requests.post(f"{EVOLUTION_URL}/message/sendText/{INSTANCE}", 
                      json={"number": tel_clean, "text": txt}, 
                      headers={"apikey": EVOLUTION_APIKEY})
    except Exception as e: print(f"Erro envio: {e}")

def enviar_imagem(tel, image_url, legenda=""):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        requests.post(f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE}", 
                      json={"number": tel_clean, "media": image_url, "mediatype": "image", "caption": legenda}, 
                      headers={"apikey": EVOLUTION_APIKEY})
    except: pass

# --- CÉREBRO DO ROBERTO V1008 ---
def agente_redator(state):
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', tools=[{"google_search_retrieval": {}}])
    
    prompt = f"""Você é o ROBERTO, consultor da Conseg. Sua comunicação é tipicamente brasileira: amigável, prestativa e sem "robotez".
    
    REGRAS DE OURO:
    1. FOCO EM 2026: Ajude o cliente a planejar a casa ou o carro para o ano que vem.
    2. CONSULTORIA: Explique por que o consórcio é a rota financeira correta (sem juros abusivos).
    3. SIMPLICIDADE: Se o cliente responder, tire as dúvidas de forma simples. Use dados do Google Search se ele perguntar de taxas ou Selic.
    4. NÃO PRESSIONE: O objetivo é ser um parceiro na conquista.

    HISTÓRICO: {state['historico']}
    CLIENTE {state['nome']} DISSE: {state['mensagem_original']}"""
    
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

# --- WEBHOOK DE LEADS (DISPARO INICIAL) ---
@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    try:
        dados = request.get_json(force=True)
        if isinstance(dados, list): dados = dados[0]
        phone = ''.join(filter(str.isdigit, str(dados.get('phone') or dados.get('telefone'))))
        nome = dados.get('name', 'amigo(a)').split(' ')[0] # Pega só o primeiro nome

        banner_url = "https://consegseguro.com.br/wp-content/uploads/2024/banner-investimento.jpg"
        
        # 1. Envia a Imagem Aspiracional
        enviar_imagem(phone, banner_url)
        
        # 2. Abordagem Humana e Simples
        msg_inicial = (
            f"Olá {nome}! Tudo bem? 👋\n\n"
            f"Vi que você preencheu um cadastro interessado em consórcio conosco.\n\n"
            f"Qual tipo de sonho você pretende realizar em 2026? O carro, a casa ou outro objetivo?\n\n"
            f"Estou aqui para tirar suas dúvidas e te ajudar a encontrar a rota financeiramente mais viável para você conquistar isso sem juros abusivos. 😊"
        )
        
        threading.Thread(target=enviar_zap, args=(phone, msg_inicial)).start()
        return jsonify({"status": "ok"}), 200
    except: return jsonify({"status": "erro"}), 400

# --- CONTINUAÇÃO DO CHAT ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    data = request.json.get('data', {})
    if not data.get('key', {}).get('fromMe'):
        phone = data.get('key', {}).get('remoteJid', '').split('@')[0]
        name = data.get('pushName', 'Cliente')
        txt = data.get('message', {}).get('conversation') or data.get('message', {}).get('extendedTextMessage',{}).get('text')
        
        if txt:
            # Lógica de resposta via Roberto IA
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp ASC", (phone,))
            hist = " | ".join([f[0] for f in cur.fetchall()])
            
            # Aqui rodaria a IA (agente_redator)...
            # (Simplificado para o post)
            threading.Thread(target=enviar_zap, args=(phone, "Entendi! Vamos conversar sobre isso. O que mais te preocupa hoje no financiamento?")).start()
            
            cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone, txt))
            conn.commit(); conn.close()
    return jsonify({"status": "ok"}), 200

@app.route('/')
def home(): return "Roberto V1008 Ativo", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
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
DATABASE_URL = os.getenv("DATABASE_URL")
ANDRE_PESSOAL = "5561999949724"

# URL DO BANNER BOAS VINDAS
BANNER_BOAS_VINDAS = "https://consegseguro.com.br/wp-content/uploads/2024/banner-investimento.jpg"
BANNER_DOSSIE = "https://consegseguro.com.br/wp-content/uploads/2024/dossie-pronto.png"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- FUNÇÕES DE ENVIO ---
def enviar_zap(tel, txt):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean
        
        # Delay humano dinâmico
        tempo_digitacao = min(len(txt) / 12, 5) 
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

# --- CÉREBRO CONTEXTUAL V1013 ---
def agente_redator(state):
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""Você é ROBERTO, consultor da Conseg. 
    Seu tom é: Brasileiro, Profissional, Humano e Seguro.

    --- REGRAS DE CONTEXTO (CRÍTICO) ---
    1. LEIA O HISTÓRICO: Se o cliente fizer uma pergunta (ex: "Onde pegou meu número?", "Quem é você?"), RESPONDA A PERGUNTA PRIMEIRO. Não ignore.
    2. LGPD: Se perguntarem a origem do contato, diga: "Recebemos seu registro de interesse em consórcios através dos nossos anúncios online."
    3. ANTI-LOOP: Se você já saudou, NÃO diga "Olá" de novo. Continue o assunto.
    4. NÃO SEJA ROBÔ: Não use listas (1, 2, 3). Converse como no WhatsApp. Uma pergunta por vez.

    --- MODO MATEMÁTICO (PROPOSTA) ---
    Se o cliente falar um VALOR (ex: "20 mil", "30k"), gere a proposta IMEDIATAMENTE:
    
    LAYOUT:
    Andre (ou nome), simulação rápida pro seu perfil:

    📋 *PROPOSTA OFICIAL CONSEG*
    
    🎯 *Crédito:* R$ [Valor]
    ⏳ *Prazo:* [Prazo] meses

    📉 *No Consórcio:* R$ [Valor Parcela]/mês
    📈 *No Financiamento:* ~R$ [Valor Alto]/mês

    💰 *Economia:* R$ [Valor Economia]

    Faz sentido reservar essa carta?
    --------------------------------

    HISTÓRICO DA CONVERSA:
    {state['historico']}
    
    MENSAGEM ATUAL DO CLIENTE:
    "{state['mensagem_original']}"
    """
    
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

# --- EXECUTOR ---
def executar_roberto(phone, msg, nome):
    phone_clean = ''.join(filter(str.isdigit, str(phone)))

    if phone_clean == ANDRE_PESSOAL and "/relatorio" in msg.lower():
        enviar_zap(ANDRE_PESSOAL, "📊 V1013 Online: Inteligência de Contexto Ativa.")
        return

    try:
        # Busca histórico (Aumentei para 6 para ele ter mais contexto e não repetir)
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp DESC LIMIT 6", (phone_clean,))
        rows = cur.fetchall()
        # Inverte para ordem cronológica (Antigo -> Novo) para a IA entender o fluxo
        hist = " | ".join([r[0] for r in rows[::-1]])
        
        # Inteligência
        res = agente_redator({"nome": nome, "historico": hist, "mensagem_original": msg, "resposta_final": ""})
        texto_final = res['resposta_final']

        # Envia Dossiê se for proposta
        if "PROPOSTA OFICIAL" in texto_final:
            enviar_imagem(phone_clean, BANNER_DOSSIE)
        
        enviar_zap(phone_clean, texto_final)

        # Salva formatado: "Cliente: msg" e "Roberto: resposta" para ajudar o contexto na próxima
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, f"Cliente: {msg}"))
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, f"Roberto: {texto_final}"))
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
            # 1. Envia Imagem
            enviar_imagem(phone, BANNER_BOAS_VINDAS)
            time.sleep(3)
            
            # 2. Abordagem LGPD + Qualificação (Sem ser invasivo)
            msg = (f"Olá {nome}, tudo bem? Sou Roberto da Conseg. 👋\n\n"
                   f"Recebi seu contato através do nosso cadastro de interesse em consórcios.\n"
                   f"Pra eu te direcionar certo: seu foco hoje é **Carro** ou **Imóvel**?")
            enviar_zap(phone, msg)
            
            # Registra o início para a IA não repetir "Olá" depois
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
        txt = data.get('message', {}).get('conversation') or data.get('message', {}).get('extendedTextMessage',{}).get('text')
        
        if txt:
            threading.Thread(target=executar_roberto, args=(phone, txt, name)).start()
    return jsonify({"status": "ok"}), 200

@app.route('/')
def home(): return "Roberto V1013 - Contexto & LGPD Ativos", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
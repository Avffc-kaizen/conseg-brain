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

# URLs DE IMAGENS (Substitua pelos seus links reais)
BANNER_BOAS_VINDAS = "https://consegseguro.com.br/wp-content/uploads/2024/banner-investimento.jpg"
BANNER_DOSSIE = "https://consegseguro.com.br/wp-content/uploads/2024/dossie-pronto.png" 

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- FUNÇÕES DE ENVIO (Humanizadas) ---
def enviar_zap(tel, txt):
    try:
        tel_clean = ''.join(filter(str.isdigit, str(tel)))
        if not tel_clean.startswith('55'): tel_clean = '55' + tel_clean
        
        # Delay para parecer que está digitando/pensando
        tempo_digitacao = min(len(txt) / 20, 5) 
        time.sleep(random.randint(2, 4))
        
        # Marca como "digitando..."
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
        # Delay pequeno para a imagem carregar antes do texto
        requests.post(f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE}", 
                      json={"number": tel_clean, "media": image_url, "mediatype": "image", "caption": legenda}, 
                      headers={"apikey": EVOLUTION_APIKEY})
        time.sleep(2) 
    except: pass

# --- CÉREBRO DO ROBERTO V1011 (Matemático e Brasileiro) ---
def agente_redator(state):
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""Você é o ROBERTO, Consultor Sênior da Conseg.
    Sua comunicação é: Humana, Especialista e Direta (estilo WhatsApp brasileiro).

    MISSÃO CRÍTICA:
    Se o cliente mencionar um valor (ex: "20 mil", "250k", "quero 50.000"), você NÃO DEVE mandar para o site.
    Você deve CALCULAR e apresentar a PROPOSTA OFICIAL imediatamente no chat.

    --- FÓRMULA DE CÁLCULO MENTAL ---
    1. Prazo Padrão: 80 meses (Carros) ou 180 meses (Imóveis/Altos valores).
    2. Parcela Consórcio = (Valor Crédito / Prazo) * 1.22 (Taxa Adm diluída).
    3. Parcela Financiamento = Parcela Consórcio * 1.9 (Juros bancários abusivos).
    4. Economia = (Parcela Financiamento - Parcela Consórcio) * Prazo.

    --- TEMPLATE OBRIGATÓRIO (Use este layout exato) ---
    Andre (ou nome do cliente), preparei uma simulação oficial para seu perfil:

    📋 *PROPOSTA OFICIAL CONSEG*
    
    🎯 *Crédito:* R$ [Valor Formatado]
    ⏳ *Prazo:* [Prazo] meses

    📉 *No Consórcio:* R$ [Valor Parcela]/mês
    📈 *No Financiamento:* ~R$ [Valor Alto]/mês (Banco)

    💰 *Economia estimada:* R$ [Valor Economia]

    Considerando seu perfil, essa é a rota mais inteligente para não rasgar dinheiro com juros.
    
    Faz sentido reservar essa carta agora?
    --------------------------------------

    SE NÃO TIVER VALOR DEFINIDO:
    Apenas qualifique o cliente. Pergunte o que ele busca (Imóvel, Carro, Investimento) e o prazo que ele imagina. Seja curto.

    HISTÓRICO: {state['historico']}
    CLIENTE {state['nome']} DISSE: {state['mensagem_original']}"""
    
    response = model.generate_content(prompt)
    state['resposta_final'] = response.text.strip()
    return state

# --- EXECUTOR ---
def executar_roberto(phone, msg, nome):
    phone_clean = ''.join(filter(str.isdigit, str(phone)))

    # 1. COMANDO DO CHEFE (Relatório Rápido)
    if phone_clean == ANDRE_PESSOAL and "/relatorio" in msg.lower():
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM episode_memory WHERE timestamp >= CURRENT_DATE")
            hoje = cur.fetchone()[0]
            conn.close()
            enviar_zap(ANDRE_PESSOAL, f"📊 *Resumo Rápido:*\n{hoje} atendimentos hoje.\nO sistema está calculando propostas automaticamente.")
        except: pass
        return

    # 2. ATENDIMENTO AO CLIENTE
    try:
        # Busca memória
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT key_fact FROM episode_memory WHERE phone = %s ORDER BY timestamp DESC LIMIT 4", (phone_clean,))
        hist = " | ".join([f[0] for f in cur.fetchall()])
        
        # Roda a IA
        res = agente_redator({"nome": nome, "historico": hist, "mensagem_original": msg, "resposta_final": ""})
        texto_final = res['resposta_final']

        # 3. GATILHO VISUAL (Se gerou proposta, manda a imagem do Dossiê antes)
        if "PROPOSTA OFICIAL" in texto_final or "Crédito:" in texto_final:
            enviar_imagem(phone_clean, BANNER_DOSSIE)
        
        # Envia Texto
        enviar_zap(phone_clean, texto_final)

        # Salva Memória
        cur.execute("INSERT INTO episode_memory (phone, key_fact) VALUES (%s, %s)", (phone_clean, msg))
        conn.commit(); conn.close()
    except Exception as e: print(f"Erro no fluxo: {e}")

# --- WEBHOOKS ---
@app.route('/webhook/ads', methods=['POST'])
def webhook_ads():
    try:
        dados = request.get_json(force=True)
        if isinstance(dados, list): dados = dados[0]
        phone = ''.join(filter(str.isdigit, str(dados.get('phone') or dados.get('telefone'))))
        nome = (dados.get('name') or "Parceiro").split(' ')[0]

        # Lógica de Entrada (Simples e Direta)
        def iniciar():
            enviar_imagem(phone, BANNER_BOAS_VINDAS)
            time.sleep(4)
            msg = (f"Olá {nome}! Tudo bem? 👋\n\n"
                   f"Vi seu cadastro aqui na Conseg. Me conta uma coisa: esse projeto para 2026 é pra *Carro*, *Casa* ou *Investimento*?\n\n"
                   f"Já vou separar umas oportunidades aqui pra você.")
            enviar_zap(phone, msg)

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
def home(): return "Roberto V1011 - Calculadora Humana Ativa", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
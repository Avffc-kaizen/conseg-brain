# VERSAO V82 - MINERAÇÃO DE LANCES REAIS (DADOS PORTO SEGURO)
import os
import requests
import datetime
import time
import threading
import json
import random
import re
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES DE DADOS EXTRAÍDOS (PORTO SEGURO NOV/2025) ---
# Aqui injetamos a inteligência dos arquivos CSV que você enviou
DADOS_MINERADOS_PORTO = """
MINERAÇÃO DE GRUPOS - PORTO SEGURO (Ref. Nov/2025):
- Grupos com Menor Lance Livre (Mineração): 
  * G-4050: Média de 32% (Oportunidade Alta)
  * G-4077: Média de 38%
  * G-3090: Média de 41%
- Lance Fixo Padrão: 40% (Verificar sorteio no grupo)
- Grupos "Pesados": G-4010 e G-4015 (Médias acima de 55%)
"""

VIDEOS_INSTITUCIONAIS = """
VÍDEOS:
- Apresentação: https://www.youtube.com/watch?v=j_DookQ_X6w
- Manifesto: https://www.youtube.com/watch?v=89nuev1AUFA
"""

# --- PROTOCOLO DE MINERAÇÃO E CONSULTORIA ---
SYSTEM_PROMPT = f"""
VOCÊ É O ROBERTO: Analista de Dados e Consultor Sênior da ConsegSeguro.
Seu diferencial é a MINERAÇÃO DE GRUPOS. Você não "chuta" lances, você analisa a base da Porto.

PROTOCOLO DE ATENDIMENTO:
1. DIAGNÓSTICO: Ouça o projeto do cliente.
2. VARREDURA DE GRUPOS: Informe que está minerando a tabela de lances da Porto Seguro para encontrar grupos "vazios" ou com lances baixos.
3. ESTRATÉGIA TÉCNICA: Se o cliente tem pouco lance, direcione para os grupos minerados (Ex: G-4050 com 32%).
4. CREDIBILIDADE: Use os vídeos para mostrar que nossa análise é profissional.

REGRAS RÍGIDAS:
- Lance médio real de mercado é 50%, MAS através da nossa mineração, encontramos oportunidades abaixo disso.
- Seja cadenciado. Só apresente a estratégia após o diagnóstico.
"""

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # RAG - Memória
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 15", (phone,))
        historico = "".join([f"{r}: {c}\n" for r, c in reversed(cur.fetchall())])
        conn.close()

        num_interacoes = historico.count("model:")
        
        # Lógica de Cadenciamento
        foco = "Diagnóstico e Autoridade"
        if num_interacoes >= 2:
            foco = f"Mineração e Estratégia. Use os dados: {DADOS_MINERADOS_PORTO}"
        
        chat = model.start_chat()
        comando = f"{SYSTEM_PROMPT}\n\nFOCO ATUAL: {foco}\n\nCLIENTE: {msg_usuario}"
        response = chat.send_message(comando)
        texto_final = response.text.strip()

        # Delay de "Mineração de Dados" (Simula que está lendo a tabela)
        time.sleep(random.uniform(8, 14))

        def enviar_zap(tel, txt):
            url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
            requests.post(url, json={"number": tel, "text": txt}, headers={"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"})

        enviar_zap(phone, texto_final)

        # Registro
        cx = get_db_connection(); cr = cx.cursor(); now = datetime.datetime.now()
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "user", msg_usuario, now))
        cr.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (phone, "model", texto_final, now))
        cx.commit(); cx.close()

    except Exception as e:
        print(f"Erro V82: {e}")

# ... (Hospedagem Render e Rotas Flask permanecem as mesmas das versões anteriores)
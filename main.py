import os
import requests
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO ---
EVOLUTION_URL = os.getenv("EVOLUTION_URL") 
EVOLUTION_APIKEY = os.getenv("EVOLUTION_APIKEY")
INSTANCE = os.getenv("INSTANCE_NAME", "consorcio")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)

# Prompt simplificado para este deploy inicial
SYSTEM_PROMPT = """
VOCÊ É: Roberto, Mentor Financeiro Sênior da ConsegSeguro.
SUA MISSÃO: Transformar interessados em investidores de consórcio.
ESTILO: Curto, direto e educativo.
"""

async def gerar_msg(data):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"{SYSTEM_PROMPT}\nLead: {data.get('name')}, quer {data.get('objective')} de R$ {data.get('value')}."
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Erro IA: {e}")
        return f"Olá {data.get('name')}! Vi seu planejamento. Vamos conversar sobre como economizar?"

def enviar_zap(telefone, texto):
    if not telefone: return
    clean_phone = "".join(filter(str.isdigit, str(telefone)))
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    payload = {"number": clean_phone, "textMessage": {"text": texto}}
    headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"Erro Envio Zap: {e}")

@app.route('/webhook', methods=['POST'])
def novo_lead():
    data = request.json
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        msg = loop.run_until_complete(gerar_msg(data))
        loop.close()
        
        enviar_zap(data.get('phone'), msg)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
# ATUALIZACAO FORCADA VIA TERMINAL

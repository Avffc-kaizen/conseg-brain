# VERSAO V48 - SISTEMA RESTAURADO
import os
import requests
import sqlite3
import datetime
import time
import threading
import json
import random
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
LINK_AGENDA = "https://calendar.app.google/HxFwGyHA4zihQE27A"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

DB_FILE = "crm_nuvem.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (phone TEXT, role TEXT, content TEXT, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leads 
                 (phone TEXT, nome TEXT, status TEXT, last_interaction DATETIME, 
                  origem TEXT, funnel_stage INTEGER DEFAULT 0, 
                  tags TEXT DEFAULT '', current_product TEXT DEFAULT 'CONSORCIO')''')
    conn.commit()
    conn.close()

def salvar_msg(phone, role, content, nome="Cliente", origem="Whatsapp"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = datetime.datetime.now()
        c.execute("INSERT INTO messages VALUES (?, ?, ?, ?)", (phone, role, content, now))
        if role == 'user':
            c.execute("INSERT OR REPLACE INTO leads (phone, nome, status, last_interaction, origem, funnel_stage) VALUES (?, ?, 'ATIVO', ?, ?, 0)", 
                      (phone, nome, now, origem))
        conn.commit()
        conn.close()
    except: pass

def ler_historico(phone):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT role, content FROM messages WHERE phone = ? ORDER BY timestamp DESC LIMIT 20", (phone,))
        data = c.fetchall()
        conn.close()
        return [{"role": row[0], "parts": [row[1]]} for row in reversed(data)]
    except: return []

init_db()

# --- INTEGRAÇÃO WHATSAPP ---
def enviar_zap(telefone, texto):
    clean_phone = "".join(filter(str.isdigit, str(telefone)))
    if len(clean_phone) == 12 and clean_phone.startswith("55"):
        clean_phone = f"{clean_phone[:4]}9{clean_phone[4:]}"
    
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
    try:
        requests.post(url, json={"number": clean_phone, "text": texto}, headers=headers)
    except: pass

# --- PROFILER E IA ---
def analisar_vulnerabilidades(phone, texto_usuario):
    try:
        prompt = f"""Analise a frase e extraia tags: familia, veiculo, saude, renda. Frase: {texto_usuario}. Responda apenas as tags."""
        model = genai.GenerativeModel('gemini-2.0-flash')
        resp = model.generate_content(prompt)
        tags = resp.text.strip().lower()
        if len(tags) > 2:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT tags FROM leads WHERE phone = ?", (phone,))
            row = c.fetchone()
            antigas = row[0] if row else ""
            novas = ",".join(list(set(antigas.split(',') + tags.split(','))))
            c.execute("UPDATE leads SET tags = ? WHERE phone = ?", (novas, phone))
            conn.commit()
            conn.close()
    except: pass

SYSTEM_PROMPT = f"""
IDENTIDADE: Roberto, Consultor Sênior da ConsegSeguro.
MISSÃO: Vender Consórcio e Seguros.
ESTILO: Estóico, Protetor, Breve.
AGENDAMENTO: {LINK_AGENDA}
"""

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    if 0 <= datetime.datetime.now().hour < 6: return
    time.sleep(min(len(msg_usuario) * 0.05, 4) + 2)
    threading.Thread(target=analisar_vulnerabilidades, args=(phone, msg_usuario)).start()

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        history = ler_historico(phone)
        chat = model.start_chat(history=history)
        prompt = f"{SYSTEM_PROMPT}\nCliente: {msg_usuario}\nRoberto:"
        response = chat.send_message(prompt)
        texto_resp = response.text.strip()
        time.sleep(min(len(texto_resp) * 0.05, 6))
        salvar_msg(phone, "model", texto_resp, nome_cliente)
        enviar_zap(phone, texto_resp)
    except: pass

# --- NOVO: ROTA DE LIMPEZA DE DUPLICATAS ---
@app.route('/fix/limpeza', methods=['GET'])
def limpar_duplicatas():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            DELETE FROM leads 
            WHERE rowid NOT IN (
                SELECT MAX(rowid) 
                FROM leads 
                GROUP BY phone
            )
        ''')
        removidos = c.rowcount
        conn.commit()
        conn.close()
        return jsonify({"status": "Limpeza Concluída", "duplicatas_removidas": removidos})
    except Exception as e:
        return jsonify({"erro": str(e)})

# --- WORKER ANTI-DUPLICIDADE ---
def ja_falou_hoje(phone):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        ontem = datetime.datetime.now() - datetime.timedelta(hours=24)
        c.execute("SELECT count(*) FROM messages WHERE phone = ? AND timestamp > ?", (phone, ontem))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except: return False

@app.route('/cron/aquecimento', methods=['GET'])
def processar_aquecimento():
    hora = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).hour
    if hora < 9 or hora > 19: return jsonify({"msg": "Dormindo"})

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT phone, nome FROM leads WHERE status = 'FILA_AQUECIMENTO' GROUP BY phone LIMIT 20")
    lote = c.fetchall()
    conn.close()
    
    if not lote: return jsonify({"msg": "Fila vazia."})

    def worker(lista):
        conn_w = sqlite3.connect(DB_FILE, timeout=30)
        c_w = conn_w.cursor()
        for p, n in lista:
            try:
                if ja_falou_hoje(p):
                    print(f"🚫 Pulando {p} (Já recebeu mensagem hoje)")
                    c_w.execute("UPDATE leads SET status = 'ATIVO' WHERE phone = ?", (p,))
                    conn_w.commit()
                    continue

                msg = f"Olá {n}, tudo bem? Roberto aqui da ConsegSeguro. ☀️ Encontrei seu cadastro antigo aqui. Como estão seus planos de aquisição? O mercado deu uma aquecida e surgiram grupos novos."
                enviar_zap(p, msg)
                c_w.execute("UPDATE leads SET status = 'ATIVO', last_interaction = ? WHERE phone = ?", (datetime.datetime.now(), p))
                c_w.execute("INSERT INTO messages VALUES (?, ?, ?, ?)", (p, 'model', msg, datetime.datetime.now()))
                conn_w.commit()
                time.sleep(random.randint(30, 60))
            except: continue
        conn_w.close()

    threading.Thread(target=worker, args=(lote,)).start()
    return jsonify({"status": "Lote V47 Iniciado", "qtd": len(lote)})

@app.route('/importar_leads', methods=['POST'])
def importar_leads():
    lista = request.json
    c = 0
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    for l in lista:
        try:
            p = "".join(filter(str.isdigit, str(l.get('phone'))))
            cur.execute("INSERT INTO leads (phone, nome, status, last_interaction, origem) VALUES (?, ?, 'FILA_AQUECIMENTO', ?, 'Base')", (p, l.get('nome','Investidor'), datetime.datetime.now()))
            c += 1
        except: pass
    conn.commit()
    conn.close()
    return jsonify({"status": "Importado", "qtd": c})

@app.route('/webhook/google-ads', methods=['POST'])
def google_ads_hook():
    return jsonify({"status": "received"}), 200

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    try:
        b = request.json
        if b.get('event') == 'messages.upsert':
            k = b.get('data',{}).get('key',{})
            if not k.get('fromMe'):
                p = k.get('remoteJid','').split('@')[0]
                t = b.get('data',{}).get('message',{}).get('conversation')
                n = b.get('data',{}).get('pushName', 'Cliente')
                if t: threading.Thread(target=responder_chat_inteligente, args=(p, t, n)).start()
        return jsonify({"status": "ok"}), 200
    except: return jsonify({"status": "error"}), 500

@app.route('/', methods=['GET'])
def health(): return jsonify({"status": "Roberto V47 - Restaurado"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
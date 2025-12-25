# VERSAO V56.1
import os
import requests
import datetime
import time
import threading
import json
import random
import psycopg2
import base64
import tempfile
from pathlib import Path
from psycopg2.extras import RealDictCursor
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
DATABASE_URL = os.getenv("DATABASE_URL") 
LINK_AGENDA = "https://calendar.app.google/HxFwGyHA4zihQE27A"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# --- CONEXÃO COM BANCO ---
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS messages 
                       (phone TEXT, role TEXT, content TEXT, timestamp TIMESTAMP)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS leads 
                       (phone TEXT PRIMARY KEY, nome TEXT, status TEXT, 
                        last_interaction TIMESTAMP, origem TEXT, 
                        funnel_stage INTEGER DEFAULT 0, 
                        tags TEXT DEFAULT '', current_product TEXT DEFAULT 'CONSORCIO')''')
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Banco de Dados V56 Conectado!")
    except Exception as e:
        print(f"❌ Erro ao conectar no Banco: {e}")

init_db()

# --- FUNÇÕES DE BANCO ---
def salvar_msg(phone, role, content, nome="Cliente", origem="Whatsapp"):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        now = datetime.datetime.now()
        cur.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", 
                    (phone, role, content, now))
        if role == 'user':
            cur.execute("""
                INSERT INTO leads (phone, nome, status, last_interaction, origem, funnel_stage) 
                VALUES (%s, %s, 'ATIVO', %s, %s, 0)
                ON CONFLICT (phone) DO UPDATE 
                SET status = 'ATIVO', last_interaction = %s, nome = EXCLUDED.nome
            """, (phone, nome, now, origem, now))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erro salvar_msg: {e}")

def ler_historico(phone):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 15", (phone,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return [{"role": row[0], "parts": [row[1]]} for row in reversed(data)]
    except: return []

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

# --- INTELIGÊNCIA DE VENDAS & ÁUDIO ---
SYSTEM_PROMPT = f"""
IDENTIDADE: Roberto, Consultor Sênior da ConsegSeguro.
OBJETIVO: Vender Consórcio (Imóvel, Carro, Pesados) ouvindo o cliente.
REGRAS:
1. Se receber um áudio, ouça com atenção e responda em TEXTO curto.
2. Não mande link de agenda no começo.
3. Sondar -> Educar -> Ofertar.
LINK DA AGENDA: {LINK_AGENDA}
"""

def processar_audio_e_responder(phone, audio_url, nome_cliente):
    """Baixa o áudio, envia pro Gemini ouvir e gera a resposta"""
    path_audio = None
    try:
        # 1. Baixar o áudio
        print(f"🎧 Recebendo áudio de {phone}...")
        
        # Tenta pegar o base64 direto da API se possível, ou baixa da URL pública
        # Aqui assumimos que a URL vem acessível do Webhook da Evolution
        headers = {"apikey": EVOLUTION_APIKEY}
        response = requests.get(audio_url, headers=headers, stream=True)
        
        if response.status_code != 200:
            print("❌ Erro ao baixar áudio. Tentando método alternativo...")
            # Fallback: Pedir base64 para Evolution (caso a URL seja interna)
            # Implementação simplificada: avisa erro se não conseguir baixar
            return

        # 2. Salvar temporário
        suffix = ".mp3" if "mpeg" in response.headers.get('Content-Type', '') else ".ogg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            path_audio = tmp.name
            for chunk in response.iter_content(chunk_size=1024):
                tmp.write(chunk)
        
        # 3. Enviar para Gemini
        myfile = genai.upload_file(path_audio)
        print(f"🗣️ Áudio enviado para IA: {myfile.name}")
        
        # 4. Gerar Resposta
        model = genai.GenerativeModel('gemini-1.5-flash') # 1.5 é ótimo para áudio
        history = ler_historico(phone)
        
        # Adiciona o arquivo de áudio no final do histórico para ele "ouvir" agora
        chat = model.start_chat(history=history)
        prompt_final = f"{SYSTEM_PROMPT}\nO cliente {nome_cliente} enviou este áudio. Ouça, entenda a intenção e responda em texto como Roberto."
        
        response_ia = chat.send_message([prompt_final, myfile])
        texto_resp = response_ia.text.strip()
        
        # 5. Enviar Resposta e Salvar
        salvar_msg(phone, "user", "[ÁUDIO ENVIADO PELO CLIENTE]", nome_cliente)
        salvar_msg(phone, "model", texto_resp, nome_cliente)
        enviar_zap(phone, texto_resp)

    except Exception as e:
        print(f"❌ Erro no processamento de áudio: {e}")
        enviar_zap(phone, "Opa, minha conexão falhou ao tentar ouvir seu áudio. Pode escrever por favor?")
    finally:
        # Limpeza
        if path_audio and os.path.exists(path_audio):
            os.remove(path_audio)

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    try:
        # Analisa Tags Simples (Profiler)
        tags = [t for t in ['casa', 'carro', 'moto', 'investimento'] if t in msg_usuario.lower()]
        if tags:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE leads SET tags = %s WHERE phone = %s", (",".join(tags), phone))
            conn.commit()
            conn.close()

        # Resposta IA
        model = genai.GenerativeModel('gemini-2.0-flash')
        history = ler_historico(phone)
        chat = model.start_chat(history=history)
        
        prompt_final = f"{SYSTEM_PROMPT}\nCliente {nome_cliente}: {msg_usuario}\nRoberto:"
        response = chat.send_message(prompt_final)
        texto_resp = response.text.strip()
        
        salvar_msg(phone, "user", msg_usuario, nome_cliente)
        salvar_msg(phone, "model", texto_resp, nome_cliente)
        enviar_zap(phone, texto_resp)
    except Exception as e:
        print(f"Erro IA: {e}")

# --- ROTAS ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    try:
        b = request.json
        if b.get('event') == 'messages.upsert':
            data = b.get('data', {})
            msg_type = data.get('messageType')
            key = data.get('key', {})
            
            if not key.get('fromMe'):
                phone = key.get('remoteJid', '').split('@')[0]
                push_name = data.get('pushName', 'Cliente')
                
                # 1. É Texto Simples?
                if msg_type == 'conversation':
                    texto = data.get('message', {}).get('conversation')
                    if texto: threading.Thread(target=responder_chat_inteligente, args=(phone, texto, push_name)).start()
                
                # 2. É Texto Estendido (Resposta a msg)?
                elif msg_type == 'extendedTextMessage':
                    texto = data.get('message', {}).get('extendedTextMessage', {}).get('text')
                    if texto: threading.Thread(target=responder_chat_inteligente, args=(phone, texto, push_name)).start()

                # 3. É ÁUDIO?
                elif msg_type == 'audioMessage':
                    audio_url = data.get('message', {}).get('audioMessage', {}).get('url')
                    # Tenta pegar URL assinada ou direta
                    if audio_url:
                        threading.Thread(target=processar_audio_e_responder, args=(phone, audio_url, push_name)).start()

        return jsonify({"status": "ok"}), 200
    except: return jsonify({"status": "error"}), 500

@app.route('/importar_leads', methods=['POST'])
def importar_leads():
    lista = request.json
    c = 0
    conn = get_db_connection()
    cur = conn.cursor()
    for l in lista:
        try:
            p = "".join(filter(str.isdigit, str(l.get('phone'))))
            n = l.get('nome', 'Investidor')
            now = datetime.datetime.now()
            cur.execute("""
                INSERT INTO leads (phone, nome, status, last_interaction, origem) 
                VALUES (%s, %s, 'FILA_AQUECIMENTO', %s, 'Base')
                ON CONFLICT (phone) DO NOTHING
            """, (p, n, now))
            c += 1
        except: pass
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "Importado", "qtd": c})

@app.route('/cron/aquecimento', methods=['GET'])
def processar_aquecimento():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT phone, nome FROM leads WHERE status = 'FILA_AQUECIMENTO' LIMIT 20")
    lote = cur.fetchall()
    conn.close()
    
    if not lote: return jsonify({"msg": "Fila vazia."})

    def worker(lista):
        for p, n in lista:
            try:
                msg = f"Olá {n}, tudo bem? Roberto aqui da ConsegSeguro. ☀️ Como estão seus planos de investimento hoje?"
                enviar_zap(p, msg)
                salvar_msg(p, "model", msg, n)
                # Tira da fila
                cx = get_db_connection()
                cx.cursor().execute("UPDATE leads SET status = 'ATIVO' WHERE phone = %s", (p,))
                cx.commit()
                cx.close()
                time.sleep(random.randint(30, 60))
            except: pass

    threading.Thread(target=worker, args=(lote,)).start()
    return jsonify({"status": "Lote Iniciado", "qtd": len(lote)})

@app.route('/fix/raio_x', methods=['GET'])
def raio_x():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM leads")
        total = cur.fetchone()[0]
        conn.close()
        return jsonify({"total_leads": total, "status": "V56 Ouvido Absoluto"})
    except: return jsonify({"erro": "banco"})

@app.route('/', methods=['GET'])
def health(): return jsonify({"status": "Roberto V56.1 - AGORA VAI"}), 200
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
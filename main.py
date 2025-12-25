# VERSAO V52 - ESPECIALISTA MULTIMODAL (AUDIO + CROSS-SELL)
import os
import requests
import datetime
import time
import threading
import json
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from pathlib import Path

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

# --- CONEXÃO COM BANCO (POSTGRESQL) ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Erro Conexão DB: {e}")
        return None

def init_db():
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS messages 
                           (phone TEXT, role TEXT, content TEXT, timestamp TIMESTAMP, tipo TEXT DEFAULT 'text')''')
            cur.execute('''CREATE TABLE IF NOT EXISTS leads 
                           (phone TEXT PRIMARY KEY, nome TEXT, status TEXT, 
                            last_interaction TIMESTAMP, origem TEXT, 
                            funnel_stage INTEGER DEFAULT 0, 
                            tags TEXT DEFAULT '', current_product TEXT DEFAULT 'CONSORCIO')''')
            conn.commit()
            cur.close()
            conn.close()
            print("✅ Banco V52 (Áudio+CrossSell) Conectado!")
    except Exception as e:
        print(f"❌ Erro Init DB: {e}")

init_db()

# --- FUNÇÕES DE BANCO ---
def salvar_msg(phone, role, content, nome="Cliente", origem="Whatsapp", tipo="text"):
    try:
        conn = get_db_connection()
        if not conn: return
        cur = conn.cursor()
        now = datetime.datetime.now()
        cur.execute("INSERT INTO messages (phone, role, content, timestamp, tipo) VALUES (%s, %s, %s, %s, %s)", 
                    (phone, role, content, now, tipo))
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

# --- NOVAS FUNÇÕES V52: PROCESSAMENTO DE ÁUDIO ---
def processar_audio_gemini(audio_url, phone):
    """Baixa o áudio do WhatsApp e envia para o Gemini transcrever/entender"""
    try:
        # 1. Baixar o arquivo de áudio temporariamente
        msg_audio = requests.get(audio_url, headers={"apikey": EVOLUTION_APIKEY})
        if msg_audio.status_code != 200: return "[Erro ao baixar áudio]"
        
        filename = f"temp_{phone}_{int(time.time())}.mp3"
        with open(filename, "wb") as f:
            f.write(msg_audio.content)

        # 2. Upload para o Gemini (File API)
        myfile = genai.upload_file(filename, mime_type="audio/mp3")
        
        # 3. Pedir transcrição e análise de sentimento
        model = genai.GenerativeModel("gemini-1.5-flash")
        result = model.generate_content([
            "Transcreva este áudio com precisão. Se o cliente parecer irritado ou urgente, avise entre colchetes [URGENTE].", 
            myfile
        ])
        
        # Limpeza
        os.remove(filename)
        return result.text.strip()
    except Exception as e:
        print(f"Erro Áudio: {e}")
        return "[Áudio recebido, mas não consegui ouvir. Peça para escrever.]"

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

# --- CÉREBRO V52: CROSS-SELL & ESPECIALISTA ---
def analisar_tags_venda(phone, texto_usuario):
    """Identifica oportunidades de Cross-Sell baseado no texto"""
    try:
        prompt = f"""
        Analise a frase e extraia tags de interesse: 
        TAGS POSSIVEIS: consorcio_imovel, consorcio_auto, seguro_vida, seguro_auto, familia, investidor, saude.
        Frase: {texto_usuario}
        Responda apenas as tags separadas por virgula.
        """
        model = genai.GenerativeModel('gemini-2.0-flash')
        resp = model.generate_content(prompt)
        novas_tags = resp.text.strip().lower()
        
        if len(novas_tags) > 3:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT tags FROM leads WHERE phone = %s", (phone,))
            row = cur.fetchone()
            antigas = row[0] if row else ""
            
            # Lógica de Cross-Sell: Se tem X, adiciona gatilho para Y
            lista_tags = list(set(antigas.split(',') + novas_tags.split(',')))
            
            # Gatilhos Automáticos de Cross-Sell
            if "consorcio_imovel" in lista_tags and "seguro_vida" not in lista_tags:
                lista_tags.append("oportunidade_vida") # Quem faz dívida precisa de proteção
            if "consorcio_auto" in lista_tags and "seguro_auto" not in lista_tags:
                lista_tags.append("oportunidade_auto") # Quem compra carro precisa de seguro
                
            tags_final = ",".join(lista_tags)
            cur.execute("UPDATE leads SET tags = %s WHERE phone = %s", (tags_final, phone))
            conn.commit()
            cur.close()
            conn.close()
    except: pass

SYSTEM_PROMPT = f"""
IDENTIDADE: Roberto, Consultor Especialista da ConsegSeguro.
MISSÃO: Consultoria Patrimonial 360º (Consórcio, Seguros e Investimento).
SITE: consegseguro.com

--- INTELIGÊNCIA DE CROSS-SELL (VENDA CRUZADA) ---
1. SE o cliente falar de CARRO/VEÍCULO:
   - Foco Principal: Consórcio (Planejamento sem juros).
   - Gatilho Cross-Sell: "Além do consórcio, já pensou na proteção do veículo? Temos o Seguro Auto com assistência 24h."

2. SE o cliente falar de IMÓVEL/CASA:
   - Foco Principal: Consórcio (Sair do aluguel/Investimento).
   - Gatilho Cross-Sell: "Para garantir essa conquista, o Seguro de Vida é essencial para quitar o saldo em imprevistos."

3. SE o cliente falar de FAMÍLIA/FILHOS:
   - Foco: Proteção Patrimonial.
   - Gatilho Cross-Sell: Mencione o Seguro Saúde ou Vida como forma de blindar o padrão de vida deles.

--- REGRAS DE ETIQUETA ---
- NÃO envie link de agenda no início.
- SE receber áudio transcrito, responda com naturalidade, como se tivesse ouvido.
- PERGUNTE mais do que afirme. Sondagem é a chave.
- OBJETIVO: Levar o cliente a perceber a necessidade da proteção completa.

LINK AGENDA: {LINK_AGENDA} (Só enviar no fechamento)
"""

def responder_chat_inteligente(phone, msg_usuario, nome_cliente, tipo_msg="text"):
    time.sleep(min(len(msg_usuario) * 0.05, 4) + 2)
    
    # Roda análise de tags em background
    threading.Thread(target=analisar_tags_venda, args=(phone, msg_usuario)).start()

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        history = ler_historico(phone)
        chat = model.start_chat(history=history)
        
        prompt_final = f"{SYSTEM_PROMPT}\nHistórico Recente: O cliente {nome_cliente} mandou ({tipo_msg}): {msg_usuario}\nRoberto:"
        
        response = chat.send_message(prompt_final)
        texto_resp = response.text.strip()
        
        time.sleep(min(len(texto_resp) * 0.05, 6))
        salvar_msg(phone, "model", texto_resp, nome_cliente)
        enviar_zap(phone, texto_resp)
    except Exception as e:
        print(f"Erro IA: {e}")

# --- ROTAS DE GESTÃO ---
@app.route('/fix/raio_x', methods=['GET'])
def raio_x():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
        resumo = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"status": dict(resumo), "msg": "V52 Operando com Áudio e Cross-Sell"})
    except: return jsonify({"erro": "db"})

# --- MOTOR DO CRON (AQUECIMENTO) ---
def ja_falou_hoje(phone):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM messages WHERE phone = %s AND timestamp > NOW() - INTERVAL '24 hours'", (phone,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0
    except: return False

@app.route('/cron/aquecimento', methods=['GET'])
def processar_aquecimento():
    # hora = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).hour
    # if hora < 9 or hora > 19: return jsonify({"msg": "Dormindo"})

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT phone, nome FROM leads WHERE status = 'FILA_AQUECIMENTO' LIMIT 20")
    lote = cur.fetchall()
    
    if not lote: 
        cur.close()
        conn.close()
        return jsonify({"msg": "Fila vazia."})

    def worker(lista):
        conn_w = get_db_connection()
        cur_w = conn_w.cursor()
        for p, n in lista:
            try:
                if ja_falou_hoje(p):
                    # Tira da fila para destravar
                    cur_w.execute("UPDATE leads SET status = 'ATIVO' WHERE phone = %s", (p,))
                    conn_w.commit()
                    continue

                msg = f"Olá {n}, tudo bem? Aqui é o Roberto da ConsegSeguro. ☀️ Estava analisando as oportunidades de hoje e lembrei do seu perfil. Você busca alavancar patrimônio (imóveis) ou atualizar seus veículos este ano?"
                
                enviar_zap(p, msg)
                now = datetime.datetime.now()
                cur_w.execute("UPDATE leads SET status = 'ATIVO', last_interaction = %s WHERE phone = %s", (now, p))
                cur_w.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", (p, 'model', msg, now))
                conn_w.commit()
                time.sleep(random.randint(30, 60))
            except: continue
        cur_w.close()
        conn_w.close()

    threading.Thread(target=worker, args=(lote,)).start()
    return jsonify({"status": "Lote V52 Iniciado", "qtd": len(lote)})

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

# --- WEBHOOK (COM SUPORTE A ÁUDIO) ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    try:
        b = request.json
        if b.get('event') == 'messages.upsert':
            k = b.get('data',{}).get('key',{})
            if not k.get('fromMe'):
                p = k.get('remoteJid','').split('@')[0]
                n = b.get('data',{}).get('pushName', 'Cliente')
                msg_type = b.get('data',{}).get('messageType', 'conversation')
                
                content = ""
                tipo_conteudo = "text"

                # 1. Se for Texto
                if msg_type == 'conversation' or msg_type == 'extendedTextMessage':
                    content = b.get('data',{}).get('message',{}).get('conversation') or \
                              b.get('data',{}).get('message',{}).get('extendedTextMessage',{}).get('text')
                
                # 2. Se for Áudio (NOVIDADE V52)
                elif msg_type == 'audioMessage':
                    audio_url = b.get('data',{}).get('message',{}).get('audioMessage',{}).get('url')
                    if not audio_url:
                         # Fallback para base64 se a Evolution mandar diferente
                         audio_url = b.get('data',{}).get('message',{}).get('base64') 
                    
                    if audio_url:
                        # Processa o áudio usando Gemini
                        print(f"🎤 Processando áudio de {p}...")
                        content = processar_audio_gemini(audio_url, p)
                        content = f"[Transcrição de Áudio]: {content}"
                        tipo_conteudo = "audio"

                if content:
                    salvar_msg(p, "user", content, n, "Whatsapp", tipo_conteudo)
                    threading.Thread(target=responder_chat_inteligente, args=(p, content, n, tipo_conteudo)).start()
                    
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Erro Hook: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/', methods=['GET'])
def health(): return jsonify({"status": "Roberto V52 - Especialista Multimodal"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
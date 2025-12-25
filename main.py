# VERSAO V51 - CONSULTOR SENIOR (SEM LINK PRECOCE)
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

# --- CONEXÃO COM BANCO (MANTIDA V50) ---
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
        print("✅ Banco de Dados Conectado!")
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
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 20", (phone,))
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

# --- IA E PROFILER (V51 - INTELIGENCIA DE VENDAS) ---
def analisar_vulnerabilidades(phone, texto_usuario):
    # Essa função extrai tags para saber o que o cliente quer
    try:
        prompt = f"""Analise a frase e extraia tags: familia, veiculo, saude, renda, casa, investimento. Frase: {texto_usuario}. Responda apenas as tags."""
        model = genai.GenerativeModel('gemini-2.0-flash')
        resp = model.generate_content(prompt)
        tags = resp.text.strip().lower()
        if len(tags) > 2:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT tags FROM leads WHERE phone = %s", (phone,))
            row = cur.fetchone()
            antigas = row[0] if row else ""
            novas = ",".join(list(set(antigas.split(',') + tags.split(','))))
            cur.execute("UPDATE leads SET tags = %s WHERE phone = %s", (novas, phone))
            conn.commit()
            cur.close()
            conn.close()
    except: pass

# --- O NOVO CÉREBRO V51 ---
SYSTEM_PROMPT = f"""
IDENTIDADE: Roberto, Consultor Sênior da ConsegSeguro.
CARACTERÍSTICAS: Experiente, Empático, Ouvinte Atento, Estrategista.

OBJETIVO PRINCIPAL: Dialogar para entender o momento de vida do cliente e apresentar o consórcio como a solução inteligente.

REGRAS DE OURO (Consultor Sênior):
1. JAMAIS envie o link de agendamento na primeira resposta ou se o cliente tiver dúvidas básicas. O agendamento é o ÚLTIMO passo.
2. Se o cliente perguntar "como assim" ou tiver dúvida, EXPLIQUE com paciência e clareza. Use metáforas simples.
3. FAÇA PERGUNTAS. Um bom consultor ouve mais do que fala. Descubra se ele quer Casa, Carro ou Investimento.
4. NUNCA EMPURRE O PRODUTO. Guie o cliente.

ROTEIRO DE VENDAS:
- Fase 1 (Sondagem): O cliente respondeu? Pergunte educadamente qual é o objetivo dele hoje (Aumentar patrimônio? Trocar de carro? Sair do aluguel?).
- Fase 2 (Educação): Mostre que você entendeu. Ex: "Para sair do aluguel, o consórcio economiza X% comparado ao financiamento".
- Fase 3 (Fechamento): SÓ AQUI, se o cliente estiver engajado, ofereça a conversa com o especialista humano.

LINK DA AGENDA: {LINK_AGENDA}
(Use este link APENAS se o cliente pedir explicitamente ou se a conversa já estiver madura e ele quiser simular valores).

TOM DE VOZ: Seguro, amigável, profissional. Respostas curtas e diretas.
"""

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    # Remove trava de horário para testes, se quiser pode descomentar
    # if 0 <= datetime.datetime.now().hour < 6: return
    
    time.sleep(min(len(msg_usuario) * 0.05, 4) + 2)
    threading.Thread(target=analisar_vulnerabilidades, args=(phone, msg_usuario)).start()

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        history = ler_historico(phone)
        chat = model.start_chat(history=history)
        
        # O Prompt agora é inserido dinamicamente no contexto
        prompt_final = f"{SYSTEM_PROMPT}\nHistórico Recente: O cliente se chama {nome_cliente}.\nCliente diz: {msg_usuario}\nRoberto (Siga as REGRAS DE OURO):"
        
        response = chat.send_message(prompt_final)
        texto_resp = response.text.strip()
        
        # Segurança extra: Se a resposta for muito curta e tiver link, abortar link
        if len(texto_resp) < 100 and "calendar" in texto_resp and "?" in msg_usuario:
             # Se o cliente fez pergunta e o bot mandou só link, forçamos uma explicação
             texto_resp = "O consórcio é uma forma planejada de compra, sem os juros altos do financiamento. Qual seria seu objetivo hoje? Imóvel ou Veículo?"

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
        cur.execute("SELECT COUNT(*) FROM leads")
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({"total_leads_no_banco_eterno": total, "status": dict(resumo)})
    except Exception as e:
        return jsonify({"erro": str(e)})

# --- MOTOR DO CRON ---
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
    # Descomente a linha abaixo para respeitar horário comercial
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
                    print(f"🚫 Pulando {p}")
                    cur_w.execute("UPDATE leads SET status = 'ATIVO' WHERE phone = %s", (p,))
                    conn_w.commit()
                    continue

                # Mensagem de Abordagem Inicial (Leve e Curta)
                msg = f"Olá {n}, tudo bem? Aqui é o Roberto da ConsegSeguro. ☀️ Estava revisando alguns cadastros e vi seu interesse antigo. Você ainda pensa em investir em bens (imóveis ou veículos) de forma planejada?"
                
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
    return jsonify({"status": "Lote V51 Iniciado", "qtd": len(lote)})

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
def health(): return jsonify({"status": "Roberto V51 - Consultor Sênior"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
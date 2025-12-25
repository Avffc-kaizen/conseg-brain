# VERSAO V54 - CONSULTOR DE PRECISAO (SIMULADOR OFICIAL)
import os
import requests
import datetime
import time
import threading
import json
import random
import re
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
# Link Oficial do App
LINK_SIMULADOR = "https://consorcio.consegseguro.com/app"
LINK_AGENDA = "https://calendar.app.google/HxFwGyHA4zihQE27A"

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# --- TABELA DE FATORES (PARA PRECISÃO MATEMÁTICA) ---
# Usamos isso para o Robô não falar "besteira" antes do cliente clicar no link.
# Fator = (1 + TaxaAdmTotal) / PrazoMaximo
FATORES = {
    "imovel": {"prazo": 200, "taxa_total": 0.23, "nome": "Imóvel"}, # Ex: 23% taxa em 200m
    "auto":   {"prazo": 80,  "taxa_total": 0.16, "nome": "Automóvel"},
    "moto":   {"prazo": 60,  "taxa_total": 0.20, "nome": "Moto"},
    "pesado": {"prazo": 100, "taxa_total": 0.18, "nome": "Caminhões/Pesados"}
}

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
                            tags TEXT DEFAULT '', current_product TEXT DEFAULT 'CONSORCIO',
                            score INTEGER DEFAULT 0)''')
            try:
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0")
            except: pass
            
            conn.commit()
            cur.close()
            conn.close()
            print("✅ Banco V54 (Simulador) Conectado!")
    except Exception as e:
        print(f"❌ Erro Init DB: {e}")

init_db()

# --- FUNÇÕES DE BANCO ---
def atualizar_lead(phone, nome, status=None, score_delta=0, tags_novas=None):
    try:
        conn = get_db_connection()
        if not conn: return
        cur = conn.cursor()
        now = datetime.datetime.now()
        
        cur.execute("SELECT score, tags FROM leads WHERE phone = %s", (phone,))
        row = cur.fetchone()
        current_score = row[0] if row and row[0] else 0
        current_tags = row[1] if row and row[1] else ""
        
        new_score = current_score + score_delta
        new_tags = current_tags
        if tags_novas:
            lista_tags = list(set(current_tags.split(',') + tags_novas.split(',')))
            new_tags = ",".join(lista_tags)
            
        sql_status = f", status = '{status}'" if status else ""
        
        cur.execute(f"""
            INSERT INTO leads (phone, nome, status, last_interaction, origem, funnel_stage, score, tags) 
            VALUES (%s, %s, 'ATIVO', %s, 'Whatsapp', 0, %s, %s)
            ON CONFLICT (phone) DO UPDATE 
            SET last_interaction = %s, score = %s, tags = %s {sql_status}
        """, (phone, nome, now, new_score, new_tags, now, new_score, new_tags))
        conn.commit()
        cur.close()
        conn.close()
    except: pass

def salvar_msg(phone, role, content, nome="Cliente", tipo="text"):
    try:
        conn = get_db_connection()
        if not conn: return
        cur = conn.cursor()
        now = datetime.datetime.now()
        cur.execute("INSERT INTO messages (phone, role, content, timestamp, tipo) VALUES (%s, %s, %s, %s, %s)", 
                    (phone, role, content, now, tipo))
        conn.commit()
        cur.close()
        conn.close()
        
        if role == 'user':
            pontos = 10
            if tipo == 'audio': pontos = 20
            if len(content) > 50: pontos += 5
            atualizar_lead(phone, nome, status='ATIVO', score_delta=pontos)
    except: pass

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

# --- CALCULADORA INTELIGENTE V54 ---
def estimar_parcela(texto):
    """
    Identifica o produto (Imóvel/Auto/Pesado) e o valor, 
    calcula com precisão e DEVOLVE O LINK do simulador.
    """
    texto_lower = texto.lower()
    
    # 1. Identificar Produto
    produto = "auto" # Padrão
    if "casa" in texto_lower or "imovel" in texto_lower or "apto" in texto_lower: produto = "imovel"
    elif "moto" in texto_lower: produto = "moto"
    elif "caminhao" in texto_lower or "pesado" in texto_lower: produto = "pesado"
    
    # 2. Identificar Valor
    match = re.search(r'(\d+)\s?(mil|k|000)', texto_lower)
    
    msg_calculo = ""
    if match:
        try:
            valor_base = int(match.group(1))
            valor_total = valor_base * 1000 if ("mil" in match.group(0) or "k" in match.group(0)) else valor_base
            
            # 3. Matemática Financeira
            dados = FATORES[produto]
            prazo = dados["prazo"]
            taxa = dados["taxa_total"]
            
            # Fórmula: (Credito * (1 + Taxa)) / Prazo
            parcela = (valor_total * (1 + taxa)) / prazo
            
            msg_calculo = f"""
            [SISTEMA DE CÁLCULO]: O cliente cotou {dados['nome']} de R$ {valor_total:,.2f}.
            - Cálculo Base: R$ {parcela:,.2f}/mês em {prazo} meses.
            - AÇÃO OBRIGATÓRIA: Informe esta estimativa e diga: "Para validar essa condição oficial, acesse nosso app exclusivo: {LINK_SIMULADOR}"
            """
        except: pass
    
    return msg_calculo

# --- INTEGRAÇÃO WHATSAPP & AUDIO ---
def processar_audio_gemini(audio_url, phone):
    try:
        msg_audio = requests.get(audio_url, headers={"apikey": EVOLUTION_APIKEY})
        if msg_audio.status_code != 200: return "[Erro baixar áudio]"
        filename = f"temp_{phone}_{int(time.time())}.mp3"
        with open(filename, "wb") as f: f.write(msg_audio.content)
        
        myfile = genai.upload_file(filename, mime_type="audio/mp3")
        model = genai.GenerativeModel("gemini-1.5-flash")
        result = model.generate_content(["Transcreva este áudio exatamente.", myfile])
        os.remove(filename)
        return result.text.strip()
    except: return "[Áudio inaudível]"

def enviar_zap(telefone, texto):
    clean_phone = "".join(filter(str.isdigit, str(telefone)))
    if len(clean_phone) == 12 and clean_phone.startswith("55"): clean_phone = f"{clean_phone[:4]}9{clean_phone[4:]}"
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
    try: requests.post(url, json={"number": clean_phone, "text": texto}, headers=headers)
    except: pass

# --- CÉREBRO V54: CONSULTOR DE ELITE ---
def analisar_intencao(phone, texto_usuario):
    try:
        tags_detectadas = []
        texto_lower = texto_usuario.lower()
        
        if "casa" in texto_lower or "imovel" in texto_lower: tags_detectadas.append("consorcio_imovel")
        if "carro" in texto_lower or "veiculo" in texto_lower: tags_detectadas.append("consorcio_auto")
        if "filho" in texto_lower or "familia" in texto_lower: tags_detectadas.append("familia")
        
        score_extra = 0
        if "fechar" in texto_lower or "simular" in texto_lower:
            score_extra = 20
        
        if tags_detectadas or score_extra > 0:
            tags_str = ",".join(tags_detectadas)
            atualizar_lead(phone, "Cliente", score_delta=score_extra, tags_novas=tags_str)
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT tags FROM leads WHERE phone = %s", (phone,))
            current_tags = cur.fetchone()[0]
            conn.close()
            
            if "consorcio_imovel" in current_tags and "seguro_vida" not in current_tags:
                return " [DICA: Ofertou Imóvel? Mencione o Seguro de Vida para proteção da carta.]"
    except: return ""
    return ""

SYSTEM_PROMPT = f"""
IDENTIDADE: Roberto, Consultor Especialista da ConsegSeguro.
FERRAMENTA OFICIAL: Simulador Conseg ({LINK_SIMULADOR}).

MISSÃO:
1. Atuar como um Consultor de Elite (Ouvir > Entender > Ofertar).
2. Se o cliente pedir valores, use a estimativa calculada, MAS SEMPRE ENVIE O LINK DO APP para ele "bater o martelo".
3. Nunca invente taxas. Use os dados fornecidos pelo sistema.

PRODUTOS:
- Consórcio (Auto, Imóvel, Pesados, Motos).
- Seguros (Vida, Auto, Residencial).

REGRA DE OURO (VALORES):
Se o sistema te der um cálculo, apresente-o como "Estimativa de Mercado" e diga:
"Confira a parcela exata e os grupos em andamento no nosso simulador oficial: {LINK_SIMULADOR}"

TOM: Seguro, Profissional, Resolutivo.
"""

def responder_chat_inteligente(phone, msg_usuario, nome_cliente, tipo_msg="text"):
    time.sleep(min(len(msg_usuario) * 0.05, 3) + 2)
    
    dica_cross_sell = analisar_intencao(phone, msg_usuario)
    dados_calculadora = estimar_parcela(msg_usuario)
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        history = ler_historico(phone)
        chat = model.start_chat(history=history)
        
        prompt_final = f"""{SYSTEM_PROMPT}
        CONTEXTO:
        Cliente: {nome_cliente}
        Mensagem ({tipo_msg}): {msg_usuario}
        {dados_calculadora}
        {dica_cross_sell}
        Roberto:"""
        
        response = chat.send_message(prompt_final)
        texto_resp = response.text.strip()
        
        # Se a resposta tiver cálculo, garante que o link está lá
        if "R$" in texto_resp and "app" not in texto_resp.lower():
            texto_resp += f"\n\n📲 Faça sua simulação oficial aqui: {LINK_SIMULADOR}"

        time.sleep(min(len(texto_resp) * 0.05, 5))
        salvar_msg(phone, "model", texto_resp, nome_cliente)
        enviar_zap(phone, texto_resp)
    except: pass

# --- ROTAS DE CRON E API (MANTIDAS) ---
@app.route('/fix/raio_x', methods=['GET'])
def raio_x():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT status, COUNT(*) as qtd, AVG(score) as media_score FROM leads GROUP BY status")
        resumo = cur.fetchall()
        conn.close()
        return jsonify(resumo)
    except: return jsonify({"erro": "db"})

@app.route('/cron/aquecimento', methods=['GET'])
def cron_aquecimento():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT phone, nome FROM leads WHERE status = 'FILA_AQUECIMENTO' ORDER BY score DESC LIMIT 20")
    lote = cur.fetchall()
    conn.close()
    if not lote: return jsonify({"msg": "Vazia"})
    
    def worker(lista):
        conn_w = get_db_connection()
        cur_w = conn_w.cursor()
        for p, n in lista:
            try:
                msg = f"Olá {n}, Roberto aqui da ConsegSeguro. ☀️ Nossos grupos de consórcio rodaram essa semana com ótimas contemplações. Quer simular um valor sem compromisso?"
                enviar_zap(p, msg)
                cur_w.execute("UPDATE leads SET status = 'ATIVO', last_interaction = NOW() WHERE phone = %s", (p,))
                cur_w.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, NOW())", (p, 'model', msg))
                conn_w.commit()
                time.sleep(random.randint(40, 90))
            except: continue
        conn_w.close()
    threading.Thread(target=worker, args=(lote,)).start()
    return jsonify({"status": "V54 Iniciado"})

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
                if msg_type == 'conversation' or msg_type == 'extendedTextMessage':
                    content = b.get('data',{}).get('message',{}).get('conversation') or b.get('data',{}).get('message',{}).get('extendedTextMessage',{}).get('text')
                elif msg_type == 'audioMessage':
                    audio_url = b.get('data',{}).get('message',{}).get('audioMessage',{}).get('url') or b.get('data',{}).get('message',{}).get('base64')
                    if audio_url:
                        content = processar_audio_gemini(audio_url, p)
                        content = f"[Transcrição de Áudio]: {content}"
                        tipo_conteudo = "audio"
                if content:
                    salvar_msg(p, "user", content, n, tipo_conteudo)
                    threading.Thread(target=responder_chat_inteligente, args=(p, content, n, tipo_conteudo)).start()
        return jsonify({"status": "ok"}), 200
    except: return jsonify({"status": "error"}), 500

@app.route('/', methods=['GET'])
def health(): return jsonify({"status": "Roberto V54 - Consultor de Precisão"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
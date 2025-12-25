# VERSAO V59 - O ESTRATEGISTA (FUNIL PASSO A PASSO)
import os
import requests
import datetime
import time
import threading
import json
import random
import re
import psycopg2
import tempfile
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

# --- BANCO DE DADOS ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS messages 
                       (phone TEXT, role TEXT, content TEXT, timestamp TIMESTAMP)''')
        # Adicionamos colunas para guardar as respostas do cliente
        cur.execute('''CREATE TABLE IF NOT EXISTS leads 
                       (phone TEXT PRIMARY KEY, nome TEXT, status TEXT, 
                        last_interaction TIMESTAMP, origem TEXT, 
                        funnel_stage INTEGER DEFAULT 0, 
                        tags TEXT DEFAULT '', 
                        dados_extra TEXT DEFAULT '{}')''')
        conn.commit()
        conn.close()
        print("✅ V59: Máquina de Estados Ativa")
    except Exception as e:
        print(f"❌ Erro Banco: {e}")

init_db()

# --- AUXILIARES ---
def salvar_msg(phone, role, content, nome="Cliente"):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        now = datetime.datetime.now()
        cur.execute("INSERT INTO messages (phone, role, content, timestamp) VALUES (%s, %s, %s, %s)", 
                    (phone, role, content, now))
        if role == 'user':
            cur.execute("""
                INSERT INTO leads (phone, nome, status, last_interaction, origem) 
                VALUES (%s, %s, 'ATIVO', %s, 'Whatsapp')
                ON CONFLICT (phone) DO UPDATE 
                SET status = 'ATIVO', last_interaction = %s, nome = EXCLUDED.nome
            """, (phone, nome, now, now))
        conn.commit()
        conn.close()
    except: pass

def ler_historico(phone):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE phone = %s ORDER BY timestamp DESC LIMIT 14", (phone,))
        data = cur.fetchall()
        conn.close()
        return [{"role": row[0], "parts": [row[1]]} for row in reversed(data)]
    except: return []

def enviar_zap(telefone, texto):
    clean_phone = "".join(filter(str.isdigit, str(telefone)))
    if len(clean_phone) == 12 and clean_phone.startswith("55"):
        clean_phone = f"{clean_phone[:4]}9{clean_phone[4:]}"
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
    try: requests.post(url, json={"number": clean_phone, "text": texto}, headers=headers)
    except: pass

# --- 🧠 O CÉREBRO DO FUNIL (Raciocínio de Estado) ---

def extrair_dados_ia(texto_usuario, estagio_atual, dados_atuais):
    """
    Usa IA para verificar se o usuário respondeu a pergunta da fase.
    Retorna: (novo_estagio, dados_atualizados_json)
    """
    try:
        prompt_analise = f"""
        Analise a resposta do cliente.
        Estágio Atual: {estagio_atual}
        Dados já coletados: {dados_atuais}
        Última mensagem do cliente: "{texto_usuario}"

        OBJETIVOS POR ESTÁGIO:
        0: Abordagem inicial. Se cliente respondeu positivo, vá para 1.
        1: Tipo de bem (Imóvel, Carro, Moto, Pesados).
        2: Valor do crédito (R$).
        3: Valor da parcela confortável (R$).
        4: Tem lance, entrada ou FGTS?
        5: Objetivo (Pressa, Investimento, Aposentadoria).
        6: Fim (Já simulou).

        SAÍDA ESPERADA (JSON PURO):
        {{"avancar": true/false, "dado_extraido": "valor ou null", "resetar": false}}
        
        Se o cliente mudou de assunto radicalmente, retorne "resetar": true.
        Se ele respondeu a pergunta da fase, retorne "avancar": true e o dado.
        """
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        resp = model.generate_content(prompt_analise)
        analise = json.loads(resp.text.replace('```json','').replace('```','').strip())
        
        dados = json.loads(dados_atuais) if dados_atuais else {}
        
        if analise.get('resetar'):
            return 1, dados # Volta pro início se o cliente se perder
            
        if analise.get('avancar'):
            # Salva o dado da fase
            if estagio_atual == 1: dados['tipo'] = analise.get('dado_extraido')
            if estagio_atual == 2: dados['valor_credito'] = analise.get('dado_extraido')
            if estagio_atual == 3: dados['parcela_max'] = analise.get('dado_extraido')
            if estagio_atual == 4: dados['lance'] = analise.get('dado_extraido')
            if estagio_atual == 5: dados['objetivo'] = analise.get('dado_extraido')
            
            return estagio_atual + 1, dados
        
        return estagio_atual, dados # Não avançou (cliente enrolou ou teve dúvida)
        
    except:
        return estagio_atual, (json.loads(dados_atuais) if dados_atuais else {})

def gerar_simulacao_final(dados):
    # Lógica Matemática para o Gran Finale
    try:
        # Tenta limpar string de valor para float
        val_str = str(dados.get('valor_credito', '0')).lower().replace('k','000').replace('.','').replace('r$','')
        valor = float(re.search(r'\d+', val_str).group())
    except: valor = 0

    if valor == 0: return "Preciso que me confirme o valor para calcular."

    tipo = str(dados.get('tipo', 'imovel')).lower()
    
    # Parâmetros
    if 'car' in tipo or 'veic' in tipo:
        prazo = 80
        taxa = 0.15
        juros_banco = 0.021
    else:
        prazo = 180
        taxa = 0.22
        juros_banco = 0.011

    parcela_cons = (valor * (1 + taxa)) / prazo
    # Price simplificada
    parcela_banco = valor * (juros_banco * (1 + juros_banco)**prazo) / ((1 + juros_banco)**prazo - 1)
    
    economia = (parcela_banco * prazo) - (parcela_cons * prazo)

    return f"""
    📋 *PROPOSTA OFICIAL CONSEG*
    
    Baseado no seu perfil ({dados.get('objetivo', 'Planejamento')}):
    
    🎯 Crédito: R$ {valor:,.2f}
    ⏳ Prazo: {prazo} meses
    
    📉 *No Consórcio:* R$ {parcela_cons:,.2f}/mês
    📈 *No Financiamento:* ~R$ {parcela_banco:,.2f}/mês
    
    💰 *Economia estimada:* R$ {economia:,.2f}
    
    Considerando seu lance/FGTS ({dados.get('lance', 'Sem lance')}), podemos tentar uma contemplação acelerada.
    
    Faz sentido reservar essa carta agora?
    """

SYSTEM_PROMPTS_POR_FASE = {
    0: "Se apresente como Roberto da ConsegSeguro. Pergunte se a pessoa tem interesse em Imóveis ou Veículos hoje.",
    1: "O cliente quer comprar algo. Pergunte QUAL TIPO de bem (Imóvel, Carro, Caminhão)? Seja breve.",
    2: "Ok, sabemos o tipo. Pergunte QUAL O VALOR do crédito que ele precisa. (Ex: 300 mil, 50 mil).",
    3: "Sabemos o valor. Agora pergunte QUAL O VALOR DA PARCELA que fica confortável no bolso dele mensalmente.",
    4: "Pergunte se ele possui algum valor para LANCE ou, no caso de imóveis, se tem saldo de FGTS.",
    5: "Última pergunta: O objetivo é contemplação rápida (tem pressa) ou investimento de médio prazo?",
    6: "Apenas apresente a simulação abaixo. Não pergunte mais nada, chame para o fechamento."
}

def responder_chat_inteligente(phone, msg_usuario, nome_cliente):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Pega Estado Atual
    cur.execute("SELECT funnel_stage, dados_extra FROM leads WHERE phone = %s", (phone,))
    res = cur.fetchone()
    if not res: 
        estagio = 0
        dados_db = "{}"
    else:
        estagio = res[0] if res[0] is not None else 0
        dados_db = res[1] if res[1] else "{}"

    # 2. Analisa se avança de fase
    novo_estagio, novos_dados = extrair_dados_ia(msg_usuario, estagio, dados_db)
    
    # 3. Atualiza Banco
    novos_dados_str = json.dumps(novos_dados)
    cur.execute("UPDATE leads SET funnel_stage = %s, dados_extra = %s WHERE phone = %s", 
                (novo_estagio, novos_dados_str, phone))
    conn.commit()
    cur.close()
    conn.close()

    # 4. Gera Resposta baseada na FASE
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        history = ler_historico(phone)
        chat = model.start_chat(history=history)
        
        instrucao_fase = SYSTEM_PROMPTS_POR_FASE.get(novo_estagio, "Ajude o cliente.")
        
        simulacao_txt = ""
        if novo_estagio == 6:
            simulacao_txt = gerar_simulacao_final(novos_dados)
        
        prompt_final = f"""
        IDENTIDADE: Roberto, Consultor Sênior ConsegSeguro.
        FASE ATUAL DO ATENDIMENTO: {novo_estagio}/6
        
        DADOS COLETADOS: {novos_dados_str}
        
        SUA MISSÃO AGORA: {instrucao_fase}
        
        {simulacao_txt}
        
        REGRAS:
        - Siga estritamente a missão da fase.
        - Não pule etapas.
        - Seja profissional e empático.
        - Se o cliente tiver dúvida, responda a dúvida e repita a pergunta da fase.
        """
        
        response = chat.send_message(prompt_final)
        texto_resp = response.text.strip()
        
        salvar_msg(phone, "model", texto_resp, nome_cliente)
        enviar_zap(phone, texto_resp)
        
    except Exception as e:
        print(f"Erro IA: {e}")

# --- PROCESSAMENTO DE ÁUDIO ---
def processar_audio(phone, audio_url, nome_cliente):
    # Passa o áudio como texto simulado para o motor de funil processar
    responder_chat_inteligente(phone, "[O cliente enviou um áudio. Ouça e extraia a informação da fase atual]", nome_cliente)

# --- ROTAS ---
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_hook():
    try:
        b = request.json
        if b.get('event') == 'messages.upsert':
            data = b.get('data', {})
            key = data.get('key', {})
            if not key.get('fromMe'):
                phone = key.get('remoteJid', '').split('@')[0]
                name = data.get('pushName', 'Cliente')
                
                if data.get('messageType') == 'conversation':
                    txt = data.get('message', {}).get('conversation')
                    if txt: threading.Thread(target=responder_chat_inteligente, args=(phone, txt, name)).start()
                elif data.get('messageType') == 'extendedTextMessage':
                    txt = data.get('message', {}).get('extendedTextMessage',{}).get('text')
                    if txt: threading.Thread(target=responder_chat_inteligente, args=(phone, txt, name)).start()
                elif data.get('messageType') == 'audioMessage':
                     url = data.get('message', {}).get('audioMessage', {}).get('url')
                     if url: threading.Thread(target=processar_audio, args=(phone, url, name)).start()
                     
        return jsonify({"status": "ok"}), 200
    except: return jsonify({"error": "err"}), 500

@app.route('/cron/aquecimento', methods=['GET'])
def processar_aquecimento():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT phone, nome FROM leads WHERE status = 'FILA_AQUECIMENTO' LIMIT 20")
    lote = cur.fetchall()
    
    if not lote: 
        conn.close()
        return jsonify({"msg": "Fila vazia"})

    def worker(lista):
        cx = get_db_connection()
        cux = cx.cursor()
        for p, n in lista:
            # Reseta o funil para 0 e manda mensagem inicial
            msg = f"Olá {n}, tudo bem? Aqui é o Roberto da ConsegSeguro. ☀️ Estamos selecionando clientes para os novos grupos de crédito hoje. Você tem interesse em Imóvel ou Veículo?"
            enviar_zap(p, msg)
            salvar_msg(p, "model", msg, n)
            
            cux.execute("UPDATE leads SET status = 'ATIVO', funnel_stage = 1 WHERE phone = %s", (p,))
            cx.commit()
            time.sleep(random.randint(40, 80))
        cux.close()
        cx.close()

    threading.Thread(target=worker, args=(lote,)).start()
    return jsonify({"status": "Lote V59 (Funil) Iniciado"})

@app.route('/importar_leads', methods=['POST'])
def importar_leads():
    # Mantido igual
    lista = request.json
    c = 0
    conn = get_db_connection()
    cur = conn.cursor()
    for l in lista:
        try:
            p = "".join(filter(str.isdigit, str(l.get('phone'))))
            n = l.get('nome', 'Investidor')
            # Reinicia leads importados na etapa 0
            cur.execute("INSERT INTO leads (phone, nome, status, last_interaction, origem, funnel_stage) VALUES (%s, %s, 'FILA_AQUECIMENTO', NOW(), 'Base', 0) ON CONFLICT (phone) DO UPDATE SET status='FILA_AQUECIMENTO', funnel_stage=0", (p, n))
            c += 1
        except: pass
    conn.commit()
    conn.close()
    return jsonify({"qtd": c})

@app.route('/', methods=['GET'])
def health(): return jsonify({"status": "Roberto V59 - Estrategista de Funil"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
import psycopg2
import os
import requests
from datetime import datetime

# Configurações (Pegue do seu .env ou Render)
DATABASE_URL = "SUA_DATABASE_URL_DO_NEON"
EVOLUTION_URL = "SUA_EVOLUTION_URL"
EVOLUTION_APIKEY = "SUA_EVOLUTION_APIKEY"
INSTANCE = "consorcio"
BOSS_PHONE = "5561999949724"

def gerar_relatorio():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 1. Total de Leads na Base
        cur.execute("SELECT COUNT(DISTINCT phone) FROM episode_memory WHERE category = 'ads_import'")
        total_leads = cur.fetchone()[0]

        # 2. Leads abordados hoje
        cur.execute("SELECT COUNT(DISTINCT phone) FROM episode_memory WHERE timestamp >= CURRENT_DATE")
        abordados_hoje = cur.fetchone()[0]

        # 3. Último lead processado
        cur.execute("SELECT phone, timestamp FROM episode_memory ORDER BY timestamp DESC LIMIT 1")
        ultimo = cur.fetchone()
        
        msg = (
            f"📊 *RELATÓRIO DE OPERAÇÃO - CONSEG*\n"
            f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"✅ *Base Total:* {total_leads} leads importados.\n"
            f"🚀 *Abordagens Hoje:* {abordados_hoje} leads.\n"
            f"🏁 *Status:* Em progresso...\n\n"
            f"📱 *Último contato:* {ultimo[0]} às {ultimo[1].strftime('%H:%M')}\n"
            f"--------------------------------\n"
            f"O Arquiteto Estóico segue trabalhando."
        )

        # Envio via Evolution API
        url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
        payload = {"number": BOSS_PHONE, "text": msg}
        headers = {"apikey": EVOLUTION_APIKEY}
        requests.post(url, json=payload, headers=headers)
        
        print("✅ Relatório enviado para o seu número pessoal!")
        conn.close()

    except Exception as e:
        print(f"❌ Erro ao gerar relatório: {e}")

if __name__ == "__main__":
    gerar_relatorio()
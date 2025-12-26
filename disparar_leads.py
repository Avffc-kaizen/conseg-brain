import pandas as pd
import requests
import time
import random

# CONFIGURAÇÕES
WEBHOOK_ADS_URL = "https://conseg-brain.onrender.com/webhook/ads"
CSV_FILE = "Relatório de formulário de lead (2).csv"

def iniciar_prospeccao():
    df = pd.read_csv(CSV_FILE)
    print(f"🚀 Iniciando prospecção de {len(df)} leads...")

    for index, row in df.iterrows():
        # Limpeza do Telefone
        phone = str(row['PHONE_NUMBER']).replace('.0', '').replace('+', '').strip()
        nome = f"{row['FIRST_NAME']} {row['LAST_NAME']}".strip()
        categoria = str(row.get('em_qual_categoria_você_tem_interesse?', 'Geral'))

        payload = {
            "phone": phone,
            "name": nome,
            "ad_name": f"Carga Terminal - {categoria}"
        }

        try:
            # Envia para o Roberto processar
            response = requests.post(WEBHOOK_ADS_URL, json=payload)
            
            if response.status_code == 200:
                print(f"✅ Lead {index+1}/{len(df)}: {nome} ({phone}) enviado para o Roberto.")
            else:
                print(f"⚠️ Erro ao enviar {nome}: {response.text}")

        except Exception as e:
            print(f"❌ Falha de conexão: {e}")

        # --- O SEGREDO DO DISPARO 1 A 1 ---
        # Intervalo entre leads para aquecimento do chip (30 a 90 segundos)
        delay = random.randint(30, 90)
        print(f"⏳ Aguardando {delay} segundos para o próximo lead...")
        time.sleep(delay)

if __name__ == "__main__":
    iniciar_prospeccao()
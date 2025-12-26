import pandas as pd
import requests
import time
import random

# CONFIGURAÇÕES
WEBHOOK_ADS_URL = "https://conseg-brain.onrender.com/webhook/ads"
CSV_FILE = "Relatório de formulário de lead (2).csv"

def continuar_prospeccao():
    df = pd.read_csv(CSV_FILE)
    
    # SALTA OS PRIMEIROS 35 LEADS (iloc[35:])
    leads_restantes = df.iloc[35:]
    
    print(f"🚀 Retomando prospecção a partir do lead 35...")
    print(f"📈 Faltam {len(leads_restantes)} leads para processar.")

    for index, row in leads_restantes.iterrows():
        phone = str(row['PHONE_NUMBER']).replace('.0', '').replace('+', '').strip()
        nome = f"{row['FIRST_NAME']} {row['LAST_NAME']}".strip()
        categoria = str(row.get('em_qual_categoria_você_tem_interesse?', 'Geral'))

        payload = {
            "phone": phone,
            "name": nome,
            "ad_name": f"Carga Terminal V2 - {categoria}"
        }

        try:
            response = requests.post(WEBHOOK_ADS_URL, json=payload)
            if response.status_code == 200:
                print(f"✅ Lead {index + 1}: {nome} ({phone}) enviado.")
            else:
                print(f"⚠️ Erro no lead {nome}: {response.text}")
        except Exception as e:
            print(f"❌ Falha: {e}")

        # Intervalo Seguro: Entre 45 a 120 segundos
        delay = random.randint(45, 120)
        print(f"⏳ Próximo lead em {delay}s...")
        time.sleep(delay)

if __name__ == "__main__":
    continuar_prospeccao()
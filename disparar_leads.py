import pandas as pd
import requests
import time
import random

# CONFIGURAÇÕES
WEBHOOK_ADS_URL = "https://conseg-brain.onrender.com/webhook/ads"
CSV_FILE = "Relatório de formulário de lead (2).csv"

def continuar_prospeccao():
    try:
        df = pd.read_csv(CSV_FILE)
        
        # --- ATUALIZAÇÃO DE RETOMADA ---
        # Já foram disparados 63 leads.
        # Começamos agora do índice 63 (que é o Lead 64 na contagem)
        leads_restantes = df.iloc[63:] 
        
        print(f"🚀 Retomando prospecção a partir do Lead 64...")
        print(f"📈 Faltam {len(leads_restantes)} leads para processar.")

        for index, row in leads_restantes.iterrows():
            # Tratamento de dados
            phone = str(row['PHONE_NUMBER']).replace('.0', '').replace('+', '').strip()
            nome = f"{row['FIRST_NAME']} {row['LAST_NAME']}".strip()
            categoria = str(row.get('em_qual_categoria_você_tem_interesse?', 'Geral'))

            payload = {
                "phone": phone,
                "name": nome,
                "ad_name": f"Retomada V1017 - {categoria}"
            }

            try:
                response = requests.post(WEBHOOK_ADS_URL, json=payload)
                if response.status_code == 200:
                    # index + 1 mostra o número real da linha
                    print(f"✅ Lead {index + 1}: {nome} ({phone}) enviado.")
                else:
                    print(f"⚠️ Erro no lead {nome}: {response.text}")
            except Exception as e:
                print(f"❌ Falha de conexão: {e}")

            # Intervalo de segurança (delay)
            delay = random.randint(45, 120)
            print(f"⏳ Próximo lead em {delay}s...")
            time.sleep(delay)
            
    except FileNotFoundError:
        print(f"❌ Erro: O arquivo '{CSV_FILE}' não foi encontrado.")
    except Exception as e:
        print(f"❌ Erro fatal: {e}")

if __name__ == "__main__":
    continuar_prospeccao()
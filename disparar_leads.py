import pandas as pd
import requests
import time
import random

# CONFIGURAÇÕES
WEBHOOK_ADS_URL = "https://conseg-brain.onrender.com/webhook/ads"
# Certifique-se de que o nome do arquivo está correto
CSV_FILE = "Relatório de formulário de lead (2).csv"

def continuar_prospeccao():
    try:
        df = pd.read_csv(CSV_FILE)
        
        # --- ATUALIZAÇÃO DE RETOMADA ---
        # Já foram disparados 51 leads.
        # Começamos agora do índice 51 (que é o Lead 52 na contagem humana)
        leads_restantes = df.iloc[51:] 
        
        print(f"🚀 Retomando prospecção a partir do Lead 52...")
        print(f"📈 Faltam {len(leads_restantes)} leads para processar.")

        for index, row in leads_restantes.iterrows():
            # Tratamento de dados para evitar erros
            phone = str(row['PHONE_NUMBER']).replace('.0', '').replace('+', '').strip()
            nome = f"{row['FIRST_NAME']} {row['LAST_NAME']}".strip()
            
            # Pega a categoria se existir, senão define padrão
            categoria = str(row.get('em_qual_categoria_você_tem_interesse?', 'Geral'))

            payload = {
                "phone": phone,
                "name": nome,
                "ad_name": f"Retomada V1016 - {categoria}"
            }

            try:
                response = requests.post(WEBHOOK_ADS_URL, json=payload)
                if response.status_code == 200:
                    # index + 1 mostra o número real da linha no Excel
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
        print(f"❌ Erro: O arquivo '{CSV_FILE}' não foi encontrado na pasta.")
    except Exception as e:
        print(f"❌ Erro fatal: {e}")

if __name__ == "__main__":
    continuar_prospeccao()
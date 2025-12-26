import requests
import csv
import json
import re

# --- CONFIGURAÇÃO ---
ARQUIVO_CSV = "Relatório de formulário de lead (1).csv"
URL_API = "https://conseg-brain.onrender.com/importar_leads"

def limpar_telefone(telefone):
    # Remove tudo que não for número
    nums = "".join(filter(str.isdigit, str(telefone)))
    
    # Se começar com 55 (Brasil) e for longo, mantém. Se não tiver 55, adiciona.
    if len(nums) <= 11:
        nums = "55" + nums
    
    return nums

def carregar_do_csv():
    leads = []
    try:
        # Tenta ler com encoding utf-8 (padrão web) ou cp1252 (padrão excel brasil)
        try:
            f = open(ARQUIVO_CSV, mode='r', encoding='utf-8-sig')
        except:
            f = open(ARQUIVO_CSV, mode='r', encoding='cp1252')
            
        reader = csv.DictReader(f)
        
        # Detecta os nomes das colunas automaticamente (padrão Facebook ou Português)
        headers = reader.fieldnames
        col_nome = next((h for h in headers if 'name' in h.lower() or 'nome' in h.lower()), None)
        col_tel = next((h for h in headers if 'phone' in h.lower() or 'tel' in h.lower()), None)

        if not col_nome or not col_tel:
            print(f"❌ Erro: Não achei colunas de Nome ou Telefone. Colunas encontradas: {headers}")
            return []

        print(f"🔍 Lendo colunas: Nome='{col_nome}' | Telefone='{col_tel}'")

        for row in reader:
            nome_raw = row[col_nome]
            tel_raw = row[col_tel]
            
            if tel_raw:
                leads.append({
                    "nome": nome_raw,
                    "phone": limpar_telefone(tel_raw)
                })
        
        f.close()
        return leads

    except FileNotFoundError:
        print(f"❌ Arquivo '{ARQUIVO_CSV}' não encontrado na pasta.")
        return []
    except Exception as e:
        print(f"❌ Erro ao ler CSV: {e}")
        return []

# --- EXECUÇÃO ---
print(f"📂 Lendo arquivo: {ARQUIVO_CSV}...")
lista_leads = carregar_do_csv()

if lista_leads:
    print(f"🚀 Enviando {len(lista_leads)} leads reais para o ROBERTO (V54)...")
    try:
        response = requests.post(URL_API, json=lista_leads, timeout=60)
        if response.status_code == 200:
            print("✅ SUCESSO! Base importada para a Nuvem (Postgres).")
            print(f"Resposta: {response.json()}")
        else:
            print(f"❌ Erro no Servidor: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erro de Conexão: {e}")
else:
    print("⚠️ Nenhum lead encontrado para enviar.")
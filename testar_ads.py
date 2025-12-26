import requests
import json

# URL do seu servidor no Render (substitua pela sua URL real)
URL_WEBHOOK = "https://conseg-brain.onrender.com/webhook/ads"

# Dados simulados do Lead (exatamente como o Zapier deve enviar)
data = {
    "phone": "5561999949724", # Use o seu número para testar
    "name": "Lead Teste V1000",
    "ad_name": "Google Ads - Consórcio Imobiliário"
}

def disparar_teste():
    print(f"🚀 Enviando lead de teste para {URL_WEBHOOK}...")
    try:
        response = requests.post(URL_WEBHOOK, json=data, timeout=10)
        if response.status_code == 200:
            print("✅ SUCESSO! O Roberto recebeu o lead e deve iniciar o atendimento no WhatsApp.")
        else:
            print(f"❌ ERRO {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ FALHA DE CONEXÃO: {e}")

if __name__ == "__main__":
    disparar_teste()
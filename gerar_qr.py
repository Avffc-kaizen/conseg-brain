import os
import requests
import base64
import time

# --- CONFIGURAÇÕES COMPLETAS ---
EVOLUTION_URL = "http://89.117.59.255:8080"
EVOLUTION_APIKEY = "442998D0-3796-4191-B7C9-03F64560E584"
INSTANCE = "consorcio"

def gerar_qr():
    # Limpeza básica
    url_api = EVOLUTION_URL.strip().rstrip('/')
    api_key = EVOLUTION_APIKEY.strip()
    headers = {"apikey": api_key}
    
    print(f"🔌 Conectando em: {url_api}")
    print("🔄 1. Tentando limpar sessão antiga...")
    
    try:
        # Tenta desconectar caso esteja travado
        requests.delete(f"{url_api}/instance/logout/{INSTANCE}", headers=headers)
        time.sleep(2)
    except: pass

    print("📲 2. Solicitando novo QR Code...")
    try:
        url = f"{url_api}/instance/connect/{INSTANCE}"
        response = requests.get(url, headers=headers)
        
        print(f"🔎 Status da Resposta: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Pega o base64 do QR Code
            qr_base64 = data.get('base64') or data.get('qrcode')
            
            if qr_base64:
                qr_base64 = qr_base64.replace("data:image/png;base64,", "")
                with open("qrcode_whatsapp.png", "wb") as fh:
                    fh.write(base64.b64decode(qr_base64))
                
                print("\n✅ SUCESSO! Abra o arquivo 'qrcode_whatsapp.png' na pasta e escaneie!")
            else:
                if "already connected" in str(data):
                     print("\n✅ JÁ CONECTADO! Seu WhatsApp já está online.")
                else:
                    print(f"⚠️ Resposta da API: {data}")
        else:
            print(f"❌ Erro ({response.status_code}): {response.text}")
            
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")

if __name__ == "__main__":
    gerar_qr()
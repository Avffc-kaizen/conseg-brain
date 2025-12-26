import os
import psycopg2

# PEGAR A URL DO SEU AMBIENTE (Se não tiver no .env local, cole a URL do NEON direto aqui nas aspas)
# Exemplo: DATABASE_URL = "postgres://neondb_owner:..."
DATABASE_URL = os.getenv("DATABASE_URL", "COLE_SUA_URL_DO_NEON_AQUI_SE_DER_ERRO")

def atualizar_tabelas():
    try:
        print("🔌 Conectando ao Neon...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        print("🔨 Adicionando coluna 'followup_stage'...")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS followup_stage INTEGER DEFAULT 0;")
        
        print("🔨 Adicionando coluna 'dados_extra'...")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS dados_extra TEXT DEFAULT '{}';")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ SUCESSO! Banco preparado para V60.")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        print("DICA: Se deu erro de senha/conexão, abra o arquivo e cole sua URL do Neon na linha 6.")

if __name__ == "__main__":
    atualizar_tabelas()
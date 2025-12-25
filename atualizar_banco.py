import psycopg2
import os

# URL do Banco Neon (Copiada do seu projeto)
DATABASE_URL = "postgresql://neondb_owner:npg_3k5zHouqFVLr@ep-lucky-hat-ah3mk8fe-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

def realizar_cirurgia():
    print("🏥 Iniciando cirurgia no banco de dados...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # 1. Adicionar coluna funnel_stage
        print("💉 Injetando coluna 'funnel_stage'...")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS funnel_stage INTEGER DEFAULT 0;")
        
        # 2. Adicionar coluna dados_extra
        print("💉 Injetando coluna 'dados_extra'...")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS dados_extra TEXT DEFAULT '{}';")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ SUCESSO! O banco foi atualizado para a V59.")
        
    except Exception as e:
        print(f"❌ Erro na cirurgia: {e}")

if __name__ == "__main__":
    realizar_cirurgia()
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def migrar():
    commands = [
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone TEXT NOT NULL,
            state JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS episode_memory (
            id SERIAL PRIMARY KEY,
            phone TEXT NOT NULL,
            key_fact TEXT,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS audio_url TEXT;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sentiment_score FLOAT;"
    ]
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    for command in commands:
        try:
            cur.execute(command)
            print(f"Executado: {command[:30]}...")
        except Exception as e:
            print(f"Erro: {e}")
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Migração V1000 Concluída!")

if __name__ == "__main__":
    migrar()
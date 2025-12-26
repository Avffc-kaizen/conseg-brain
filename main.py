# VERSAO V85 - OPERAÇÃO FORÇADA (08:00 ÀS 22:00)
import os
import datetime
import time
import threading
from flask import Flask, jsonify

app = Flask(__name__)

# --- CONFIGURAÇÃO DE HORÁRIO DE TRABALHO ---
HORA_INICIO = 8
HORA_FIM = 22

def is_horario_comercial():
    """Verifica se o Roberto deve estar ativo para proatividade agora"""
    agora = datetime.datetime.now().hour
    return HORA_INICIO <= agora < HORA_FIM

def agenda_seguimento_proativo():
    while True:
        try:
            agora = datetime.datetime.now()
            
            # Se estiver fora do horário, calcula a espera até as 08:00
            if agora.hour < HORA_INICIO:
                proxima = agora.replace(hour=HORA_INICIO, minute=0, second=0)
            elif agora.hour >= HORA_FIM:
                proxima = (agora + datetime.timedelta(days=1)).replace(hour=HORA_INICIO, minute=0, second=0)
            else:
                # Se estiver dentro do horário, executa a rotina de Nutrição
                print("Iniciando varredura de aquecimento de leads...")
                processar_nurturing_diario()
                # Após processar, agenda para o dia seguinte às 08:00
                proxima = (agora + datetime.timedelta(days=1)).replace(hour=HORA_INICIO, minute=0, second=0)

            tempo_espera = (proxima - agora).total_seconds()
            time.sleep(tempo_espera)
            
        except Exception as e:
            print(f"Erro na Cron V85: {e}")
            time.sleep(600)

# --- INTEGRAÇÃO DE CONTEÚDO E MINERAÇÃO ---
# O Roberto utilizará os dados minerados da Porto (ex: G-4050 a 32%)
# E os vídeos institucionais (ex: 'Nasceu para Vencer')

def enviar_insight_proativo(phone, nome):
    if not is_horario_comercial():
        return # Garante que não incomode o lead de madrugada

    # Seleção de conteúdo estratégico
    materiais = [
        f"o vídeo 'Nasceu para Vencer' da ConsegSeguro: https://www.youtube.com/watch?v=89nuev1AUFA",
        "nossa análise de investidores inteligentes: https://www.youtube.com/watch?v=U0uGM0rq9Ek",
        "a última mineração de lances da Porto Seguro (identificamos grupos com média de 32%)."
    ]
    # ... (lógica de envio via Evolution API)
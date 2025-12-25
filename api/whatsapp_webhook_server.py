"""
Standalone Flask server for WhatsApp webhook integration.

This server handles incoming WhatsApp messages from WAHA and processes them
synchronously without Celery dependency.

Features:
- POST /api/v1/whatsapp/webhook - Receive and process WhatsApp messages
- GET /api/v1/whatsapp/webhook - Health check endpoint
- GET /health - Server health check
- Synchronous message processing with AI response
- Direct httpx integration for sending responses via WAHA
- OpenRouter AI integration for intelligent responses
"""

import logging
import os
import random
import re
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
import uuid

from flask import Flask, jsonify, request
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/whatsapp_webhook.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5002"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
DEBUG_MODE = os.getenv("DEBUG", "true").lower() == "true"

# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "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"
)

# WAHA configuration
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "broker-waha-key-2024")

# Humanization delays (in seconds)
TYPING_DELAY_MIN = 1.5      # Minimo antes de comecar a "digitar"
TYPING_DELAY_MAX = 4.0      # Maximo antes de comecar a "digitar"
CHARS_PER_SECOND = 6.0      # Velocidade de digitacao humana (~60 WPM)

# Message buffer configuration (for aggregating consecutive messages)
MESSAGE_BUFFER_DELAY = 3.0  # Segundos para aguardar mais mensagens antes de processar

# Statistics
stats = {
    "messages_received": 0,
    "messages_processed": 0,
    "messages_failed": 0,
    "server_started_at": datetime.utcnow().isoformat()
}

# In-memory conversation history storage
# Key: conversation_id (whatsapp_5585999999999@c.us)
# Value: list of messages [{"role": "user/assistant", "content": "..."}]
conversation_history: dict[str, list[dict]] = {}

# Max messages to keep per conversation (to avoid token overflow)
MAX_HISTORY_MESSAGES = 20

# Message buffer for aggregating consecutive messages
# Key: from_number
# Value: {"messages": [...], "timer": Timer, "session": str}
message_buffer: dict[str, dict] = {}
message_buffer_lock = threading.Lock()

# Scheduled visits storage (MVP in-memory)
# Key: visit_id (uuid string)
# Value: visit dict
scheduled_visits: dict[str, dict] = {}

# Selected property per conversation (to track which property was selected before scheduling)
# Key: conversation_id
# Value: property_info dict
selected_property_context: dict[str, dict] = {}

# Broker WhatsApp number for notifications (Reno Alencar - socio)
BROKER_WHATSAPP_NUMBER = os.getenv("BROKER_WHATSAPP_NUMBER", "558596227722@c.us")

# SQLite database for landing page leads
DATABASE_PATH = os.getenv("LANDING_DB_PATH", "/tmp/landing_leads.db")

# Landing page leads context (in-memory)
# Key: conversation_id
# Value: {lead_id, property, is_landing_page, ...}
landing_lead_context: dict[str, dict] = {}

# Follow-up timers for proactive messaging
# Key: lead_id
# Value: threading.Timer
followup_timers: dict[int, threading.Timer] = {}

# ============================================
# COLD LEAD FOLLOW-UP SYSTEM
# ============================================
# Timers para leads que pararam de responder
# Key: conversation_id (ex: whatsapp_5585999999999@c.us)
# Value: {timer, tier, last_agent_response, scheduled_at}
cold_lead_timers: dict[str, dict] = {}

# Sequência de follow-ups progressivos (em segundos)
COLD_LEAD_FOLLOWUP_TIERS = [
    1800,     # Tier 1: 30 minutos
    7200,     # Tier 2: 2 horas
    86400,    # Tier 3: 24 horas (1 dia)
    259200,   # Tier 4: 72 horas (3 dias)
    604800,   # Tier 5: 168 horas (7 dias)
]

# Mensagens personalizadas para cada tier
COLD_LEAD_MESSAGES = {
    0: "Oi! Vi que voce ficou interessado em imoveis. Posso ajudar com mais informacoes ou agendar uma visita?",
    1: "Ola novamente! Ainda esta procurando imovel? Estou a disposicao para ajudar.",
    2: "Bom dia! Passando para saber se ainda tem interesse em encontrar seu imovel ideal.",
    3: "Oi! Faz alguns dias que conversamos. Surgiu algum imovel novo que pode te interessar. Quer ver?",
    4: "Ola! Ainda procurando imovel? Temos novas opcoes que podem combinar com voce.",
}


# ============================================
# VISIT FOLLOW-UP FUNCTIONS
# ============================================

def lead_has_scheduled_visit(lead_number: str, real_phone: str = None) -> dict | None:
    """
    Verifica se lead já tem visita agendada e retorna a visita.
    Busca primeiro em memoria, depois no banco de dados.

    Args:
        lead_number: Numero do lead (com @c.us ou @lid)
        real_phone: Numero real do telefone (sem sufixo)

    Returns:
        Visit dict se encontrou, None se não
    """
    # 1. Primeiro busca em memoria (rapido, visitas recentes)
    for visit_id, visit in scheduled_visits.items():
        # Verifica por lead_number
        if visit.get("lead_number") == lead_number:
            return visit
        # Verifica por real_phone nos lead_data
        if real_phone:
            visit_phone = visit.get("lead_data", {}).get("phone")
            if visit_phone and (visit_phone == real_phone or visit_phone in real_phone or real_phone in str(visit_phone)):
                return visit

    # 2. Se nao encontrou em memoria, busca no banco de dados
    db_visit = get_active_visit_from_db(lead_number, real_phone)
    if db_visit:
        # Carrega para memoria para proximas consultas
        scheduled_visits[db_visit["id"]] = db_visit
        logger.info(f"Loaded visit {db_visit['id']} from database into memory")
        return db_visit

    return None


def is_confirmation_response(message: str) -> bool:
    """Verifica se mensagem é resposta de confirmação de visita."""
    keywords = ["sim", "não", "nao", "confirmo", "cancela", "vou", "irei", "confirmar", "cancelar"]
    message_lower = message.lower().strip()
    # Resposta curta com keyword
    return len(message_lower) < 50 and any(k in message_lower for k in keywords)


def extract_feedback_score(message: str) -> int | None:
    """Extrai nota de 1-5 da mensagem."""
    match = re.search(r'\b([1-5])\b', message)
    if match:
        return int(match.group(1))
    return None


def notify_broker_lead_confirmed(visit: dict):
    """Notifica corretor que lead confirmou presença."""
    lead_name = visit.get("lead_data", {}).get("name", "Lead")
    message = f"Lead {lead_name} CONFIRMOU presenca para visita #{visit['id']} as {visit.get('scheduled_time', 'horario agendado')}."
    send_waha_message_sync(visit.get("session", "corretores"), BROKER_WHATSAPP_NUMBER, message)
    logger.info(f"Notified broker about lead confirmation for visit #{visit['id']}")


def send_lead_confirmation_request(visit_id: str):
    """Envia mensagem pedindo confirmação ao lead no dia da visita."""
    visit = scheduled_visits.get(visit_id)
    if not visit or visit.get("status") == "cancelled":
        logger.info(f"Skipping lead confirmation for visit #{visit_id} - cancelled or not found")
        return

    if visit.get("lead_confirmed"):
        logger.info(f"Lead already confirmed for visit #{visit_id}")
        return

    message = f"Bom dia! Sua visita esta marcada para hoje as {visit.get('scheduled_time', 'horario agendado')}. Confirma presenca? (Sim/Nao)"
    send_waha_message_sync(visit.get("session", "corretores"), visit["lead_number"], message)
    visit["confirmation_sent"] = True
    logger.info(f"Sent lead confirmation request for visit #{visit_id}")


def send_broker_confirmation_request(visit_id: str):
    """Envia mensagem pedindo confirmação ao corretor no dia da visita."""
    visit = scheduled_visits.get(visit_id)
    if not visit or visit.get("status") == "cancelled":
        logger.info(f"Skipping broker confirmation for visit #{visit_id} - cancelled or not found")
        return

    lead_name = visit.get("lead_data", {}).get("name", "Lead")
    property_info = visit.get("property_info", {})
    property_title = property_info.get("title", "Imovel")

    message = f"Bom dia! Visita #{visit['id']} com {lead_name} as {visit.get('scheduled_time', 'horario agendado')}.\nImovel: {property_title}\nConfirma disponibilidade? (Sim/Nao)"
    send_waha_message_sync(visit.get("session", "corretores"), BROKER_WHATSAPP_NUMBER, message)
    visit["broker_confirmation_sent"] = True
    logger.info(f"Sent broker confirmation request for visit #{visit_id}")


def send_feedback_request(visit_id: str):
    """Envia mensagem pedindo feedback ao lead após visita."""
    visit = scheduled_visits.get(visit_id)
    if not visit or visit.get("status") == "cancelled":
        logger.info(f"Skipping feedback request for visit #{visit_id} - cancelled or not found")
        return

    if visit.get("feedback_requested"):
        logger.info(f"Feedback already requested for visit #{visit_id}")
        return

    message = "Como foi sua experiencia na visita? De 1 a 5, qual nota voce daria para o atendimento do corretor?"
    send_waha_message_sync(visit.get("session", "corretores"), visit["lead_number"], message)
    visit["feedback_requested"] = True
    logger.info(f"Sent feedback request for visit #{visit_id}")


def schedule_visit_followups(visit_id: str):
    """
    Agenda todos os follow-ups para uma visita:
    1. Confirmação com lead (manhã do dia ou 2h antes)
    2. Confirmação com corretor (mesmo horário)
    3. Feedback após visita (2 horas depois)
    """
    visit = scheduled_visits.get(visit_id)
    if not visit:
        logger.warning(f"Cannot schedule follow-ups - visit #{visit_id} not found")
        return

    # Obter datetime da visita
    visit_dt = visit.get("scheduled_datetime")
    if not visit_dt:
        # Tentar construir a partir de date/time strings
        try:
            date_str = visit.get("scheduled_date", "")
            time_str = visit.get("scheduled_time", "10:00")
            if "/" in date_str:
                day, month, year = date_str.split("/")
                if len(year) == 2:
                    year = "20" + year
                hour, minute = time_str.replace("h", ":").split(":")[:2]
                minute = minute if minute else "00"
                visit_dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
                visit["scheduled_datetime"] = visit_dt
        except Exception as e:
            logger.warning(f"Could not parse visit datetime for #{visit_id}: {e}")
            return

    now = datetime.now()

    # Inicializar lista de timers se não existir
    if "follow_up_timers" not in visit:
        visit["follow_up_timers"] = []

    # 1. Confirmação com lead (manhã do dia, ou 2h antes se visita muito cedo)
    if visit_dt.hour <= 10:  # Visita antes das 10h
        lead_confirm_time = visit_dt - timedelta(hours=2)
    else:
        lead_confirm_time = visit_dt.replace(hour=8, minute=0, second=0, microsecond=0)

    if lead_confirm_time > now:
        delay = (lead_confirm_time - now).total_seconds()
        timer = threading.Timer(delay, send_lead_confirmation_request, args=[visit_id])
        timer.daemon = True
        timer.start()
        visit["follow_up_timers"].append(("lead_confirm", timer))
        logger.info(f"Scheduled lead confirmation for visit #{visit_id} at {lead_confirm_time} (in {delay/3600:.1f}h)")

    # 2. Confirmação com corretor (mesmo horário + 1 min para não enviar simultaneamente)
    broker_confirm_time = lead_confirm_time + timedelta(minutes=1)
    if broker_confirm_time > now:
        delay = (broker_confirm_time - now).total_seconds()
        timer = threading.Timer(delay, send_broker_confirmation_request, args=[visit_id])
        timer.daemon = True
        timer.start()
        visit["follow_up_timers"].append(("broker_confirm", timer))
        logger.info(f"Scheduled broker confirmation for visit #{visit_id}")

    # 3. Feedback após visita (2 horas depois)
    feedback_time = visit_dt + timedelta(hours=2)
    if feedback_time > now:
        delay = (feedback_time - now).total_seconds()
        timer = threading.Timer(delay, send_feedback_request, args=[visit_id])
        timer.daemon = True
        timer.start()
        visit["follow_up_timers"].append(("feedback", timer))
        logger.info(f"Scheduled feedback request for visit #{visit_id} at {feedback_time} (in {delay/3600:.1f}h)")


# ============================================
# DATABASE FUNCTIONS FOR LANDING PAGE LEADS
# ============================================

def init_database():
    """Inicializa banco de dados SQLite para landing page leads."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Tabela UNICA - lead com dados do imovel embutidos (SIMPLIFICADO)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS landing_leads_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                name TEXT,
                source_url TEXT,
                -- Dados do imovel (inline)
                property_title TEXT NOT NULL,
                property_price REAL,
                property_price_formatted TEXT,
                property_neighborhood TEXT,
                property_bedrooms INTEGER,
                property_area REAL,
                property_image_url TEXT,
                property_link TEXT,
                property_description TEXT,
                -- Timestamps e status
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                contacted_at TIMESTAMP,
                first_message_at TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')

        # Indices para busca rapida
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_leads_v2_phone ON landing_leads_v2(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_leads_v2_status ON landing_leads_v2(status)')

        # ============================================
        # TABELA DE VISITAS PERSISTENTE
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS property_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_uuid TEXT UNIQUE NOT NULL,
                lead_number TEXT NOT NULL,
                lead_phone TEXT,
                lead_name TEXT,
                lead_data TEXT,
                property_title TEXT,
                property_info TEXT,
                scheduled_date TEXT,
                scheduled_time TEXT,
                scheduled_datetime TIMESTAMP,
                status TEXT DEFAULT 'pending',
                session TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmation_sent INTEGER DEFAULT 0,
                lead_confirmed INTEGER DEFAULT 0,
                lead_confirmed_at TIMESTAMP,
                broker_confirmed INTEGER DEFAULT 0,
                broker_confirmed_at TIMESTAMP,
                feedback_requested INTEGER DEFAULT 0,
                feedback_score INTEGER,
                feedback_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Indices para visitas
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_lead_number ON property_visits(lead_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_lead_phone ON property_visits(lead_phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_status ON property_visits(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visits_uuid ON property_visits(visit_uuid)')

        # ============================================
        # TABELA DE HISTORICO DE CONVERSAS
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Indices para mensagens
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversation_messages(conversation_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_created_at ON conversation_messages(created_at)')

        # ============================================
        # TABELA DE CORRETORES (BROKERS)
        # ============================================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS brokers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                creci TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Indices para corretores
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_brokers_active ON brokers(active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_brokers_phone ON brokers(phone)')

        # ============================================
        # ADICIONAR COLUNAS DE QUALIFICACAO E BROKER
        # ============================================
        # Adicionar broker_id a property_visits (se nao existir)
        try:
            cursor.execute('ALTER TABLE property_visits ADD COLUMN broker_id INTEGER')
        except sqlite3.OperationalError:
            pass  # Coluna ja existe

        # Adicionar campos de qualificacao a landing_leads_v2 (se nao existirem)
        try:
            cursor.execute('ALTER TABLE landing_leads_v2 ADD COLUMN qualification_score INTEGER')
        except sqlite3.OperationalError:
            pass  # Coluna ja existe

        try:
            cursor.execute('ALTER TABLE landing_leads_v2 ADD COLUMN qualification_budget TEXT')
        except sqlite3.OperationalError:
            pass  # Coluna ja existe

        try:
            cursor.execute('ALTER TABLE landing_leads_v2 ADD COLUMN qualification_region TEXT')
        except sqlite3.OperationalError:
            pass  # Coluna ja existe

        try:
            cursor.execute('ALTER TABLE landing_leads_v2 ADD COLUMN qualification_intent TEXT')
        except sqlite3.OperationalError:
            pass  # Coluna ja existe

        try:
            cursor.execute('ALTER TABLE landing_leads_v2 ADD COLUMN last_interaction_at TIMESTAMP')
        except sqlite3.OperationalError:
            pass  # Coluna ja existe

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {DATABASE_PATH}")

        # Carregar visitas pendentes do banco para memoria
        load_visits_from_db()
    except Exception as e:
        logger.exception(f"Error initializing database: {e}")


@contextmanager
def get_db():
    """Context manager para conexao com banco de dados."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ============================================
# VISIT DATABASE FUNCTIONS
# ============================================

import json

def save_visit_to_db(visit: dict) -> int:
    """
    Salva visita no banco de dados.

    Args:
        visit: Dict com dados da visita

    Returns:
        ID do registro no banco
    """
    try:
        with get_db() as conn:
            # Serializar dicts para JSON
            lead_data_json = json.dumps(visit.get("lead_data", {}), ensure_ascii=False)
            property_info_json = json.dumps(visit.get("property_info", {}), ensure_ascii=False)

            # Extrair dados
            lead_phone = visit.get("lead_data", {}).get("phone", "")
            lead_name = visit.get("lead_data", {}).get("name", "")
            property_title = visit.get("property_info", {}).get("title", "")

            # Converter scheduled_datetime se existir
            scheduled_dt = visit.get("scheduled_datetime")
            scheduled_dt_str = scheduled_dt.isoformat() if scheduled_dt else None

            conn.execute('''
                INSERT INTO property_visits
                (visit_uuid, lead_number, lead_phone, lead_name, lead_data,
                 property_title, property_info, scheduled_date, scheduled_time,
                 scheduled_datetime, status, session, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                visit.get("id"),
                visit.get("lead_number"),
                lead_phone,
                lead_name,
                lead_data_json,
                property_title,
                property_info_json,
                visit.get("scheduled_date"),
                visit.get("scheduled_time"),
                scheduled_dt_str,
                visit.get("status", "pending"),
                visit.get("session"),
                visit.get("created_at", datetime.now().isoformat())
            ))
            conn.commit()
            db_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            logger.info(f"Visit {visit.get('id')} saved to database with ID {db_id}")
            return db_id
    except Exception as e:
        logger.error(f"Error saving visit to database: {e}")
        return -1


def update_visit_in_db(visit_uuid: str, updates: dict):
    """
    Atualiza visita no banco de dados.

    Args:
        visit_uuid: UUID da visita
        updates: Dict com campos a atualizar
    """
    try:
        with get_db() as conn:
            # Construir query dinamicamente
            set_clauses = []
            values = []

            for key, value in updates.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            # Adicionar updated_at
            set_clauses.append("updated_at = ?")
            values.append(datetime.now().isoformat())

            # Adicionar visit_uuid para WHERE
            values.append(visit_uuid)

            query = f"UPDATE property_visits SET {', '.join(set_clauses)} WHERE visit_uuid = ?"
            conn.execute(query, values)
            conn.commit()
            logger.info(f"Visit {visit_uuid} updated in database: {list(updates.keys())}")
    except Exception as e:
        logger.error(f"Error updating visit {visit_uuid} in database: {e}")


def get_active_visit_from_db(lead_number: str = None, lead_phone: str = None) -> dict | None:
    """
    Busca visita ativa (pending/confirmed) de um lead no banco.

    Args:
        lead_number: Numero do lead com @c.us/@lid
        lead_phone: Telefone real do lead

    Returns:
        Dict da visita ou None
    """
    try:
        with get_db() as conn:
            # Buscar por lead_number ou lead_phone
            cursor = conn.execute('''
                SELECT * FROM property_visits
                WHERE (lead_number = ? OR lead_phone = ? OR lead_phone LIKE ?)
                AND status IN ('pending', 'confirmed')
                ORDER BY created_at DESC
                LIMIT 1
            ''', (lead_number, lead_phone, f"%{lead_phone}%" if lead_phone else ""))

            row = cursor.fetchone()
            if row:
                visit = dict(row)
                # Deserializar JSON
                if visit.get("lead_data"):
                    try:
                        visit["lead_data"] = json.loads(visit["lead_data"])
                    except:
                        visit["lead_data"] = {}
                if visit.get("property_info"):
                    try:
                        visit["property_info"] = json.loads(visit["property_info"])
                    except:
                        visit["property_info"] = {}
                # Renomear visit_uuid para id
                visit["id"] = visit.pop("visit_uuid", visit.get("id"))
                return visit
    except Exception as e:
        logger.error(f"Error getting active visit from database: {e}")
    return None


def get_lead_visit_history(lead_number: str = None, lead_phone: str = None) -> list[dict]:
    """
    Retorna historico completo de visitas do lead (para contexto da AI).

    Args:
        lead_number: Numero do lead com @c.us/@lid
        lead_phone: Telefone real do lead

    Returns:
        Lista de visitas ordenadas por data (mais recente primeiro)
    """
    visits = []
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                SELECT * FROM property_visits
                WHERE lead_number = ? OR lead_phone = ? OR lead_phone LIKE ?
                ORDER BY created_at DESC
                LIMIT 10
            ''', (lead_number, lead_phone, f"%{lead_phone}%" if lead_phone else ""))

            for row in cursor:
                visit = dict(row)
                # Deserializar JSON
                if visit.get("lead_data"):
                    try:
                        visit["lead_data"] = json.loads(visit["lead_data"])
                    except:
                        visit["lead_data"] = {}
                if visit.get("property_info"):
                    try:
                        visit["property_info"] = json.loads(visit["property_info"])
                    except:
                        visit["property_info"] = {}
                # Renomear visit_uuid para id
                visit["id"] = visit.pop("visit_uuid", visit.get("id"))
                visits.append(visit)
    except Exception as e:
        logger.error(f"Error getting lead visit history: {e}")
    return visits


def load_visits_from_db():
    """
    Carrega visitas pendentes do banco para memoria (chamado no startup).
    """
    global scheduled_visits
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                SELECT * FROM property_visits
                WHERE status IN ('pending', 'confirmed')
                ORDER BY created_at DESC
            ''')

            count = 0
            for row in cursor:
                visit = dict(row)
                visit_uuid = visit.pop("visit_uuid", None)
                if not visit_uuid:
                    continue

                # Deserializar JSON
                if visit.get("lead_data"):
                    try:
                        visit["lead_data"] = json.loads(visit["lead_data"])
                    except:
                        visit["lead_data"] = {}
                if visit.get("property_info"):
                    try:
                        visit["property_info"] = json.loads(visit["property_info"])
                    except:
                        visit["property_info"] = {}

                # Restaurar formato esperado
                visit["id"] = visit_uuid
                visit["lead_confirmed"] = bool(visit.get("lead_confirmed"))
                visit["broker_confirmed"] = bool(visit.get("broker_confirmed"))
                visit["confirmation_sent"] = bool(visit.get("confirmation_sent"))
                visit["feedback_requested"] = bool(visit.get("feedback_requested"))

                scheduled_visits[visit_uuid] = visit
                count += 1

            logger.info(f"Loaded {count} pending visits from database")
    except Exception as e:
        logger.error(f"Error loading visits from database: {e}")


def format_visit_history_for_ai(visits: list[dict]) -> str:
    """
    Formata historico de visitas para injetar no contexto da AI.

    Args:
        visits: Lista de visitas

    Returns:
        String formatada para a AI
    """
    if not visits:
        return ""

    lines = ["[HISTORICO DE VISITAS DO LEAD:"]
    for visit in visits[:5]:  # Limitar a 5 visitas
        visit_id = visit.get("id", "?")
        prop_title = visit.get("property_title") or visit.get("property_info", {}).get("title", "Imovel")
        date = visit.get("scheduled_date", "?")
        time = visit.get("scheduled_time", "?")
        status = visit.get("status", "?")
        score = visit.get("feedback_score")

        line = f"- Visita #{visit_id}: {prop_title} em {date} as {time} - Status: {status}"
        if score:
            line += f", Nota: {score}/5"
        lines.append(line)

    lines.append("Use esse historico para ajudar o lead com duvidas sobre visitas anteriores ou reagendar.]")
    return "\n".join(lines)


# ============================================
# CONVERSATION HISTORY DATABASE FUNCTIONS
# ============================================

def save_message_to_db(conversation_id: str, role: str, content: str) -> int:
    """
    Salva mensagem no banco de dados.

    Args:
        conversation_id: ID da conversa (ex: whatsapp_5585999999999@c.us)
        role: 'user' ou 'assistant'
        content: Conteudo da mensagem

    Returns:
        ID da mensagem inserida
    """
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                INSERT INTO conversation_messages (conversation_id, role, content)
                VALUES (?, ?, ?)
            ''', (conversation_id, role, content))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Error saving message to database: {e}")
        raise


def get_conversation_history_from_db(conversation_id: str, limit: int = 20) -> list[dict]:
    """
    Busca historico de conversa do banco.

    Args:
        conversation_id: ID da conversa
        limit: Numero maximo de mensagens

    Returns:
        Lista de mensagens em ordem cronologica
    """
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                SELECT role, content FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (conversation_id, limit))
            # Inverter para ordem cronologica (mais antigas primeiro)
            messages = [{"role": row["role"], "content": row["content"]} for row in cursor]
            return list(reversed(messages))
    except Exception as e:
        logger.error(f"Error loading conversation history from database: {e}")
        return []


def clear_old_messages_from_db(conversation_id: str, keep_last: int = 50):
    """
    Remove mensagens antigas mantendo as ultimas N.

    Args:
        conversation_id: ID da conversa
        keep_last: Numero de mensagens a manter
    """
    try:
        with get_db() as conn:
            conn.execute('''
                DELETE FROM conversation_messages
                WHERE conversation_id = ? AND id NOT IN (
                    SELECT id FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC LIMIT ?
                )
            ''', (conversation_id, conversation_id, keep_last))
            conn.commit()
    except Exception as e:
        logger.error(f"Error cleaning old messages: {e}")


def cleanup_old_conversations(days_old: int = 30):
    """
    Remove conversas antigas do banco (para limpeza periodica).

    Args:
        days_old: Remover conversas mais antigas que N dias
    """
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                DELETE FROM conversation_messages
                WHERE created_at < datetime('now', ? || ' days')
            ''', (f'-{days_old}',))
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} messages older than {days_old} days")
    except Exception as e:
        logger.error(f"Error cleaning old conversations: {e}")


# ============================================
# FOLLOW-UP PROATIVO SYSTEM
# ============================================

def schedule_followup(lead_id: int, phone: str, delay_seconds: int = 300):
    """
    Agenda follow-up proativo para lead que nao iniciou conversa.

    Args:
        lead_id: ID do lead no banco
        phone: Telefone do lead
        delay_seconds: Tempo de espera (default 5 min)
    """
    # Cancela timer anterior se existir
    if lead_id in followup_timers:
        followup_timers[lead_id].cancel()

    # Cria novo timer
    timer = threading.Timer(
        delay_seconds,
        execute_followup,
        args=[lead_id, phone]
    )
    followup_timers[lead_id] = timer
    timer.start()

    logger.info(f"Follow-up scheduled for lead {lead_id} in {delay_seconds}s")


def cancel_followup(lead_id: int):
    """Cancela follow-up agendado (lead iniciou conversa)."""
    if lead_id in followup_timers:
        followup_timers[lead_id].cancel()
        del followup_timers[lead_id]
        logger.info(f"Follow-up cancelled for lead {lead_id}")


# ============================================
# COLD LEAD FOLLOW-UP FUNCTIONS
# ============================================

def format_delay(seconds: int) -> str:
    """Formata segundos para texto legível."""
    if seconds < 3600:
        return f"{seconds // 60} minutos"
    elif seconds < 86400:
        return f"{seconds // 3600} horas"
    else:
        return f"{seconds // 86400} dias"


def schedule_cold_lead_followup(conversation_id: str, last_response: str = None) -> None:
    """
    Agenda follow-up para lead que não respondeu.
    Usa sistema de tiers com delays progressivos.

    Args:
        conversation_id: ID da conversa (ex: whatsapp_5585999999999@c.us)
        last_response: Última resposta do agent (opcional)
    """
    global cold_lead_timers

    # Determinar tier atual
    current = cold_lead_timers.get(conversation_id, {})
    current_tier = current.get("tier", 0)

    # Já atingiu máximo de tiers
    if current_tier >= len(COLD_LEAD_FOLLOWUP_TIERS):
        logger.info(f"Max follow-up tiers reached for {conversation_id}")
        return

    # Cancelar timer existente
    if conversation_id in cold_lead_timers:
        old_timer = cold_lead_timers[conversation_id].get("timer")
        if old_timer:
            old_timer.cancel()

    # Determinar delay baseado no tier
    delay = COLD_LEAD_FOLLOWUP_TIERS[current_tier]

    # Criar novo timer
    timer = threading.Timer(
        delay,
        execute_cold_lead_followup,
        args=[conversation_id]
    )
    timer.daemon = True

    cold_lead_timers[conversation_id] = {
        "timer": timer,
        "tier": current_tier,
        "last_agent_response": last_response[:200] if last_response else "",
        "scheduled_at": datetime.now()
    }

    timer.start()

    # Log legível
    delay_text = format_delay(delay)
    logger.info(f"Cold lead follow-up tier {current_tier + 1} scheduled for {conversation_id} in {delay_text}")


def execute_cold_lead_followup(conversation_id: str) -> None:
    """
    Executa follow-up para lead que não respondeu.
    Usa mensagem do tier atual e agenda próximo tier.
    """
    global cold_lead_timers

    try:
        if conversation_id not in cold_lead_timers:
            return

        data = cold_lead_timers[conversation_id]
        current_tier = data.get("tier", 0)

        # Extrair número do WhatsApp
        chat_id = conversation_id.replace("whatsapp_", "")
        session = "corretores"

        # Mensagem baseada no tier
        message = COLD_LEAD_MESSAGES.get(current_tier, COLD_LEAD_MESSAGES[0])

        # Enviar mensagem
        send_waha_message_sync(session, chat_id, message)

        # Adicionar ao histórico da conversa
        add_to_history(conversation_id, "assistant", message)

        logger.info(f"Sent cold lead follow-up tier {current_tier + 1} to {conversation_id}")

        # Avançar para próximo tier
        next_tier = current_tier + 1

        if next_tier < len(COLD_LEAD_FOLLOWUP_TIERS):
            # Atualizar tier e agendar próximo
            cold_lead_timers[conversation_id]["tier"] = next_tier
            cold_lead_timers[conversation_id]["timer"] = None
            schedule_cold_lead_followup(conversation_id)
        else:
            # Último tier alcançado - limpar da memória
            del cold_lead_timers[conversation_id]
            logger.info(f"All {len(COLD_LEAD_FOLLOWUP_TIERS)} follow-up tiers completed for {conversation_id}")

    except Exception as e:
        logger.exception(f"Error executing cold lead follow-up: {e}")


def cancel_cold_lead_followup(conversation_id: str) -> None:
    """
    Cancela follow-up quando lead responde.
    Reseta contador para começar de novo se parar de responder.
    """
    global cold_lead_timers

    if conversation_id in cold_lead_timers:
        timer = cold_lead_timers[conversation_id].get("timer")
        if timer:
            timer.cancel()
        del cold_lead_timers[conversation_id]
        logger.info(f"Cold lead follow-up cancelled for {conversation_id}")


def execute_followup(lead_id: int, phone: str):
    """
    Executa follow-up proativo - dados do imovel ja estao no lead (SIMPLIFICADO).
    """
    try:
        # Verifica se lead ja iniciou conversa - dados do imovel ja estao na tabela
        with get_db() as conn:
            lead = conn.execute(
                "SELECT * FROM landing_leads_v2 WHERE id = ? AND status = 'pending'",
                (lead_id,)
            ).fetchone()

            if not lead:
                logger.info(f"Lead {lead_id} already contacted or not pending, skipping followup")
                return

        # Formata numero para WhatsApp
        chat_id = f"{phone}@c.us"

        # Monta mensagem de follow-up usando dados inline do lead
        area_text = f", {lead['property_area']}m2" if lead['property_area'] else ""
        followup_msg = f"""Ola! Vi que voce demonstrou interesse no *{lead['property_title']}*.

Esse imovel tem {lead['property_bedrooms']} quartos{area_text}, localizado em {lead['property_neighborhood']}.

Posso te ajudar a agendar uma visita?"""

        # Envia mensagem
        send_waha_message_sync("corretores", chat_id, followup_msg)

        # Atualiza status do lead
        with get_db() as conn:
            conn.execute(
                "UPDATE landing_leads_v2 SET status = 'contacted', contacted_at = ? WHERE id = ?",
                (datetime.now().isoformat(), lead_id)
            )
            conn.commit()

        # Armazena contexto do imovel para proximas mensagens
        conversation_id = f"whatsapp_{chat_id}"
        landing_lead_context[conversation_id] = {
            "lead_id": lead_id,
            "property": {
                "title": lead["property_title"],
                "price": lead["property_price"],
                "price_formatted": lead["property_price_formatted"],
                "neighborhood": lead["property_neighborhood"],
                "bedrooms": lead["property_bedrooms"],
                "area": lead["property_area"],
                "image_url": lead["property_image_url"],
                "link": lead["property_link"]
            },
            "is_landing_page": True,
            "followup_sent": True
        }

        logger.info(f"Follow-up sent to lead {lead_id} ({phone}) for property {lead['property_title']}")

        # Remove timer da lista
        if lead_id in followup_timers:
            del followup_timers[lead_id]

    except Exception as e:
        logger.exception(f"Error executing followup for lead {lead_id}: {e}")


def get_landing_lead_by_phone(phone: str) -> dict | None:
    """
    Busca lead pre-registrado pelo telefone (SIMPLIFICADO - dados inline).

    Returns:
        Dict com dados do lead e imovel, ou None
    """
    # Normaliza telefone
    phone_clean = re.sub(r'\D', '', phone)

    try:
        with get_db() as conn:
            # Busca lead pendente ou recentemente contatado - dados do imovel ja estao na tabela
            lead = conn.execute('''
                SELECT * FROM landing_leads_v2
                WHERE phone = ? AND status IN ('pending', 'contacted')
                ORDER BY registered_at DESC
                LIMIT 1
            ''', (phone_clean,)).fetchone()

            if lead:
                return {
                    "lead_id": lead["id"],
                    "lead_name": lead["name"],
                    "is_landing_page": True,
                    "property": {
                        "title": lead["property_title"],
                        "price": lead["property_price"],
                        "price_formatted": lead["property_price_formatted"],
                        "neighborhood": lead["property_neighborhood"],
                        "bedrooms": lead["property_bedrooms"],
                        "area": lead["property_area"],
                        "image_url": lead["property_image_url"],
                        "link": lead["property_link"],
                        "description": lead["property_description"]
                    }
                }

    except Exception as e:
        logger.exception(f"Error getting landing lead by phone {phone}: {e}")

    return None


def get_system_prompt_for_lead(is_landing_page: bool, property_context: dict = None) -> str:
    """
    Retorna system prompt diferenciado baseado na origem do lead.
    """

    if is_landing_page and property_context:
        prop = property_context
        area_text = f"- Area: {prop.get('area', 'N/A')}m2" if prop.get('area') else ""
        return f"""Voce e um assistente imobiliario conversando com lead que veio de landing page.

CONTEXTO DO IMOVEL:
- Titulo: {prop.get('title', 'Imovel')}
- Preco: {prop.get('price_formatted', 'Consultar')}
- Bairro: {prop.get('neighborhood', 'Nao informado')}
- Quartos: {prop.get('bedrooms', 'N/A')}
{area_text}

REGRAS:
- Respostas CURTAS (2-3 frases)
- UMA pergunta por vez
- SEM EMOJIS
- NUNCA peca numero de WhatsApp

FLUXO PARA LEAD DE LANDING PAGE:
1. Confirmar interesse no imovel especifico
2. Coletar nome (se nao tiver)
3. Oferecer visita: "Quando voce gostaria de visitar?"
4. Coletar data e horario
5. Confirmar agendamento

IMPORTANTE:
- Lead JA demonstrou interesse neste imovel especifico
- NAO envie outras opcoes a menos que ele PECA
- Foco total em AGENDAR VISITA para este imovel
- Se pedir outras opcoes: "Claro, posso mostrar outras opcoes. Qual regiao te interessa?"

OBJETIVO: Agendar visita para o imovel da landing page."""

    else:
        # Prompt generico - retorna None para usar o padrao existente
        return None


def get_conversation_history(conversation_id: str) -> list[dict]:
    """
    Retorna historico da conversa (memoria ou banco).

    1. Primeiro tenta memoria (cache rapido)
    2. Se nao encontrar, busca no banco de dados
    3. Se encontrar no banco, recarrega para memoria (cache)
    """
    # 1. Primeiro tenta memoria
    if conversation_id in conversation_history and conversation_history[conversation_id]:
        return conversation_history[conversation_id].copy()

    # 2. Se nao estiver em memoria, busca no banco de dados
    try:
        db_history = get_conversation_history_from_db(conversation_id, MAX_HISTORY_MESSAGES)
        if db_history:
            # Recarregar para memoria (cache)
            conversation_history[conversation_id] = db_history
            logger.info(f"Loaded {len(db_history)} messages from database for {conversation_id}")
            return db_history.copy()
    except Exception as e:
        logger.warning(f"Error loading history from database: {e}")

    return []


def add_to_history(conversation_id: str, role: str, content: str) -> None:
    """
    Adiciona mensagem ao historico da conversa (memoria + banco).

    1. Adiciona a memoria para acesso rapido
    2. Persiste no banco para permanencia
    """
    if conversation_id not in conversation_history:
        conversation_history[conversation_id] = []

    conversation_history[conversation_id].append({
        "role": role,
        "content": content
    })

    # Limita tamanho do historico em memoria para evitar overflow de tokens
    if len(conversation_history[conversation_id]) > MAX_HISTORY_MESSAGES:
        conversation_history[conversation_id] = conversation_history[conversation_id][-MAX_HISTORY_MESSAGES:]

    # Persistir no banco de dados
    try:
        save_message_to_db(conversation_id, role, content)
    except Exception as e:
        logger.warning(f"Error persisting message to database: {e}")


def clear_conversation_history(conversation_id: str) -> None:
    """Limpa historico de uma conversa."""
    if conversation_id in conversation_history:
        del conversation_history[conversation_id]


def extract_filters_from_history(conversation_id: str) -> dict:
    """
    Analisa historico da conversa e extrai filtros de busca.
    Retorna dict com: neighborhood, bedrooms, max_price
    """
    history = get_conversation_history(conversation_id)

    # Junta todas as mensagens do usuario
    user_messages = " ".join([
        msg["content"].lower()
        for msg in history
        if msg["role"] == "user"
    ])

    filters = {}

    # Lista de bairros conhecidos de Fortaleza/CE
    bairros = [
        "aldeota", "meireles", "cocó", "coco", "dionisio torres", "papicu",
        "benfica", "centro", "fatima", "joaquim tavora", "mucuripe",
        "praia de iracema", "varjota", "guararapes", "edson queiroz",
        "agua fria", "luciano cavalcante", "cambeba", "messejana",
        "parquelandia", "montese", "parangaba", "maraponga"
    ]

    # CORREÇÃO: Pegar o ÚLTIMO bairro mencionado (mais recente na conversa)
    last_bairro = None
    last_position = -1
    for bairro in bairros:
        pos = user_messages.rfind(bairro)  # rfind = última ocorrência
        if pos > last_position:
            last_position = pos
            last_bairro = bairro

    if last_bairro:
        filters["neighborhood"] = last_bairro.title()
        logger.info(f"Extracted neighborhood: {last_bairro.title()} (last mentioned at pos {last_position})")

    # Extrai quartos (padroes: "2 quartos", "3 qts", "2")
    quartos_match = re.search(r'(\d+)\s*(?:quarto|quartos|qts|qto)', user_messages)
    if quartos_match:
        filters["bedrooms"] = quartos_match.group(1)
        logger.info(f"Extracted bedrooms: {filters['bedrooms']}")

    # CORREÇÃO: Melhorar detecção de renda
    renda = None

    # Padrão 1: "9 mil", "9k", "9mil"
    renda_match = re.search(r'(\d+)\s*(?:mil|k)\b', user_messages)
    if renda_match:
        renda = int(renda_match.group(1)) * 1000
        logger.info(f"Detected renda pattern 1: {renda_match.group(0)} -> R$ {renda:,.0f}")
    else:
        # Padrão 2: número grande (1000-99999) - provavelmente renda
        # Exemplos: "9500", "9.500", "R$ 9500"
        renda_match = re.search(r'(?:r\$\s*)?(\d{1,2}[.\s]?\d{3})(?!\d)', user_messages)
        if renda_match:
            renda_str = renda_match.group(1).replace(".", "").replace(" ", "")
            renda = int(renda_str)
            logger.info(f"Detected renda pattern 2: {renda_match.group(0)} -> R$ {renda:,.0f}")

    if renda and renda >= 1000:
        max_price = renda * 0.30 * 360  # Formula de financiamento
        filters["max_price"] = max_price
        filters["renda"] = renda  # Renda bruta para notificacao ao corretor
        logger.info(f"Extracted max_price: R$ {max_price:,.2f} (from renda R$ {renda:,.0f})")

    return filters


def extract_lead_name(conversation_id: str) -> str:
    """
    Extrai nome do lead do historico da conversa.

    Procura padroes como:
    - "meu nome e X", "me chamo X", "sou o X", "sou a X"
    - "oi, X aqui", "ola, sou X"

    Returns:
        Nome do lead ou "Nao informado"
    """
    history = get_conversation_history(conversation_id)

    for msg in history:
        if msg["role"] == "user":
            text = msg["content"]

            # Padrao 1: "meu nome e X", "me chamo X"
            match = re.search(
                r'(?:meu nome [eé]|me chamo)\s+([A-Z][a-zà-ú]+(?:\s+[A-Z][a-zà-ú]+)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).title()

            # Padrao 2: "sou o/a X"
            match = re.search(
                r'sou\s+[oa]?\s*([A-Z][a-zà-ú]+(?:\s+[A-Z][a-zà-ú]+)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).title()

            # Padrao 3: "oi, X aqui" ou "ola, sou X"
            match = re.search(
                r'(?:oi|ola|olá),?\s+(?:aqui [eé] [oa]?\s*)?([A-Z][a-zà-ú]+)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).title()

    return "Nao informado"


def validate_lead_data_for_scheduling(conversation_id: str) -> dict:
    """
    Valida se lead informou dados obrigatórios para agendamento.

    Dados obrigatórios:
    - name: Nome do lead
    - neighborhood: Bairro de interesse
    - bedrooms: Número de quartos

    Returns:
        {
            "is_valid": bool,
            "missing_fields": list[str],
            "collected_data": dict
        }
    """
    filters = extract_filters_from_history(conversation_id)
    lead_name = extract_lead_name(conversation_id)

    missing = []

    if lead_name == "Nao informado":
        missing.append("nome")

    if not filters.get("neighborhood") or filters.get("neighborhood") == "Nao informado":
        missing.append("bairro")

    if not filters.get("bedrooms") or filters.get("bedrooms") == "Nao informado":
        missing.append("quartos")

    return {
        "is_valid": len(missing) == 0,
        "missing_fields": missing,
        "collected_data": {
            "name": lead_name,
            "neighborhood": filters.get("neighborhood", "Nao informado"),
            "bedrooms": filters.get("bedrooms", "Nao informado"),
            "renda": filters.get("renda", 0),
            "max_price": filters.get("max_price", 0)
        }
    }


def extract_lead_data_with_ai(conversation_id: str) -> dict:
    """
    Usa AI para extrair dados estruturados do histórico.
    Mais preciso que regex para variações de linguagem natural.
    """
    history = get_conversation_history(conversation_id)
    if not history:
        return {}

    # Formatar histórico para o prompt
    formatted = "\n".join([
        f"{'Lead' if m['role']=='user' else 'Assistente'}: {m['content']}"
        for m in history[-10:]  # Últimas 10 mensagens
    ])

    extraction_prompt = """Analise o historico de conversa abaixo e extraia os dados do cliente.
O lead pode ter respondido de forma curta (ex: so o nome, so um numero).
Retorne APENAS um JSON valido com os campos abaixo (use null se nao encontrar):

{
  "name": "nome do cliente",
  "neighborhood": "bairro de interesse",
  "bedrooms": "numero de quartos",
  "renda": numero da renda mensal ou null,
  "property_type": "apartamento/casa/terreno ou null"
}

HISTORICO:
""" + formatted

    try:
        import httpx
        import json

        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [{"role": "user", "content": extraction_prompt}],
                    "temperature": 0.2,
                    "max_tokens": 200
                }
            )
            response.raise_for_status()

            ai_text = response.json()["choices"][0]["message"]["content"]
            logger.info(f"AI extraction response: {ai_text[:200]}")

            # Extrair JSON da resposta
            import re
            json_match = re.search(r'\{[^{}]*\}', ai_text, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group())
                logger.info(f"AI extracted lead data: {extracted}")
                return extracted

    except Exception as e:
        logger.warning(f"AI extraction failed: {e}")

    return {}


def detect_property_selection(message_text: str, has_quoted: bool, quoted_msg: dict = None) -> dict:
    """
    Detecta quando usuario seleciona um imovel especifico.

    Args:
        message_text: Texto da mensagem do usuario
        has_quoted: Se a mensagem cita/responde outra mensagem
        quoted_msg: Dados da mensagem citada (se houver)

    Returns:
        {
            "has_selection": bool,
            "selection_type": "quoted" | "keyword" | "none",
            "intent": "schedule" | "interest" | "none"
        }
    """
    message_lower = message_text.lower().strip()

    result = {
        "has_selection": False,
        "selection_type": "none",
        "intent": "none"
    }

    # Palavras que indicam selecao de imovel especifico
    selection_words = ["esse", "este", "aquele", "esse ai", "esse aí", "ali", "aí"]
    interest_words = ["quero", "gostei", "interessei", "gosto", "prefiro", "escolho"]
    schedule_words = ["agendar", "visita", "visitar", "ver", "conhecer", "marcar", "quando"]

    # TIPO 1: Mensagem citando/respondendo a imovel (maior confianca)
    if has_quoted and quoted_msg:
        result["has_selection"] = True
        result["selection_type"] = "quoted"

        if any(w in message_lower for w in schedule_words):
            result["intent"] = "schedule"
        else:
            result["intent"] = "interest"

        logger.info(f"Detected QUOTED property selection: intent={result['intent']}")
        return result

    # TIPO 2: Palavras-chave de selecao sem citacao
    has_selection_word = any(w in message_lower for w in selection_words)
    has_interest_word = any(w in message_lower for w in interest_words)

    if has_selection_word or has_interest_word:
        # Verificar se NAO esta pedindo mais opcoes
        more_options_words = ["outro", "mais", "diferente", "opcoes", "opções", "outras"]
        wants_more = any(w in message_lower for w in more_options_words)

        if not wants_more:
            result["has_selection"] = True
            result["selection_type"] = "keyword"

            if any(w in message_lower for w in schedule_words):
                result["intent"] = "schedule"
            else:
                result["intent"] = "interest"

            logger.info(f"Detected KEYWORD property selection: intent={result['intent']}")

    return result


def parse_portuguese_datetime(message: str) -> dict | None:
    """
    Parse Portuguese date/time expressions from user message.

    Supports patterns like:
    - "amanha as 14h", "amanhã às 14:00"
    - "segunda 10:00", "terça de manhã"
    - "dia 26 de manhã", "dia 15 às 15h"
    - "hoje às 16h"

    Returns:
        {
            "date": datetime.date or None,
            "time": str (e.g., "14:00") or None,
            "period": str (e.g., "manha", "tarde") or None
        }
        or None if no scheduling pattern detected
    """
    message_lower = message.lower().strip()
    today = datetime.now()
    result = {"date": None, "time": None, "period": None}

    # === DATE PATTERNS ===

    # Pattern 1: "hoje"
    if "hoje" in message_lower:
        result["date"] = today.date()

    # Pattern 2: "amanha" / "amanhã"
    elif re.search(r'amanh[aã]', message_lower):
        result["date"] = (today + timedelta(days=1)).date()

    # Pattern 3: "dia X" (e.g., "dia 26", "dia 15")
    dia_match = re.search(r'dia\s+(\d{1,2})', message_lower)
    if dia_match:
        day = int(dia_match.group(1))
        try:
            # Try current month first
            result["date"] = today.replace(day=day).date()
            # If in past, use next month
            if result["date"] < today.date():
                if today.month == 12:
                    result["date"] = today.replace(year=today.year+1, month=1, day=day).date()
                else:
                    result["date"] = today.replace(month=today.month+1, day=day).date()
        except ValueError:
            pass  # Invalid day for month

    # Pattern 4: Day of week (segunda, terça, quarta, quinta, sexta, sábado, domingo)
    weekdays = {
        "segunda": 0, "terca": 1, "terça": 1, "quarta": 2,
        "quinta": 3, "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6
    }
    for name, target_weekday in weekdays.items():
        if name in message_lower:
            days_ahead = target_weekday - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            result["date"] = (today + timedelta(days=days_ahead)).date()
            break

    # === TIME PATTERNS ===

    # Pattern 1: Exact time "14h", "14:00", "14h30", "14:30", "às 14h"
    time_match = re.search(r'(\d{1,2})[h:](\d{2})?', message_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result["time"] = f"{hour:02d}:{minute:02d}"

    # Pattern 2: Period of day (manhã, tarde, noite)
    if re.search(r'manh[aã]', message_lower):
        result["period"] = "manha"
        if not result["time"]:
            result["time"] = "09:00"  # Default morning time
    elif "tarde" in message_lower:
        result["period"] = "tarde"
        if not result["time"]:
            result["time"] = "14:00"  # Default afternoon time
    elif "noite" in message_lower:
        result["period"] = "noite"
        if not result["time"]:
            result["time"] = "19:00"  # Default evening time

    # Only return if we found at least a date or time
    if result["date"] or result["time"]:
        logger.info(f"Parsed datetime from '{message[:50]}...': date={result['date']}, time={result['time']}, period={result['period']}")
        return result

    return None


def detect_scheduling_intent(message: str, conversation_id: str) -> dict:
    """
    Detect if user is trying to schedule a visit.

    Args:
        message: User's message text
        conversation_id: Conversation ID to check context

    Returns:
        {
            "has_scheduling": bool,
            "datetime_info": dict or None (from parse_portuguese_datetime),
            "property_context": dict or None (selected property info)
        }
    """
    result = {
        "has_scheduling": False,
        "datetime_info": None,
        "property_context": None
    }

    # Check if there's a selected property for this conversation
    property_ctx = selected_property_context.get(conversation_id)

    # Parse date/time from message
    datetime_info = parse_portuguese_datetime(message)

    if datetime_info:
        result["has_scheduling"] = True
        result["datetime_info"] = datetime_info
        result["property_context"] = property_ctx
        logger.info(f"Scheduling intent detected for {conversation_id}: {datetime_info}")

    return result


def store_and_notify_visit(
    lead_number: str,
    datetime_info: dict,
    property_ctx: dict,
    session: str,
    lead_data: dict = None
) -> dict:
    """
    Store a scheduled visit and notify the broker via WhatsApp.

    Args:
        lead_number: Lead's WhatsApp number
        datetime_info: Dict with date, time, period from parse_portuguese_datetime
        property_ctx: Property context dict (title, info)
        session: WAHA session
        lead_data: Dict with lead info (name, neighborhood, bedrooms, renda, max_price)

    Returns:
        Visit dict with id and status
    """
    visit_id = str(uuid.uuid4())[:8]  # Short ID for MVP

    # Format date and time
    if datetime_info.get("date"):
        scheduled_date = datetime_info["date"].strftime("%d/%m/%Y")
    else:
        scheduled_date = "A confirmar"

    scheduled_time = datetime_info.get("time") or "A confirmar"

    # Create visit record
    visit = {
        "id": visit_id,
        "lead_number": lead_number,
        "lead_data": lead_data or {},
        "property_info": property_ctx or {},
        "scheduled_date": scheduled_date,
        "scheduled_time": scheduled_time,
        "status": "pending",  # pending, confirmed, cancelled
        "created_at": datetime.now().isoformat(),
        "session": session
    }

    scheduled_visits[visit_id] = visit
    logger.info(f"Stored scheduled visit {visit_id} for {lead_number} on {scheduled_date} {scheduled_time}")

    # === PERSISTIR NO BANCO DE DADOS ===
    try:
        db_id = save_visit_to_db(visit)
        visit["db_id"] = db_id
        logger.info(f"Visit {visit_id} persisted to database with ID {db_id}")
    except Exception as e:
        logger.error(f"Failed to persist visit {visit_id} to database: {e}")

    # === NOTIFY BROKER WITH COMPLETE LEAD DATA ===
    # Usa phone do lead_data (ja contem numero real extraido de participant para @lid)
    lead_phone = lead_data.get("phone", lead_number.replace("@c.us", "").replace("@lid", "")) if lead_data else lead_number.replace("@c.us", "").replace("@lid", "")

    # Extrai dados do lead
    lead_name = lead_data.get("name", "Nao informado") if lead_data else "Nao informado"
    bairro = lead_data.get("neighborhood", "Nao informado") if lead_data else "Nao informado"
    quartos = lead_data.get("bedrooms", "Nao informado") if lead_data else "Nao informado"
    renda = lead_data.get("renda", 0) if lead_data else 0
    max_price = lead_data.get("max_price", 0) if lead_data else 0

    # Formata valores monetarios
    renda_fmt = f"R$ {renda:,.0f}".replace(",", ".") if renda else "Nao informado"
    limite_fmt = f"R$ {max_price:,.0f}".replace(",", ".") if max_price else "Nao informado"

    # Dados do imovel
    prop_title = property_ctx.get("title", "Imovel selecionado") if property_ctx else "Imovel selecionado"

    broker_msg = f"""*NOVA VISITA AGENDADA* #{visit_id}

*LEAD*
Nome: {lead_name}
Tel: {lead_phone}

*PERFIL DE COMPRA*
Bairro: {bairro}
Quartos: {quartos}
Renda: {renda_fmt}
Limite: {limite_fmt}

*VISITA*
Imovel: {prop_title}
Data: {scheduled_date}
Horario: {scheduled_time}

Responda para confirmar."""

    try:
        send_waha_message_sync(session, BROKER_WHATSAPP_NUMBER, broker_msg)
        logger.info(f"Broker notified about visit {visit_id} at {BROKER_WHATSAPP_NUMBER}")
    except Exception as e:
        logger.error(f"Failed to notify broker about visit {visit_id}: {e}")

    # Agendar follow-ups (confirmação e feedback)
    try:
        schedule_visit_followups(visit_id)
        logger.info(f"Follow-ups scheduled for visit {visit_id}")
    except Exception as e:
        logger.error(f"Failed to schedule follow-ups for visit {visit_id}: {e}")

    return visit


def add_to_message_buffer(from_number: str, message_text: str, session: str, real_phone: str = None) -> None:
    """
    Adiciona mensagem ao buffer e (re)inicia timer.
    Quando o timer dispara, todas as mensagens sao processadas juntas.
    """
    global message_buffer

    with message_buffer_lock:
        if from_number in message_buffer:
            # Cancela timer existente
            old_timer = message_buffer[from_number].get("timer")
            if old_timer:
                old_timer.cancel()

            # Adiciona mensagem ao buffer existente
            message_buffer[from_number]["messages"].append(message_text)
            # Atualiza real_phone se fornecido (mantem o primeiro valido)
            if real_phone and not message_buffer[from_number].get("real_phone"):
                message_buffer[from_number]["real_phone"] = real_phone
        else:
            # Cria novo buffer
            message_buffer[from_number] = {
                "messages": [message_text],
                "session": session,
                "real_phone": real_phone or from_number.replace("@c.us", "").replace("@lid", "")
            }

        # Cria novo timer
        timer = threading.Timer(
            MESSAGE_BUFFER_DELAY,
            process_buffered_messages,
            args=[from_number]
        )
        message_buffer[from_number]["timer"] = timer
        timer.start()

        logger.info(f"Buffered message from {from_number} ({len(message_buffer[from_number]['messages'])} in buffer, processing in {MESSAGE_BUFFER_DELAY}s)")


def process_buffered_messages(from_number: str) -> None:
    """
    Processa todas as mensagens acumuladas no buffer para um usuario.
    Chamada pelo timer apos MESSAGE_BUFFER_DELAY segundos.
    """
    global message_buffer

    with message_buffer_lock:
        if from_number not in message_buffer:
            return

        buffer_data = message_buffer.pop(from_number)

    messages = buffer_data["messages"]
    session = buffer_data["session"]

    if not messages:
        return

    # Combina todas as mensagens em uma so
    combined_text = " ".join(messages)
    logger.info(f"Processing {len(messages)} buffered messages from {from_number}: {combined_text[:80]}...")

    # Cria message_data combinado (inclui real_phone do buffer)
    real_phone = buffer_data.get("real_phone", from_number.replace("@c.us", "").replace("@lid", ""))
    combined_message_data = {
        "from_number": from_number,
        "real_phone": real_phone,
        "message_text": combined_text,
        "session": session,
        "message_type": "text",
        "buffered_count": len(messages)
    }

    # Processa como mensagem unica
    try:
        process_message_sync(combined_message_data)
        stats["messages_processed"] += 1
    except Exception as e:
        stats["messages_failed"] += 1
        logger.exception(f"Error processing buffered messages: {e}")


def search_properties_memude(filters: dict = None) -> list[dict]:
    """
    Busca imoveis na API do Memude com filtro CLIENT-SIDE.

    A API Memude nao filtra corretamente por parametros server-side,
    entao buscamos mais imoveis e filtramos localmente.

    Args:
        filters: dict com neighborhood, bedrooms, max_price

    Returns:
        Lista de imoveis filtrados (max 5)
    """
    import requests

    try:
        url = "https://www.memude.com.br/wp-json/custom/v1/posts"
        # Busca MAIS imoveis para ter margem de filtro client-side
        params = {"per_page": 100}

        # Headers de browser real para evitar bloqueio Cloudflare/ModSecurity
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.memude.com.br/"
        }

        logger.info(f"Searching Memude API (will filter client-side)")
        logger.info(f"Filters to apply: {filters}")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()

        all_properties = response.json()
        logger.info(f"Memude returned {len(all_properties)} total properties")

        # FILTRO CLIENT-SIDE
        filtered = []
        for item in all_properties:
            # Extrai dados do imovel
            price_raw = item.get("valor", 0)
            try:
                price_cents = float(price_raw) if price_raw else 0
            except (ValueError, TypeError):
                price_cents = 0
            price_reais = price_cents / 100 if price_cents else 0

            # Extrai bairro (categories e um array)
            bairros = item.get("categories", [])
            bairro = bairros[0] if bairros else ""

            # Extrai quartos (pode ser "2", "2-3", etc)
            quartos_str = str(item.get("quartos", "0"))
            quartos_match = re.search(r'\d+', quartos_str)
            quartos = int(quartos_match.group()) if quartos_match else 0

            # Aplica filtros
            if filters:
                # Filtro de bairro (case-insensitive, busca parcial)
                if filters.get("neighborhood"):
                    filter_bairro = filters["neighborhood"].lower()
                    if filter_bairro not in bairro.lower():
                        continue  # Nao passou no filtro de bairro

                # Filtro de quartos (minimo)
                if filters.get("bedrooms"):
                    try:
                        filter_quartos = int(filters["bedrooms"])
                        if quartos != filter_quartos:
                            continue  # Só aceita número EXATO de quartos
                    except (ValueError, TypeError):
                        pass

                # Filtro de preco maximo
                if filters.get("max_price"):
                    if price_reais > filters["max_price"]:
                        continue  # Acima do orcamento

            # Imovel passou nos filtros!
            filtered.append({
                "id": item.get("id"),
                "title": item.get("title", "Imovel"),
                "price": price_reais,
                "price_formatted": f"R$ {price_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "city": item.get("cidade", [""])[0] if isinstance(item.get("cidade"), list) and item.get("cidade") else item.get("cidade", "") or "",
                "neighborhood": bairro,
                "bedrooms": quartos_str,
                "area": item.get("area", ""),
                "image_url": item.get("image", ""),
                "link": item.get("link", "")
            })

            # Limita a 5 resultados
            if len(filtered) >= 5:
                break

        logger.info(f"After client-side filtering: {len(filtered)} properties match criteria")
        if filters and len(filtered) == 0:
            logger.warning(f"No properties matched filters: {filters}")

        return filtered

    except Exception as e:
        logger.exception(f"Error searching Memude: {e}")
        return []


def send_property_image_sync(session: str, chat_id: str, property_data: dict) -> bool:
    """
    Envia imagem de imovel via WAHA.

    Args:
        session: Sessao WAHA
        chat_id: ID do chat WhatsApp
        property_data: Dados do imovel

    Returns:
        True se enviou, False se falhou
    """
    import requests

    try:
        image_url = property_data.get("image_url")
        if not image_url:
            logger.warning(f"No image URL for property {property_data.get('title')}")
            return False

        # Monta caption formatada
        caption = f"*{property_data.get('title', 'Imovel')}*\n\n"

        if property_data.get("price_formatted"):
            caption += f"Valor: {property_data['price_formatted']}\n"
        if property_data.get("bedrooms"):
            caption += f"Quartos: {property_data['bedrooms']}\n"
        if property_data.get("area"):
            caption += f"Area: {property_data['area']}m2\n"
        if property_data.get("neighborhood"):
            caption += f"Bairro: {property_data['neighborhood']}\n"
        if property_data.get("city"):
            caption += f"Cidade: {property_data['city']}\n"
        if property_data.get("link"):
            caption += f"\nMais detalhes: {property_data['link']}"

        url = f"{WAHA_BASE_URL}/api/sendImage"
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": WAHA_API_KEY
        }
        payload = {
            "session": session,
            "chatId": chat_id,
            "file": {"url": image_url},
            "caption": caption
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        logger.info(f"Sent property image to {chat_id}: {property_data.get('title')}")
        return True

    except Exception as e:
        logger.exception(f"Error sending property image: {e}")
        return False


def send_properties_to_lead(session: str, chat_id: str, filters: dict = None, conversation_id: str = None) -> int:
    """
    Busca e envia imoveis para o lead.

    Args:
        session: Sessao WAHA
        chat_id: ID do chat
        filters: Filtros de busca
        conversation_id: ID da conversa para extração via AI

    Returns:
        Quantidade de imoveis enviados
    """
    # Enriquecer filtros com extração via AI se disponível
    if conversation_id and filters:
        try:
            ai_data = extract_lead_data_with_ai(conversation_id)
            if ai_data:
                # Preencher campos faltantes com dados extraídos via AI
                if not filters.get("bedrooms") and ai_data.get("bedrooms"):
                    filters["bedrooms"] = str(ai_data.get("bedrooms"))
                    logger.info(f"AI enriched bedrooms: {filters['bedrooms']}")
                if not filters.get("neighborhood") and ai_data.get("neighborhood"):
                    filters["neighborhood"] = ai_data.get("neighborhood")
                    logger.info(f"AI enriched neighborhood: {filters['neighborhood']}")
                if not filters.get("max_price") and ai_data.get("renda"):
                    try:
                        renda = float(ai_data.get("renda"))
                        filters["max_price"] = renda * 0.30 * 360
                        logger.info(f"AI enriched max_price from renda: {filters['max_price']}")
                    except (ValueError, TypeError):
                        pass
                logger.info(f"Filters after AI enrichment: {filters}")
        except Exception as e:
            logger.warning(f"AI extraction failed, using original filters: {e}")

    properties = search_properties_memude(filters)

    if not properties:
        logger.info("No properties found to send")
        return 0

    sent_count = 0
    for prop in properties:
        if send_property_image_sync(session, chat_id, prop):
            sent_count += 1
            # Delay entre envios para nao parecer spam
            time.sleep(1.5)

    logger.info(f"Sent {sent_count}/{len(properties)} properties to {chat_id}")
    return sent_count


def extract_message_data(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract relevant message data from WAHA webhook payload.

    Args:
        payload: Raw webhook payload from WAHA

    Returns:
        Extracted message data or None if message should be ignored
    """
    try:
        event = payload.get("event")

        # Only process "message" events (ignore "message.any" to avoid duplicates)
        if event != "message":
            logger.debug(f"Ignoring event: {event}")
            return None

        message_data = payload.get("payload", {})

        # Ignore messages sent by ourselves
        if message_data.get("fromMe", False):
            logger.debug("Ignoring message sent by us")
            return None

        # Extract core message information
        from_number = message_data.get("from", "")
        message_text = message_data.get("body", "")
        message_type = message_data.get("type", "text")
        session = payload.get("session", "default")
        message_id = message_data.get("id", "")

        # Extrair numero REAL do telefone (importante para @lid)
        # Quando from e @lid, o numero real esta em 'participant'
        if from_number.endswith("@lid"):
            participant = message_data.get("participant", "")
            if participant:
                real_phone = participant.replace("@c.us", "")
            else:
                real_phone = from_number.replace("@lid", "")
            logger.info(f"@lid detected: from={from_number}, real_phone={real_phone}")
        else:
            real_phone = from_number.replace("@c.us", "")

        # Skip empty messages
        if not message_text and message_type == "text":
            logger.debug("Ignoring empty text message")
            return None

        # Extract quoted message information (when user replies to a message)
        has_quoted = False
        quoted_message = None

        # WAHA pode usar diferentes campos para mensagens citadas
        quoted_msg = message_data.get("quotedMsg") or message_data.get("quotedMessage") or {}
        if quoted_msg:
            has_quoted = True
            quoted_message = {
                "id": quoted_msg.get("id", ""),
                "body": quoted_msg.get("body", "") or quoted_msg.get("caption", ""),
                "type": quoted_msg.get("type", ""),
                "from": quoted_msg.get("from", ""),
            }
            logger.info(f"Message has quoted reply: {quoted_message.get('body', '')[:50]}...")

        return {
            "from_number": from_number,
            "real_phone": real_phone,  # Numero real do telefone (sem @c.us/@lid)
            "message_text": message_text,
            "message_type": message_type,
            "session": session,
            "message_id": message_id,
            "timestamp": message_data.get("timestamp", datetime.utcnow().timestamp()),
            "raw_payload": message_data,
            "has_quoted_message": has_quoted,
            "quoted_message": quoted_message
        }
    except Exception as e:
        logger.exception(f"Error extracting message data: {e}")
        return None


def get_ai_response_sync(
    message_text: str,
    conversation_id: str,
    property_context: dict = None,
    is_landing_page: bool = False,
    landing_property: dict = None,
    properties_available: int = None,
    active_visit: dict = None
) -> str:
    """
    Get AI response using OpenRouter API (synchronous).

    Args:
        message_text: User's message text
        conversation_id: Conversation identifier
        property_context: Optional dict with property info from property selection
        is_landing_page: True if lead came from landing page
        landing_property: Property dict from landing page context
        properties_available: Number of properties available (None if not checked)
        active_visit: Visit dict if lead has an active scheduled visit

    Returns:
        AI-generated response text
    """
    try:
        import httpx

        # Use prompt diferenciado para landing leads
        if is_landing_page and landing_property:
            landing_prompt = get_system_prompt_for_lead(True, landing_property)
            if landing_prompt:
                system_prompt = landing_prompt
            else:
                # Fallback to default
                system_prompt = """Voce e um assistente imobiliario do Ceara conversando pelo WhatsApp.

REGRAS:
- Respostas CURTAS (2-3 frases)
- UMA pergunta por vez
- SEM EMOJIS
- NUNCA peca numero de WhatsApp (voce JA esta no WhatsApp)

Foco em agendar visita para o imovel especifico."""
        else:
            system_prompt = """Voce e um assistente imobiliario do Ceara conversando pelo WhatsApp.

REGRAS:
- Respostas CURTAS (2-3 frases)
- UMA pergunta por vez
- SEM EMOJIS
- NUNCA peca numero de WhatsApp (voce JA esta no WhatsApp)

DADOS OBRIGATORIOS PARA AGENDAMENTO:
Antes de confirmar QUALQUER visita, voce DEVE ter coletado:
1. Nome do cliente
2. Bairro de interesse
3. Numero de quartos

IMPORTANTE: Se o lead tentar agendar visita SEM esses 3 dados, NAO confirme.
Pergunte os dados que faltam PRIMEIRO.

Exemplo:
Lead: "Quero agendar visita amanha"
Voce: "Claro! Para agendar, me diz: qual seu nome, quantos quartos procura e qual bairro de preferencia?"

FLUXO DE QUALIFICACAO:
1. Cumprimentar e perguntar nome: "Como posso te chamar?"
2. Regiao de interesse (bairro)
3. Quantidade de quartos
4. Renda mensal: "Qual sua renda mensal aproximada?"
   - Usar para calcular limite de financiamento: Renda x 30% x 360
   - IMPORTANTE: Perguntar renda ANTES de enviar opcoes de imoveis

QUANDO LEAD PEDIR OPCOES/FOTOS:
- Se NAO tiver renda ainda, pergunte: "Para te enviar opcoes adequadas, qual sua renda mensal aproximada?"
- Se contexto indicar [DISPONIBILIDADE: X imoveis disponiveis], responda "Vou te enviar algumas opcoes agora"
- Se contexto indicar [DISPONIBILIDADE: NAO ha imoveis disponiveis], NUNCA diga que vai enviar. Responda algo como "No momento nao encontrei imoveis com esses criterios. Posso buscar em outro bairro ou ajustar os criterios?"
- Sistema envia fotos automaticamente SE houver imoveis

QUANDO LEAD ESCOLHER UM IMOVEL:
- Confirme interesse: "Gostou desse?"
- Se tiver os 3 dados (nome, bairro, quartos), ofereca agendar visita
- Se NAO tiver, pergunte os dados faltantes antes

FLUXO DE AGENDAMENTO (somente se tiver nome, bairro e quartos):
1. Pergunte data preferida
2. Pergunte horario (manha, tarde)
3. Confirme: "Visita agendada! Um corretor entrara em contato para confirmar."

CONFIRMACAO DE DATA:
Quando o lead mencionar datas relativas (sexta, proxima semana, mes que vem):
1. SEMPRE confirme a data especifica: "Seria dia DD/MM (dia da semana). Pode ser?"
2. Pergunte o horario se nao informado: "Prefere manha ou tarde?"
3. SO confirme o agendamento apos lead aprovar data E horario

Exemplo:
Lead: "Quero marcar pra proxima sexta"
Voce: "Otimo! Seria sexta dia 27/12. Qual horario voce prefere?"
Lead: "14h"
Voce: "Perfeito! Visita confirmada para sexta 27/12 as 14h. Um corretor entrara em contato!"

NUNCA agende diretamente sem o lead confirmar a data exata.

Se receber contexto de imovel SELECIONADO, foque nele e ofereça visita.
Seja conversacional e direto."""

        # Injetar data atual no prompt para o AI calcular datas corretamente
        today = datetime.now()
        weekday_names = ["segunda-feira", "terca-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sabado", "domingo"]
        today_weekday = weekday_names[today.weekday()]

        # Calcular próximos dias da semana para referência
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:  # Se já é sexta, vai para próxima
            days_until_friday = 7
        next_friday = today + timedelta(days=days_until_friday)

        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:  # Se já é sábado, vai para próximo
            days_until_saturday = 7
        next_saturday = today + timedelta(days=days_until_saturday)

        date_context = f"""DATA ATUAL: Hoje é {today_weekday}, {today.strftime('%d/%m/%Y')}.
Proxima sexta-feira: {next_friday.strftime('%d/%m/%Y')}
Proximo sabado: {next_saturday.strftime('%d/%m/%Y')}
Use essas datas como referencia ao confirmar agendamentos.

"""
        # Prepend ao system_prompt
        system_prompt = date_context + system_prompt

        # Build user message with property context if available
        user_message = message_text
        if property_context:
            # Caso 1: Lead SELECIONOU um imovel (citou/marcou mensagem)
            if property_context.get("selected"):
                property_info = property_context.get("property_info", "um imovel")
                intent = property_context.get("intent", "interest")
                if intent == "schedule":
                    context_info = f"[LEAD SELECIONOU IMOVEL E QUER AGENDAR VISITA: {property_info}]"
                else:
                    context_info = f"[LEAD SELECIONOU IMOVEL (marcou/citou mensagem): {property_info}]"
            # Caso 2: Lead veio de landing page com interesse em imovel especifico
            else:
                context_info = f"[Lead interessado em: {property_context.get('title', 'Imovel')} - {property_context.get('price', 'Preco nao informado')} - {property_context.get('location', 'Localizacao nao informada')}]"
            user_message = f"{context_info}\n{message_text}"

        # Injetar info de disponibilidade de imoveis se relevante
        if properties_available is not None:
            if properties_available > 0:
                availability_context = f"[DISPONIBILIDADE: {properties_available} imoveis disponiveis com os criterios do lead]"
            else:
                availability_context = "[DISPONIBILIDADE: NAO ha imoveis disponiveis com os criterios atuais do lead - informe isso e sugira ajustar bairro ou outros criterios]"
            user_message = f"{availability_context}\n{user_message}"

        # Injetar contexto de visita ativa se lead já tem visita agendada
        if active_visit:
            visit_date = active_visit.get("scheduled_date", "data agendada")
            visit_time = active_visit.get("scheduled_time", "horario agendado")
            visit_id = active_visit.get("id", "")
            visit_context = f"[VISITA JA AGENDADA: #{visit_id} para {visit_date} as {visit_time}. NAO ofereca mais opcoes de imoveis. Responda educadamente e confirme a visita ja marcada.]"
            user_message = f"{visit_context}\n{user_message}"

        # Injetar historico de visitas anteriores do lead (para contexto)
        try:
            # Extrair lead_number do conversation_id (whatsapp_PHONE@c.us)
            lead_number = conversation_id.replace("whatsapp_", "") if conversation_id.startswith("whatsapp_") else conversation_id
            visit_history = get_lead_visit_history(lead_number, lead_number.replace("@c.us", "").replace("@lid", ""))

            if visit_history:
                history_context = format_visit_history_for_ai(visit_history)
                if history_context:
                    user_message = f"{history_context}\n{user_message}"
                    logger.info(f"Injected {len(visit_history)} visit history records for {conversation_id}")
        except Exception as e:
            logger.warning(f"Error getting visit history for AI context: {e}")

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://sells.orquestr.ai",
            "X-Title": "Sells - Real Estate Assistant"
        }

        # Build messages array with conversation history
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(get_conversation_history(conversation_id))
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": "google/gemini-3-flash-preview",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 150
        }

        # Use httpx client for API calls
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            ai_message = data["choices"][0]["message"]["content"]

            logger.info(f"Got AI response for conversation {conversation_id}")
            return ai_message

    except Exception as e:
        logger.exception(f"Error getting AI response: {e}")
        return "Olá! Estou aqui para ajudá-lo a encontrar o imóvel ideal. Como posso ajudar?"


def calculate_human_delay(response_text: str) -> float:
    """
    Calcula delay aleatorio para simular digitacao humana.

    Componentes:
    1. "Thinking time" - tempo para ler e pensar na resposta
    2. "Typing time" - tempo proporcional ao tamanho da mensagem

    Returns:
        Delay em segundos
    """
    # Tempo de "pensar" (aleatorio)
    thinking_time = random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX)

    # Tempo de "digitar" (proporcional ao texto)
    char_count = len(response_text)
    typing_time = char_count / CHARS_PER_SECOND

    # Adiciona variacao de +/- 20%
    typing_time *= random.uniform(0.8, 1.2)

    total_delay = thinking_time + typing_time

    # Limita entre 2 e 12 segundos para nao parecer suspeito
    return min(max(total_delay, 2.0), 12.0)


def send_waha_message_sync(session: str, chat_id: str, text: str) -> dict[str, Any]:
    """
    Send a text message via WAHA API directly using requests (synchronous).

    Args:
        session: WAHA session name
        chat_id: WhatsApp chat ID (e.g., "5585996227722@c.us")
        text: Message text to send

    Returns:
        WAHA API response
    """
    url = f"{WAHA_BASE_URL}/api/sendText"  # Define before try to avoid UnboundLocalError
    try:
        import requests
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": WAHA_API_KEY
        }
        payload = {
            "session": session,
            "chatId": chat_id,
            "text": text
        }

        logger.info(f"Sending message to WAHA: url={url}, chatId={chat_id}, session={session}")

        # Use requests library which has better Docker networking compatibility
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Message sent successfully to {chat_id}")
        return result

    except Exception as e:
        logger.exception(f"Error sending WAHA message to {url}: {e}")
        raise


def mark_as_seen_sync(session: str, chat_id: str) -> bool:
    """
    Marca mensagens como lidas/vistas via WAHA API.
    Mostra check azul para o lead.
    """
    url = f"{WAHA_BASE_URL}/api/{session}/sendSeen"
    try:
        import requests
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": WAHA_API_KEY
        }
        payload = {
            "session": session,
            "chatId": chat_id
        }
        logger.info(f"Marking message as seen for {chat_id}")
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Message marked as seen for {chat_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to mark as seen: {e}")
        return False


def send_typing_indicator_sync(session: str, chat_id: str) -> bool:
    """
    Envia indicador de 'digitando...' via WAHA API.
    Mostra "digitando..." no WhatsApp do lead.
    """
    url = f"{WAHA_BASE_URL}/api/{session}/presence"
    try:
        import requests
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": WAHA_API_KEY
        }
        payload = {
            "chatId": chat_id,
            "presence": "typing"
        }
        logger.info(f"Sending typing indicator to {chat_id}")
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Typing indicator sent to {chat_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send typing indicator: {e}")
        return False


def process_message_sync(message_data: dict[str, Any]) -> dict[str, Any]:
    """
    Process incoming WhatsApp message and send AI response (synchronous).

    Args:
        message_data: Extracted message data

    Returns:
        Processing result
    """
    try:
        from_number = message_data["from_number"]
        message_text = message_data["message_text"]
        session = message_data["session"]
        has_quoted = message_data.get("has_quoted_message", False)
        quoted_msg = message_data.get("quoted_message")

        logger.info(f"Processing message from {from_number}: {message_text[:50]}...")

        # Marcar mensagem como lida (check azul no WhatsApp do lead)
        mark_as_seen_sync(session, from_number)

        # Create conversation ID
        conversation_id = f"whatsapp_{from_number}"

        # ===== CANCELAR FOLLOW-UP DE LEAD FRIO =====
        # Lead respondeu! Cancelar timer pendente e resetar tier
        cancel_cold_lead_followup(conversation_id)

        # ===== DETECTAR LEAD DE LANDING PAGE =====
        real_phone = message_data.get("real_phone", from_number.replace("@c.us", "").replace("@lid", ""))
        is_landing_page_lead = False
        lp_context = None

        # Verifica se ja tem contexto em memoria
        if conversation_id not in landing_lead_context:
            # Busca no banco
            lp_context = get_landing_lead_by_phone(real_phone)
            if lp_context:
                landing_lead_context[conversation_id] = lp_context

                # Cancela follow-up se estava agendado
                cancel_followup(lp_context["lead_id"])

                # Marca que lead iniciou conversa
                try:
                    with get_db() as conn:
                        conn.execute(
                            "UPDATE landing_leads_v2 SET status = 'in_conversation', first_message_at = ? WHERE id = ?",
                            (datetime.now().isoformat(), lp_context["lead_id"])
                        )
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error updating landing lead status: {e}")

                logger.info(f"Landing page lead detected: {real_phone} -> {lp_context['property']['title']}")

        # Pega contexto se existir
        lp_context = landing_lead_context.get(conversation_id)
        is_landing_page_lead = lp_context is not None

        if is_landing_page_lead:
            logger.info(f"Processing landing page lead for property: {lp_context['property'].get('title', 'Unknown')}")

        # Adiciona mensagem do usuario ao historico ANTES de processar
        # (para que extract_filters e extract_lead_name vejam a mensagem atual)
        add_to_history(conversation_id, "user", message_text)

        # ===== PROCESSAR CONFIRMAÇÃO/FEEDBACK DE VISITA =====
        visit_for_confirmation = lead_has_scheduled_visit(from_number, real_phone)
        if visit_for_confirmation:
            message_lower = message_text.lower().strip()

            # Verificar se é resposta de confirmação
            if visit_for_confirmation.get("confirmation_sent") and not visit_for_confirmation.get("lead_confirmed"):
                if is_confirmation_response(message_text):
                    if any(w in message_lower for w in ["sim", "confirmo", "vou", "irei"]):
                        visit_for_confirmation["lead_confirmed"] = True
                        visit_for_confirmation["lead_confirmed_at"] = datetime.now().isoformat()
                        response = "Confirmado! Estaremos te esperando. Ate mais tarde!"
                        # Notificar corretor
                        notify_broker_lead_confirmed(visit_for_confirmation)
                        # Persistir no banco
                        update_visit_in_db(visit_for_confirmation["id"], {
                            "lead_confirmed": 1,
                            "lead_confirmed_at": datetime.now().isoformat(),
                            "status": "confirmed"
                        })
                    else:
                        visit_for_confirmation["status"] = "cancelled"
                        response = "Entendi, visita cancelada. Posso ajudar a reagendar para outro dia?"
                        # Persistir cancelamento no banco
                        update_visit_in_db(visit_for_confirmation["id"], {
                            "status": "cancelled"
                        })

                    # Enviar resposta e encerrar processamento
                    send_typing_indicator_sync(session, from_number)
                    time.sleep(1)
                    send_waha_message_sync(session, from_number, response)
                    add_to_history(conversation_id, "assistant", response)
                    logger.info(f"Processed confirmation response for visit #{visit_for_confirmation['id']}")
                    return {"status": "success", "type": "confirmation_response"}

            # Verificar se é feedback (nota 1-5)
            if visit_for_confirmation.get("feedback_requested") and not visit_for_confirmation.get("feedback_score"):
                score = extract_feedback_score(message_text)
                if score:
                    visit_for_confirmation["feedback_score"] = score
                    visit_for_confirmation["status"] = "completed"

                    if score >= 4:
                        response = "Obrigado pelo feedback! Ficamos felizes que gostou do atendimento. Se precisar de mais ajuda, estou aqui!"
                    else:
                        response = "Obrigado pelo feedback. Vamos trabalhar para melhorar! O que podemos fazer de diferente na proxima vez?"
                        visit_for_confirmation["needs_improvement"] = True

                    # Persistir feedback no banco
                    update_visit_in_db(visit_for_confirmation["id"], {
                        "feedback_score": score,
                        "feedback_at": datetime.now().isoformat(),
                        "status": "completed"
                    })

                    # Enviar resposta e encerrar processamento
                    send_typing_indicator_sync(session, from_number)
                    time.sleep(1)
                    send_waha_message_sync(session, from_number, response)
                    add_to_history(conversation_id, "assistant", response)
                    logger.info(f"Processed feedback (score={score}) for visit #{visit_for_confirmation['id']}")
                    return {"status": "success", "type": "feedback_response", "score": score}

        # ===== DETECTAR SELECAO DE IMOVEL =====
        selection = detect_property_selection(message_text, has_quoted, quoted_msg)
        logger.info(f"Property selection analysis: {selection}")

        # Se lead selecionou um imovel, NAO enviar mais opcoes
        property_context = None
        if selection["has_selection"]:
            logger.info(f"Lead selected a property! Type: {selection['selection_type']}, Intent: {selection['intent']}")

            # Criar contexto para IA saber que lead escolheu
            if quoted_msg and quoted_msg.get("body"):
                property_context = {
                    "selected": True,
                    "property_info": quoted_msg.get("body", "")[:200],
                    "intent": selection["intent"]
                }
                # ===== ARMAZENAR PROPRIEDADE SELECIONADA para agendamento =====
                selected_property_context[conversation_id] = {
                    "title": "Imovel selecionado",
                    "info": quoted_msg.get("body", "")[:200]
                }
                logger.info(f"Stored selected property context for {conversation_id}")
            else:
                property_context = {
                    "selected": True,
                    "intent": selection["intent"]
                }

        # ===== DETECTAR AGENDAMENTO DE VISITA =====
        scheduling = detect_scheduling_intent(message_text, conversation_id)

        if scheduling["has_scheduling"]:
            logger.info(f"Scheduling intent detected! Validating lead data...")

            # Primeiro: Tentar extração via AI (mais precisa para respostas curtas)
            ai_data = extract_lead_data_with_ai(conversation_id)

            # Segundo: Fallback para regex
            filters = extract_filters_from_history(conversation_id)
            lead_name = extract_lead_name(conversation_id)

            # Combinar dados: AI tem prioridade, depois regex
            final_name = ai_data.get("name") or lead_name
            final_neighborhood = ai_data.get("neighborhood") or filters.get("neighborhood", "Nao informado")
            final_bedrooms = ai_data.get("bedrooms") or filters.get("bedrooms", "Nao informado")
            final_renda = ai_data.get("renda") or filters.get("renda", 0)

            # Validar se temos dados mínimos
            missing_fields = []
            if final_name == "Nao informado" or not final_name:
                missing_fields.append("nome")
            if final_neighborhood == "Nao informado" or not final_neighborhood:
                missing_fields.append("bairro")
            if final_bedrooms == "Nao informado" or not final_bedrooms:
                missing_fields.append("quartos")

            if missing_fields:
                # Dados incompletos - não agendar ainda, AI vai pedir os dados
                logger.info(f"Scheduling BLOCKED - missing data: {', '.join(missing_fields)}")
                logger.info(f"AI will ask for missing data in next response")
            else:
                # Dados completos - prosseguir com agendamento
                logger.info(f"Scheduling APPROVED - all required data present")

                lead_data = {
                    "name": final_name,
                    "phone": message_data.get("real_phone", from_number.replace("@c.us", "").replace("@lid", "")),
                    "neighborhood": final_neighborhood,
                    "bedrooms": final_bedrooms,
                    "renda": final_renda if final_renda else 0,
                    "max_price": filters.get("max_price", 0)
                }
                logger.info(f"Lead data for notification: {lead_data}")

                visit = store_and_notify_visit(
                    from_number,
                    scheduling["datetime_info"],
                    scheduling["property_context"],
                    session,
                    lead_data
                )
                # Limpa contexto apos agendamento bem-sucedido
                selected_property_context.pop(conversation_id, None)
                logger.info(f"Visit scheduled and broker notified: {visit}")

        # Detecta pedido de fotos/opcoes na MENSAGEM DO USUARIO
        message_lower = message_text.lower()
        user_wants_properties = any(keyword in message_lower for keyword in [
            "foto", "fotos", "imagem", "imagens",
            "opcao", "opcoes", "opção", "opções",
            "imovel", "imoveis", "imóvel", "imóveis",
            "apartamento", "casa", "ver", "mostrar",
            "tem o que", "tem algo", "disponivel", "disponível"
        ])

        # ===== PRE-CHECK: Verificar disponibilidade de imoveis ANTES de gerar resposta =====
        available_count = None
        pre_filters = None
        try:
            # Adiciona mensagem atual ao historico temporariamente para extração
            temp_history = get_conversation_history(conversation_id) + [{"role": "user", "content": message_text}]

            # Extrai filtros incluindo a mensagem atual
            pre_filters = extract_filters_from_history(conversation_id)

            # Se tem filtros suficientes, consulta disponibilidade
            if pre_filters.get("neighborhood") or pre_filters.get("max_price") or pre_filters.get("bedrooms"):
                # Usa AI extraction para enriquecer filtros (como já fazemos em send_properties_to_lead)
                ai_data = extract_lead_data_with_ai(conversation_id)
                if ai_data:
                    if not pre_filters.get("bedrooms") and ai_data.get("bedrooms"):
                        pre_filters["bedrooms"] = str(ai_data.get("bedrooms"))
                    if not pre_filters.get("neighborhood") and ai_data.get("neighborhood"):
                        pre_filters["neighborhood"] = ai_data.get("neighborhood")
                    if not pre_filters.get("max_price") and ai_data.get("renda"):
                        try:
                            renda = float(ai_data.get("renda"))
                            pre_filters["max_price"] = renda * 0.30 * 360
                        except (ValueError, TypeError):
                            pass

                # Consulta Memude
                pre_search_results = search_properties_memude(pre_filters)
                available_count = len(pre_search_results) if pre_search_results else 0
                logger.info(f"Pre-check: {available_count} properties available for filters {pre_filters}")
        except Exception as e:
            logger.warning(f"Pre-check failed: {e}")
            available_count = None

        # Verificar se lead tem visita agendada ANTES de gerar resposta AI
        pre_active_visit = lead_has_scheduled_visit(from_number, real_phone)

        # Get AI response (synchronous) - passa contexto de selecao se houver
        # Para landing leads, passa contexto do imovel especifico
        if is_landing_page_lead and lp_context:
            ai_response = get_ai_response_sync(
                message_text,
                conversation_id,
                property_context,
                is_landing_page=True,
                landing_property=lp_context.get("property"),
                properties_available=available_count,
                active_visit=pre_active_visit
            )
        else:
            ai_response = get_ai_response_sync(
                message_text,
                conversation_id,
                property_context,
                properties_available=available_count,
                active_visit=pre_active_visit
            )

        # Detecta se AI disse que vai enviar opcoes na RESPOSTA
        ai_lower = ai_response.lower()
        ai_will_send = any(phrase in ai_lower for phrase in [
            "vou te enviar",
            "vou enviar",
            "enviar algumas",
            "enviar opcoes",
            "enviar opções",
            "te mostrar algumas",
            "mostrar algumas opcoes",
            "mostrar algumas opções"
        ])

        # ===== DECISAO: ENVIAR OPCOES OU NAO =====
        # Verificar se lead já tem visita agendada - NÃO enviar mais opções
        active_visit = lead_has_scheduled_visit(from_number, real_phone)
        if active_visit:
            should_send_properties = False
            logger.info(f"Lead has active visit #{active_visit['id']} - NOT sending more options")
        # Se lead veio de landing page, NAO enviar multiplas opcoes (foco no imovel especifico)
        elif is_landing_page_lead:
            should_send_properties = False
            logger.info("Landing page lead - NOT sending multiple options (focused on specific property)")
        elif selection["has_selection"]:
            should_send_properties = False
            logger.info("Lead selected a property - NOT sending more options")
        else:
            # Envia fotos se USUARIO pediu OU se AI disse que vai enviar
            should_send_properties = user_wants_properties or ai_will_send

        # Save AI response to history (user message already added at start)
        add_to_history(conversation_id, "assistant", ai_response)
        logger.info(f"Conversation history updated for {conversation_id} ({len(get_conversation_history(conversation_id))} messages)")

        # Humanized delay before sending (simulates reading + typing)
        delay = calculate_human_delay(ai_response)
        logger.info(f"Humanization delay: {delay:.1f}s for {len(ai_response)} chars")

        # Mostrar "digitando..." no WhatsApp do lead
        send_typing_indicator_sync(session, from_number)

        time.sleep(delay)

        # Send response via WhatsApp using direct WAHA API call (synchronous)
        send_result = send_waha_message_sync(session, from_number, ai_response)

        logger.info(f"Successfully sent AI response to {from_number}")

        # Se deve enviar fotos (usuario pediu OU AI disse que vai enviar)
        properties_sent = 0
        if should_send_properties:
            logger.info(f"Sending properties to {from_number} (user_request={user_wants_properties}, ai_promised={ai_will_send})")
            time.sleep(2)  # Pequeno delay antes das fotos

            # Extrai filtros da conversa (bairro, quartos, preco)
            filters = extract_filters_from_history(conversation_id)
            logger.info(f"Extracted filters from conversation: {filters}")

            # Busca e envia imoveis com filtros
            properties_sent = send_properties_to_lead(session, from_number, filters=filters, conversation_id=conversation_id)

            if properties_sent > 0:
                time.sleep(1)
                send_waha_message_sync(
                    session,
                    from_number,
                    f"Enviei {properties_sent} opcoes para voce. Algum te interessou?"
                )

        # ===== AGENDAR FOLLOW-UP PARA LEAD FRIO =====
        # Verificar se NÃO deve agendar follow-up frio
        message_lower = message_text.lower()
        should_skip_cold_followup = (
            active_visit is not None or  # Visita já agendada = follow-up de visita cobre
            "sem interesse" in message_lower or
            "nao quero" in message_lower or
            "nao tenho interesse" in message_lower or
            "nao preciso" in message_lower or
            "desisto" in message_lower or
            "cancelar" in message_lower
        )

        if not should_skip_cold_followup:
            # Agendar follow-up caso lead não responda
            schedule_cold_lead_followup(conversation_id, ai_response)
        else:
            logger.info(f"Skipping cold lead follow-up for {conversation_id} (active_visit or no interest)")

        return {
            "status": "success",
            "from_number": from_number,
            "response_sent": True,
            "properties_sent": properties_sent,
            "message_id": send_result.get("id", "")
        }

    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        raise


@app.route("/api/v1/whatsapp/webhook", methods=["POST", "GET"])
def webhook():
    """
    WhatsApp webhook endpoint.

    GET: Health check
    POST: Process incoming messages
    """
    if request.method == "GET":
        # Health check for webhook verification
        return jsonify({
            "status": "ok",
            "service": "whatsapp_webhook",
            "timestamp": datetime.utcnow().isoformat()
        }), 200

    # POST - Process incoming message
    try:
        payload = request.json

        if not payload:
            logger.warning("Received empty payload")
            return jsonify({"status": "error", "message": "Empty payload"}), 400

        stats["messages_received"] += 1
        logger.info(f"Webhook received: {payload.get('event', 'unknown')}")

        # Extract message data
        message_data = extract_message_data(payload)

        if not message_data:
            return jsonify({
                "status": "ignored",
                "reason": "Message filtered (not processable)"
            }), 200

        # Add to buffer instead of processing immediately
        # This allows aggregating multiple consecutive messages
        add_to_message_buffer(
            message_data["from_number"],
            message_data["message_text"],
            message_data["session"],
            message_data.get("real_phone")  # Passa o numero real para o buffer
        )

        return jsonify({
            "status": "buffered",
            "message": f"Message buffered, will process after {MESSAGE_BUFFER_DELAY}s",
            "timestamp": datetime.utcnow().isoformat()
        }), 200

    except Exception as e:
        stats["messages_failed"] += 1
        logger.exception(f"Error in webhook handler: {e}")

        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500


@app.route("/health", methods=["GET"])
def health():
    """
    Server health check endpoint.

    Returns server status and statistics.
    """
    uptime_seconds = (
        datetime.utcnow() -
        datetime.fromisoformat(stats["server_started_at"])
    ).total_seconds()

    return jsonify({
        "status": "healthy",
        "service": "whatsapp_webhook_server",
        "version": "1.0.0",
        "uptime_seconds": uptime_seconds,
        "stats": stats,
        "timestamp": datetime.utcnow().isoformat()
    }), 200


@app.route("/stats", methods=["GET"])
def get_stats():
    """
    Get server statistics.

    Returns detailed statistics about message processing.
    """
    return jsonify({
        "stats": stats,
        "timestamp": datetime.utcnow().isoformat()
    }), 200


@app.route("/visits", methods=["GET"])
def list_visits():
    """
    List all scheduled visits.

    Returns list of scheduled visits for debugging/monitoring.
    """
    return jsonify({
        "visits": list(scheduled_visits.values()),
        "count": len(scheduled_visits),
        "timestamp": datetime.now().isoformat()
    }), 200


# ============================================
# LANDING PAGE ENDPOINTS (SIMPLIFICADO)
# ============================================

@app.route("/api/landing-lead", methods=["POST"])
def register_landing_lead():
    """
    Recebe lead + dados do imovel da landing page (SIMPLIFICADO).

    Payload esperado:
    {
        "phone": "5585991234567",
        "name": "Joao Silva",
        "source_url": "https://meusite.com/aldeota-2quartos",
        "property": {
            "title": "Apartamento 2 Quartos - Aldeota",
            "price": 450000,
            "neighborhood": "Aldeota",
            "bedrooms": 2,
            "area": 85,
            "image_url": "https://...",
            "link": "https://memude.com.br/...",
            "description": "Apartamento bem localizado..."
        }
    }
    """
    try:
        data = request.json

        phone = data.get("phone", "").strip()
        name = data.get("name", "").strip()
        source_url = data.get("source_url", "")
        prop = data.get("property", {})

        if not phone or not prop.get("title"):
            return jsonify({"error": "phone e property.title sao obrigatorios"}), 400

        # Normaliza telefone (remove caracteres)
        phone = re.sub(r'\D', '', phone)
        if not phone.startswith("55"):
            phone = f"55{phone}"

        # Formata preco
        price = prop.get("price", 0)
        price_formatted = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if price else "Consultar"

        # Registra lead com dados do imovel embutidos
        with get_db() as conn:
            conn.execute('''
                INSERT INTO landing_leads_v2
                (phone, name, source_url, property_title, property_price, property_price_formatted,
                 property_neighborhood, property_bedrooms, property_area, property_image_url,
                 property_link, property_description, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (
                phone, name, source_url,
                prop.get("title"),
                price,
                price_formatted,
                prop.get("neighborhood", ""),
                prop.get("bedrooms", 0),
                prop.get("area", 0),
                prop.get("image_url", ""),
                prop.get("link", ""),
                prop.get("description", "")
            ))
            conn.commit()
            lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Agenda follow-up em 5 minutos
        schedule_followup(lead_id, phone, delay_seconds=300)

        logger.info(f"Landing lead registered: {phone} -> {prop.get('title')} (lead_id={lead_id})")

        return jsonify({
            "status": "success",
            "lead_id": lead_id,
            "message": "Lead registrado. Follow-up agendado para 5 minutos."
        }), 201

    except Exception as e:
        logger.exception(f"Error registering landing lead: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/landing-leads", methods=["GET"])
def list_landing_leads():
    """Lista todos os leads de landing pages (SIMPLIFICADO - dados inline)."""
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                SELECT * FROM landing_leads_v2
                ORDER BY registered_at DESC
            ''')
            leads = [dict(row) for row in cursor.fetchall()]

        return jsonify({"leads": leads, "count": len(leads)}), 200

    except Exception as e:
        logger.exception(f"Error listing leads: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# DASHBOARD API ENDPOINTS
# ============================================

@app.route("/api/v1/dashboard/leads", methods=["GET"])
def dashboard_get_leads():
    """
    Lista leads com paginacao e filtros.

    Query params:
    - page: numero da pagina (padrao: 1)
    - page_size: tamanho da pagina (padrao: 20)
    - status: filtrar por status (pending, contacted, qualified, converted)
    - search: buscar por nome ou telefone
    - date_from: filtrar por data inicial (ISO format)
    - date_to: filtrar por data final (ISO format)
    """
    try:
        # Parametros de paginacao
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        offset = (page - 1) * page_size

        # Parametros de filtro
        status = request.args.get("status")
        search = request.args.get("search")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        with get_db() as conn:
            # Construir query dinamicamente
            where_clauses = []
            params = []

            if status:
                where_clauses.append("status = ?")
                params.append(status)

            if search:
                where_clauses.append("(phone LIKE ? OR name LIKE ?)")
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])

            if date_from:
                where_clauses.append("registered_at >= ?")
                params.append(date_from)

            if date_to:
                where_clauses.append("registered_at <= ?")
                params.append(date_to)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Contar total
            count_query = f"SELECT COUNT(*) as total FROM landing_leads_v2 WHERE {where_sql}"
            total = conn.execute(count_query, params).fetchone()["total"]

            # Buscar dados paginados
            data_query = f"""
                SELECT * FROM landing_leads_v2
                WHERE {where_sql}
                ORDER BY registered_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([page_size, offset])
            cursor = conn.execute(data_query, params)
            leads = [dict(row) for row in cursor.fetchall()]

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        # Transform leads data to match frontend expectations
        transformed_leads = []
        for lead in leads:
            transformed_leads.append({
                "id": str(lead["id"]),
                "name": lead.get("name", ""),
                "phone": lead.get("phone", ""),
                "email": None,
                "status": lead.get("status", "novo"),
                "created_at": lead.get("registered_at", ""),
                "updated_at": lead.get("registered_at", ""),
                "preferences": {
                    "property_type": lead.get("property_title", ""),
                    "bedrooms": lead.get("property_bedrooms"),
                    "min_price": None,
                    "max_price": lead.get("property_price"),
                    "neighborhoods": [lead.get("property_neighborhood")] if lead.get("property_neighborhood") else [],
                    "additional_notes": lead.get("property_description", "")
                },
                "score": lead.get("qualification_score")
            })

        return jsonify({
            "leads": transformed_leads,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }), 200

    except Exception as e:
        logger.exception(f"Error getting dashboard leads: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/leads/<int:lead_id>", methods=["GET"])
def dashboard_get_lead(lead_id: int):
    """
    Retorna dados detalhados de um lead especifico.
    """
    try:
        with get_db() as conn:
            lead = conn.execute(
                "SELECT * FROM landing_leads_v2 WHERE id = ?",
                (lead_id,)
            ).fetchone()

            if not lead:
                return jsonify({"error": "Lead not found"}), 404

            lead_row = dict(lead)

            # Buscar visitas associadas ao lead
            visits_cursor = conn.execute('''
                SELECT * FROM property_visits
                WHERE lead_phone = ?
                ORDER BY created_at DESC
            ''', (lead_row["phone"],))

            visits = []
            for row in visits_cursor:
                visit = dict(row)
                # Deserializar JSON
                if visit.get("property_info"):
                    try:
                        visit["property_info"] = json.loads(visit["property_info"])
                    except:
                        visit["property_info"] = {}
                visits.append(visit)

            # Transform to match frontend expectations
            lead_data = {
                "id": str(lead_row["id"]),
                "name": lead_row.get("name", ""),
                "phone": lead_row.get("phone", ""),
                "email": None,
                "status": lead_row.get("status", "novo"),
                "created_at": lead_row.get("registered_at", ""),
                "updated_at": lead_row.get("registered_at", ""),
                "preferences": {
                    "property_type": lead_row.get("property_title", ""),
                    "bedrooms": lead_row.get("property_bedrooms"),
                    "min_price": None,
                    "max_price": lead_row.get("property_price"),
                    "neighborhoods": [lead_row.get("property_neighborhood")] if lead_row.get("property_neighborhood") else [],
                    "additional_notes": lead_row.get("property_description", "")
                },
                "score": lead_row.get("qualification_score"),
                "visits": visits
            }

            return jsonify(lead_data), 200

    except Exception as e:
        logger.exception(f"Error getting lead {lead_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/leads/<int:lead_id>/conversation", methods=["GET"])
def dashboard_get_lead_conversation(lead_id: int):
    """
    Retorna historico de conversa de um lead.
    """
    try:
        with get_db() as conn:
            # Buscar lead para obter o telefone
            lead = conn.execute(
                "SELECT phone FROM landing_leads_v2 WHERE id = ?",
                (lead_id,)
            ).fetchone()

            if not lead:
                return jsonify({"error": "Lead not found"}), 404

            phone = lead["phone"]

            # Construir conversation_id (formato: whatsapp_5585999999999@c.us)
            # Tentar multiplos formatos possiveis
            conversation_ids = [
                f"whatsapp_{phone}@c.us",
                f"whatsapp_{phone}@lid",
                f"whatsapp_{phone}",
                phone  # Fallback direto
            ]

            # Query com IN clause para buscar em todos os formatos de uma vez
            placeholders = ','.join(['?' for _ in conversation_ids])
            cursor = conn.execute(f'''
                SELECT id, role, content, created_at
                FROM conversation_messages
                WHERE conversation_id IN ({placeholders})
                ORDER BY created_at ASC
            ''', conversation_ids)

            # Transformar para formato esperado pelo frontend
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": str(row["id"]),
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["created_at"]  # Frontend espera 'timestamp'
                })

            return jsonify({
                "lead_id": str(lead_id),
                "phone": phone,
                "messages": messages
            }), 200

    except Exception as e:
        logger.exception(f"Error getting conversation for lead {lead_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/leads/<int:lead_id>", methods=["PATCH"])
def dashboard_update_lead(lead_id: int):
    """
    Atualiza dados de um lead.

    Body JSON:
    {
        "status": "qualified",
        "qualification_score": 85,
        "qualification_budget": "300k-500k",
        "qualification_region": "Aldeota",
        "qualification_intent": "buy"
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Campos permitidos para atualizacao
        allowed_fields = [
            "status", "name", "qualification_score", "qualification_budget",
            "qualification_region", "qualification_intent", "last_interaction_at"
        ]

        # Construir query de update dinamicamente
        updates = []
        params = []

        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = ?")
                params.append(data[field])

        if not updates:
            return jsonify({"error": "No valid fields to update"}), 400

        params.append(lead_id)
        update_sql = f"""
            UPDATE landing_leads_v2
            SET {", ".join(updates)}
            WHERE id = ?
        """

        with get_db() as conn:
            # Verificar se lead existe
            lead = conn.execute(
                "SELECT id FROM landing_leads_v2 WHERE id = ?",
                (lead_id,)
            ).fetchone()

            if not lead:
                return jsonify({"error": "Lead not found"}), 404

            # Executar update
            conn.execute(update_sql, params)
            conn.commit()

            # Retornar lead atualizado
            updated_lead = conn.execute(
                "SELECT * FROM landing_leads_v2 WHERE id = ?",
                (lead_id,)
            ).fetchone()

            return jsonify(dict(updated_lead)), 200

    except Exception as e:
        logger.exception(f"Error updating lead {lead_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/visits", methods=["GET"])
def dashboard_get_visits():
    """
    Lista visitas com paginacao e filtros.

    Query params:
    - page: numero da pagina (padrao: 1)
    - page_size: tamanho da pagina (padrao: 20)
    - status: filtrar por status (pending, confirmed, completed, cancelled)
    - date_from: filtrar por data inicial
    - date_to: filtrar por data final
    - broker_id: filtrar por corretor
    """
    try:
        # Parametros de paginacao
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        offset = (page - 1) * page_size

        # Parametros de filtro
        status = request.args.get("status")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        broker_id = request.args.get("broker_id")

        with get_db() as conn:
            # Construir query dinamicamente
            where_clauses = []
            params = []

            if status:
                where_clauses.append("status = ?")
                params.append(status)

            if date_from:
                where_clauses.append("scheduled_datetime >= ?")
                params.append(date_from)

            if date_to:
                where_clauses.append("scheduled_datetime <= ?")
                params.append(date_to)

            if broker_id:
                where_clauses.append("broker_id = ?")
                params.append(broker_id)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Contar total
            count_query = f"SELECT COUNT(*) as total FROM property_visits WHERE {where_sql}"
            total = conn.execute(count_query, params).fetchone()["total"]

            # Buscar dados paginados
            data_query = f"""
                SELECT * FROM property_visits
                WHERE {where_sql}
                ORDER BY scheduled_datetime DESC
                LIMIT ? OFFSET ?
            """
            params.extend([page_size, offset])
            cursor = conn.execute(data_query, params)

            visits = []
            for row in cursor.fetchall():
                visit = dict(row)
                # Deserializar JSON
                if visit.get("lead_data"):
                    try:
                        visit["lead_data"] = json.loads(visit["lead_data"])
                    except:
                        visit["lead_data"] = {}
                if visit.get("property_info"):
                    try:
                        visit["property_info"] = json.loads(visit["property_info"])
                    except:
                        visit["property_info"] = {}
                visits.append(visit)

        # Transform visits data to match frontend expectations
        transformed_visits = []
        for visit in visits:
            lead_data = visit.get("lead_data", {}) or {}
            property_info = visit.get("property_info", {}) or {}
            scheduled_dt = visit.get("scheduled_datetime", "")

            # Parse scheduled datetime
            scheduled_date = ""
            scheduled_time = ""
            if scheduled_dt:
                try:
                    dt_parts = scheduled_dt.split("T")
                    scheduled_date = dt_parts[0] if len(dt_parts) > 0 else ""
                    scheduled_time = dt_parts[1][:5] if len(dt_parts) > 1 else "00:00"
                except:
                    scheduled_date = scheduled_dt[:10] if len(scheduled_dt) >= 10 else ""
                    scheduled_time = "00:00"

            transformed_visits.append({
                "id": visit.get("id", ""),
                "lead_id": visit.get("lead_phone", ""),
                "lead_name": lead_data.get("name", visit.get("lead_phone", "")),
                "property_id": None,
                "property_address": property_info.get("address", property_info.get("title", "")),
                "property_type": property_info.get("type", property_info.get("title", "")),
                "scheduled_date": scheduled_date,
                "scheduled_time": scheduled_time,
                "status": visit.get("status", "pendente"),
                "notes": visit.get("notes", ""),
                "created_at": visit.get("created_at", "")
            })

        return jsonify({
            "visits": transformed_visits,
            "total": total
        }), 200

    except Exception as e:
        logger.exception(f"Error getting dashboard visits: {e}")
        return jsonify({"visits": [], "total": 0}), 500


@app.route("/api/v1/dashboard/visits/<visit_uuid>", methods=["GET"])
def dashboard_get_visit(visit_uuid: str):
    """
    Retorna dados detalhados de uma visita especifica.
    """
    try:
        with get_db() as conn:
            visit = conn.execute(
                "SELECT * FROM property_visits WHERE visit_uuid = ?",
                (visit_uuid,)
            ).fetchone()

            if not visit:
                return jsonify({"error": "Visit not found"}), 404

            visit_data = dict(visit)

            # Deserializar JSON
            if visit_data.get("lead_data"):
                try:
                    visit_data["lead_data"] = json.loads(visit_data["lead_data"])
                except:
                    visit_data["lead_data"] = {}

            if visit_data.get("property_info"):
                try:
                    visit_data["property_info"] = json.loads(visit_data["property_info"])
                except:
                    visit_data["property_info"] = {}

            # Buscar dados do corretor se existir
            if visit_data.get("broker_id"):
                broker = conn.execute(
                    "SELECT * FROM brokers WHERE id = ?",
                    (visit_data["broker_id"],)
                ).fetchone()
                visit_data["broker"] = dict(broker) if broker else None

            return jsonify(visit_data), 200

    except Exception as e:
        logger.exception(f"Error getting visit {visit_uuid}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/visits/<visit_uuid>", methods=["PATCH"])
def dashboard_update_visit(visit_uuid: str):
    """
    Atualiza dados de uma visita.

    Body JSON:
    {
        "status": "completed",
        "broker_id": 1,
        "feedback_score": 5,
        "broker_confirmed": 1
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Campos permitidos para atualizacao
        allowed_fields = [
            "status", "broker_id", "feedback_score", "broker_confirmed",
            "lead_confirmed", "confirmation_sent", "feedback_requested"
        ]

        # Construir query de update dinamicamente
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params = []

        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = ?")
                params.append(data[field])

                # Adicionar timestamps de confirmacao se aplicavel
                if field == "broker_confirmed" and data[field]:
                    updates.append("broker_confirmed_at = CURRENT_TIMESTAMP")
                elif field == "lead_confirmed" and data[field]:
                    updates.append("lead_confirmed_at = CURRENT_TIMESTAMP")
                elif field == "feedback_score" and data[field]:
                    updates.append("feedback_at = CURRENT_TIMESTAMP")

        if len(updates) == 1:  # Apenas updated_at
            return jsonify({"error": "No valid fields to update"}), 400

        params.append(visit_uuid)
        update_sql = f"""
            UPDATE property_visits
            SET {", ".join(updates)}
            WHERE visit_uuid = ?
        """

        with get_db() as conn:
            # Verificar se visita existe
            visit = conn.execute(
                "SELECT id FROM property_visits WHERE visit_uuid = ?",
                (visit_uuid,)
            ).fetchone()

            if not visit:
                return jsonify({"error": "Visit not found"}), 404

            # Executar update
            conn.execute(update_sql, params)
            conn.commit()

            # Retornar visita atualizada
            updated_visit = conn.execute(
                "SELECT * FROM property_visits WHERE visit_uuid = ?",
                (visit_uuid,)
            ).fetchone()

            visit_data = dict(updated_visit)

            # Deserializar JSON
            if visit_data.get("lead_data"):
                try:
                    visit_data["lead_data"] = json.loads(visit_data["lead_data"])
                except:
                    visit_data["lead_data"] = {}

            if visit_data.get("property_info"):
                try:
                    visit_data["property_info"] = json.loads(visit_data["property_info"])
                except:
                    visit_data["property_info"] = {}

            return jsonify(visit_data), 200

    except Exception as e:
        logger.exception(f"Error updating visit {visit_uuid}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/metrics", methods=["GET"])
def dashboard_get_metrics():
    """
    Retorna metricas e KPIs do dashboard.

    Returns:
    {
        "total_leads": 150,
        "leads_today": 8,
        "total_visits": 45,
        "pending_visits": 12,
        "completed_visits": 10,
        "conversion_rate": 30.0
    }
    """
    try:
        with get_db() as conn:
            # Total de leads
            total_leads = conn.execute(
                "SELECT COUNT(*) as count FROM landing_leads_v2"
            ).fetchone()["count"]

            # Leads de hoje
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            leads_today = conn.execute(
                "SELECT COUNT(*) as count FROM landing_leads_v2 WHERE registered_at >= ?",
                (today_start,)
            ).fetchone()["count"]

            # Total de visitas
            total_visits = conn.execute(
                "SELECT COUNT(*) as count FROM property_visits"
            ).fetchone()["count"]

            # Visitas pendentes
            pending_visits = conn.execute(
                "SELECT COUNT(*) as count FROM property_visits WHERE status = 'pending'"
            ).fetchone()["count"]

            # Visitas confirmadas
            confirmed_visits = conn.execute(
                "SELECT COUNT(*) as count FROM property_visits WHERE status = 'confirmed'"
            ).fetchone()["count"]

            # Visitas completadas
            completed_visits = conn.execute(
                "SELECT COUNT(*) as count FROM property_visits WHERE status = 'completed'"
            ).fetchone()["count"]

            # Taxa de conversao (leads que geraram visitas)
            leads_with_visits = conn.execute('''
                SELECT COUNT(DISTINCT l.id) as count
                FROM landing_leads_v2 l
                INNER JOIN property_visits v ON l.phone = v.lead_phone
            ''').fetchone()["count"]

            conversion_rate = (leads_with_visits / total_leads * 100) if total_leads > 0 else 0.0

            # Leads por status
            leads_by_status = {}
            cursor = conn.execute('''
                SELECT status, COUNT(*) as count
                FROM landing_leads_v2
                GROUP BY status
            ''')
            for row in cursor:
                leads_by_status[row["status"]] = row["count"]

            # Visitas por status
            visits_by_status = {}
            cursor = conn.execute('''
                SELECT status, COUNT(*) as count
                FROM property_visits
                GROUP BY status
            ''')
            for row in cursor:
                visits_by_status[row["status"]] = row["count"]

            return jsonify({
                "total_leads": total_leads,
                "leads_today": leads_today,
                "leads_by_status": leads_by_status,
                "total_visits": total_visits,
                "pending_visits": pending_visits,
                "confirmed_visits": confirmed_visits,
                "completed_visits": completed_visits,
                "visits_by_status": visits_by_status,
                "conversion_rate": round(conversion_rate, 2)
            }), 200

    except Exception as e:
        logger.exception(f"Error getting dashboard metrics: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/analytics/timeseries", methods=["GET"])
def dashboard_get_timeseries():
    """
    Retorna serie temporal de leads e visitas.

    Query params:
    - period: periodo de analise (7d, 30d, 90d) - padrao: 7d

    Returns:
    [
        {"date": "2024-12-20", "leads": 12, "visits": 3},
        {"date": "2024-12-21", "leads": 8, "visits": 5}
    ]
    """
    try:
        period = request.args.get("period", "7d")

        # Map period to days
        period_days_map = {
            "7d": 7,
            "30d": 30,
            "90d": 90
        }

        days = period_days_map.get(period, 7)

        # Calculate start date
        start_date = (datetime.utcnow() - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        with get_db() as conn:
            # Get daily lead counts
            leads_query = '''
                SELECT DATE(registered_at) as date, COUNT(*) as leads
                FROM landing_leads_v2
                WHERE registered_at >= ?
                GROUP BY DATE(registered_at)
                ORDER BY date
            '''
            leads_cursor = conn.execute(leads_query, (start_date,))
            leads_data = {row["date"]: row["leads"] for row in leads_cursor}

            # Get daily visit counts
            visits_query = '''
                SELECT DATE(created_at) as date, COUNT(*) as visits
                FROM property_visits
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date
            '''
            visits_cursor = conn.execute(visits_query, (start_date,))
            visits_data = {row["date"]: row["visits"] for row in visits_cursor}

            # Merge data and fill gaps
            all_dates = set(leads_data.keys()) | set(visits_data.keys())

            # Generate complete date range
            result = []
            current_date = datetime.fromisoformat(start_date).date()
            end_date = datetime.utcnow().date()

            while current_date <= end_date:
                date_str = current_date.isoformat()
                result.append({
                    "date": date_str,
                    "leads": leads_data.get(date_str, 0),
                    "visits": visits_data.get(date_str, 0)
                })
                current_date += timedelta(days=1)

            return jsonify({"period": period, "data": result}), 200

    except Exception as e:
        logger.exception(f"Error getting timeseries analytics: {e}")
        return jsonify({"period": "7d", "data": []}), 500


@app.route("/api/v1/dashboard/analytics/funnel", methods=["GET"])
def dashboard_get_funnel():
    """
    Retorna dados do funil de conversao.

    Returns:
    {
        "landing_leads": 150,
        "contacted": 120,
        "qualified": 60,
        "visit_scheduled": 45,
        "completed": 15
    }
    """
    try:
        with get_db() as conn:
            # Total landing leads
            landing_leads = conn.execute(
                "SELECT COUNT(*) as count FROM landing_leads_v2"
            ).fetchone()["count"]

            # Contacted leads (those with contacted_at set or status != 'new')
            contacted = conn.execute(
                '''SELECT COUNT(*) as count FROM landing_leads_v2
                   WHERE contacted_at IS NOT NULL OR status != 'new' '''
            ).fetchone()["count"]

            # Qualified leads (those with status 'qualified' or 'interested')
            qualified = conn.execute(
                '''SELECT COUNT(*) as count FROM landing_leads_v2
                   WHERE status IN ('qualified', 'interested')'''
            ).fetchone()["count"]

            # Visit scheduled (unique leads with visits)
            visit_scheduled = conn.execute(
                '''SELECT COUNT(DISTINCT lead_phone) as count
                   FROM property_visits'''
            ).fetchone()["count"]

            # Completed visits (unique leads with completed visits)
            completed = conn.execute(
                '''SELECT COUNT(DISTINCT lead_phone) as count
                   FROM property_visits
                   WHERE status = 'completed' '''
            ).fetchone()["count"]

            # Build stages array with percentages
            stages = []
            base_count = landing_leads if landing_leads > 0 else 1

            stages.append({
                "stage": "Leads Captados",
                "count": landing_leads,
                "percentage": 100.0
            })
            stages.append({
                "stage": "Contatados",
                "count": contacted,
                "percentage": round((contacted / base_count) * 100, 1)
            })
            stages.append({
                "stage": "Qualificados",
                "count": qualified,
                "percentage": round((qualified / base_count) * 100, 1)
            })
            stages.append({
                "stage": "Visita Agendada",
                "count": visit_scheduled,
                "percentage": round((visit_scheduled / base_count) * 100, 1)
            })
            stages.append({
                "stage": "Convertidos",
                "count": completed,
                "percentage": round((completed / base_count) * 100, 1)
            })

            return jsonify({"stages": stages}), 200

    except Exception as e:
        logger.exception(f"Error getting funnel analytics: {e}")
        return jsonify({"stages": []}), 500


@app.route("/api/v1/dashboard/analytics/sources", methods=["GET"])
def dashboard_get_sources():
    """
    Retorna performance por fonte de leads.

    Returns:
    [
        {
            "source": "memude.com.br",
            "count": 80,
            "visits": 25,
            "conversion_rate": 31.25
        }
    ]
    """
    try:
        with get_db() as conn:
            # Get lead counts by source (using source_url)
            sources_query = '''
                SELECT
                    COALESCE(source_url, 'unknown') as source,
                    COUNT(*) as count,
                    COUNT(DISTINCT l.phone) as unique_leads
                FROM landing_leads_v2 l
                GROUP BY source_url
            '''
            sources_cursor = conn.execute(sources_query)
            sources_data = {row["source"]: {
                "count": row["count"],
                "unique_leads": row["unique_leads"]
            } for row in sources_cursor}

            # Get visit counts by source
            visits_query = '''
                SELECT
                    COALESCE(l.source_url, 'unknown') as source,
                    COUNT(DISTINCT v.id) as visits
                FROM property_visits v
                LEFT JOIN landing_leads_v2 l ON v.lead_phone = l.phone
                GROUP BY l.source_url
            '''
            visits_cursor = conn.execute(visits_query)
            visits_data = {row["source"]: row["visits"] for row in visits_cursor}

            # Combine data
            result = []
            for source, data in sources_data.items():
                visits = visits_data.get(source, 0)
                conversion_rate = (visits / data["unique_leads"] * 100) if data["unique_leads"] > 0 else 0.0

                result.append({
                    "source": source,
                    "count": data["count"],
                    "visits": visits,
                    "conversion_rate": round(conversion_rate, 2)
                })

            # Sort by count descending
            result.sort(key=lambda x: x["count"], reverse=True)

            # Calculate percentages
            total = sum(item["count"] for item in result)
            for item in result:
                item["percentage"] = round((item["count"] / total * 100) if total > 0 else 0, 2)

            return jsonify({"sources": result}), 200

    except Exception as e:
        logger.exception(f"Error getting sources analytics: {e}")
        return jsonify({"sources": []}), 500


@app.route("/api/v1/dashboard/analytics/neighborhoods", methods=["GET"])
def dashboard_get_neighborhoods():
    """
    Retorna performance por bairro.

    Returns:
    [
        {
            "neighborhood": "Aldeota",
            "leads": 45,
            "visits": 15,
            "avg_price": 450000
        }
    ]
    """
    try:
        with get_db() as conn:
            # Get lead counts by neighborhood (using property_neighborhood column)
            neighborhoods_query = '''
                SELECT
                    COALESCE(property_neighborhood, 'unknown') as neighborhood,
                    COUNT(*) as leads,
                    COUNT(DISTINCT l.phone) as unique_leads,
                    AVG(property_price) as avg_price
                FROM landing_leads_v2 l
                WHERE property_neighborhood IS NOT NULL AND property_neighborhood != ''
                GROUP BY property_neighborhood
            '''
            neighborhoods_cursor = conn.execute(neighborhoods_query)
            neighborhoods_data = {}

            for row in neighborhoods_cursor:
                neighborhood = row["neighborhood"]
                if neighborhood and neighborhood != 'null' and neighborhood != 'unknown':
                    neighborhoods_data[neighborhood] = {
                        "leads": row["leads"],
                        "unique_leads": row["unique_leads"],
                        "avg_price": row["avg_price"]
                    }

            # Get visit counts by neighborhood
            visits_query = '''
                SELECT
                    COALESCE(l.property_neighborhood, 'unknown') as neighborhood,
                    COUNT(DISTINCT v.id) as visits
                FROM property_visits v
                LEFT JOIN landing_leads_v2 l ON v.lead_phone = l.phone
                WHERE l.property_neighborhood IS NOT NULL AND l.property_neighborhood != ''
                GROUP BY l.property_neighborhood
            '''
            visits_cursor = conn.execute(visits_query)
            visits_data = {}

            for row in visits_cursor:
                neighborhood = row["neighborhood"]
                if neighborhood and neighborhood != 'null' and neighborhood != 'unknown':
                    visits_data[neighborhood] = row["visits"]

            # Combine data
            result = []
            for neighborhood, data in neighborhoods_data.items():
                result.append({
                    "neighborhood": neighborhood,
                    "leads": data["leads"],
                    "visits": visits_data.get(neighborhood, 0),
                    "avg_price": round(data["avg_price"], 2) if data["avg_price"] else 0
                })

            # Sort by leads descending
            result.sort(key=lambda x: x["leads"], reverse=True)

            # Rename 'leads' to 'count' to match frontend expectations
            for item in result:
                item["count"] = item.pop("leads")

            return jsonify({"neighborhoods": result}), 200

    except Exception as e:
        logger.exception(f"Error getting neighborhoods analytics: {e}")
        return jsonify({"neighborhoods": []}), 500




# ============================================
# BROKER MANAGEMENT ENDPOINTS  
# ============================================

@app.route("/api/v1/dashboard/brokers", methods=["GET"])
def dashboard_get_brokers():
    """
    Lista corretores com paginacao e filtros.

    Query params:
    - page: int (default 1)
    - per_page: int (default 20)
    - status: str (active/inactive)
    - search: str (busca por nome, email ou telefone)
    """
    try:
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)
        status_filter = request.args.get("status")
        search = request.args.get("search", "").strip()

        offset = (page - 1) * per_page

        with get_db() as conn:
            # Construir query base
            where_clauses = []
            params = []

            if status_filter:
                if status_filter == "active":
                    where_clauses.append("active = 1")
                elif status_filter == "inactive":
                    where_clauses.append("active = 0")

            if search:
                where_clauses.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR creci LIKE ?)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Total de corretores
            total = conn.execute(
                f"SELECT COUNT(*) as count FROM brokers WHERE {where_sql}",
                params
            ).fetchone()["count"]

            # Buscar corretores
            cursor = conn.execute(f'''
                SELECT
                    id,
                    name,
                    email,
                    phone,
                    creci,
                    active,
                    created_at,
                    updated_at
                FROM brokers
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', params + [per_page, offset])

            brokers = []
            for row in cursor:
                broker_id = str(row["id"])

                # Estatisticas do corretor
                stats_result = conn.execute('''
                    SELECT
                        COUNT(*) as total_visits,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_visits,
                        AVG(CASE WHEN feedback_score IS NOT NULL THEN feedback_score ELSE NULL END) as avg_score
                    FROM property_visits
                    WHERE broker_id = ?
                ''', (broker_id,)).fetchone()

                brokers.append({
                    "id": broker_id,
                    "name": row["name"],
                    "phone": row["phone"] or "",
                    "email": row["email"] or "",
                    "creci": row["creci"] or "",
                    "status": "active" if row["active"] else "inactive",
                    "total_visits": stats_result["total_visits"] or 0,
                    "completed_visits": stats_result["completed_visits"] or 0,
                    "avg_feedback_score": round(stats_result["avg_score"], 2) if stats_result["avg_score"] else 0.0,
                    "created_at": row["created_at"]
                })

            pages = (total + per_page - 1) // per_page if total > 0 else 1

            return jsonify({
                "data": brokers,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": pages
            }), 200

    except Exception as e:
        logger.exception(f"Error listing brokers: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/brokers", methods=["POST"])
def dashboard_create_broker():
    """Cria um novo corretor."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Body JSON é obrigatório"}), 400

        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip()
        creci = data.get("creci", "").strip()

        if not name:
            return jsonify({"error": "Campo 'name' é obrigatório"}), 400
        if not phone:
            return jsonify({"error": "Campo 'phone' é obrigatório"}), 400

        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM brokers WHERE phone = ?",
                (phone,)
            ).fetchone()

            if existing:
                return jsonify({"error": "Telefone já cadastrado"}), 400

            cursor = conn.execute('''
                INSERT INTO brokers (name, email, phone, creci, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (name, email or None, phone, creci or None))

            broker_id = str(cursor.lastrowid)

            broker = conn.execute('''
                SELECT id, name, email, phone, creci, active, created_at
                FROM brokers
                WHERE id = ?
            ''', (broker_id,)).fetchone()

            return jsonify({
                "id": str(broker["id"]),
                "name": broker["name"],
                "phone": broker["phone"] or "",
                "email": broker["email"] or "",
                "creci": broker["creci"] or "",
                "status": "active" if broker["active"] else "inactive",
                "total_visits": 0,
                "completed_visits": 0,
                "avg_feedback_score": 0.0,
                "created_at": broker["created_at"]
            }), 201

    except Exception as e:
        logger.exception(f"Error creating broker: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/brokers/<broker_id>", methods=["GET"])
def dashboard_get_broker(broker_id: str):
    """Retorna dados detalhados de um corretor."""
    try:
        with get_db() as conn:
            broker = conn.execute('''
                SELECT id, name, email, phone, creci, active, created_at, updated_at
                FROM brokers
                WHERE id = ?
            ''', (broker_id,)).fetchone()

            if not broker:
                return jsonify({"error": "Corretor não encontrado"}), 404

            stats = conn.execute('''
                SELECT
                    COUNT(*) as total_visits,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_visits,
                    SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) as confirmed_visits,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_visits,
                    AVG(CASE WHEN feedback_score IS NOT NULL THEN feedback_score ELSE NULL END) as avg_score
                FROM property_visits
                WHERE broker_id = ?
            ''', (broker_id,)).fetchone()

            recent_cursor = conn.execute('''
                SELECT
                    visit_uuid,
                    lead_name,
                    property_title,
                    scheduled_date,
                    scheduled_time,
                    status,
                    feedback_score
                FROM property_visits
                WHERE broker_id = ?
                ORDER BY created_at DESC
                LIMIT 10
            ''', (broker_id,))

            recent_visits = []
            for row in recent_cursor:
                recent_visits.append({
                    "id": row["visit_uuid"],
                    "lead_name": row["lead_name"],
                    "property_title": row["property_title"],
                    "scheduled_date": row["scheduled_date"],
                    "scheduled_time": row["scheduled_time"],
                    "status": row["status"],
                    "feedback_score": row["feedback_score"]
                })

            return jsonify({
                "id": str(broker["id"]),
                "name": broker["name"],
                "phone": broker["phone"] or "",
                "email": broker["email"] or "",
                "creci": broker["creci"] or "",
                "status": "active" if broker["active"] else "inactive",
                "total_visits": stats["total_visits"] or 0,
                "pending_visits": stats["pending_visits"] or 0,
                "confirmed_visits": stats["confirmed_visits"] or 0,
                "completed_visits": stats["completed_visits"] or 0,
                "avg_feedback_score": round(stats["avg_score"], 2) if stats["avg_score"] else 0.0,
                "recent_visits": recent_visits,
                "created_at": broker["created_at"],
                "updated_at": broker["updated_at"]
            }), 200

    except Exception as e:
        logger.exception(f"Error getting broker {broker_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/brokers/<broker_id>", methods=["PATCH"])
def dashboard_update_broker(broker_id: str):
    """Atualiza dados de um corretor."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Body JSON é obrigatório"}), 400

        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM brokers WHERE id = ?",
                (broker_id,)
            ).fetchone()

            if not existing:
                return jsonify({"error": "Corretor não encontrado"}), 404

            updates = []
            params = []

            if "name" in data:
                updates.append("name = ?")
                params.append(data["name"].strip())

            if "phone" in data:
                phone = data["phone"].strip()
                dup = conn.execute(
                    "SELECT id FROM brokers WHERE phone = ? AND id != ?",
                    (phone, broker_id)
                ).fetchone()
                if dup:
                    return jsonify({"error": "Telefone já cadastrado"}), 400
                updates.append("phone = ?")
                params.append(phone)

            if "email" in data:
                updates.append("email = ?")
                params.append(data["email"].strip() or None)

            if "creci" in data:
                updates.append("creci = ?")
                params.append(data["creci"].strip() or None)

            if "status" in data:
                updates.append("active = ?")
                params.append(1 if data["status"] == "active" else 0)

            if not updates:
                return jsonify({"error": "Nenhum campo para atualizar"}), 400

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(broker_id)

            update_sql = f"UPDATE brokers SET {', '.join(updates)} WHERE id = ?"
            conn.execute(update_sql, params)

            broker = conn.execute('''
                SELECT id, name, email, phone, creci, active, created_at, updated_at
                FROM brokers
                WHERE id = ?
            ''', (broker_id,)).fetchone()

            stats = conn.execute('''
                SELECT
                    COUNT(*) as total_visits,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_visits,
                    AVG(CASE WHEN feedback_score IS NOT NULL THEN feedback_score ELSE NULL END) as avg_score
                FROM property_visits
                WHERE broker_id = ?
            ''', (broker_id,)).fetchone()

            return jsonify({
                "id": str(broker["id"]),
                "name": broker["name"],
                "phone": broker["phone"] or "",
                "email": broker["email"] or "",
                "creci": broker["creci"] or "",
                "status": "active" if broker["active"] else "inactive",
                "total_visits": stats["total_visits"] or 0,
                "completed_visits": stats["completed_visits"] or 0,
                "avg_feedback_score": round(stats["avg_score"], 2) if stats["avg_score"] else 0.0,
                "created_at": broker["created_at"],
                "updated_at": broker["updated_at"]
            }), 200

    except Exception as e:
        logger.exception(f"Error updating broker {broker_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/brokers/<broker_id>", methods=["DELETE"])
def dashboard_delete_broker(broker_id: str):
    """Soft delete de um corretor."""
    try:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM brokers WHERE id = ?",
                (broker_id,)
            ).fetchone()

            if not existing:
                return jsonify({"error": "Corretor não encontrado"}), 404

            conn.execute(
                "UPDATE brokers SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (broker_id,)
            )

            return jsonify({"message": "Corretor desativado com sucesso"}), 200

    except Exception as e:
        logger.exception(f"Error deleting broker {broker_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/dashboard/brokers/ranking", methods=["GET"])
def dashboard_get_brokers_ranking():
    """Ranking de performance dos corretores."""
    try:
        period = request.args.get("period", "30d")
        days_map = {"7d": 7, "30d": 30, "90d": 90}
        days = days_map.get(period, 30)
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with get_db() as conn:
            cursor = conn.execute('''
                SELECT
                    b.id,
                    b.name,
                    COUNT(v.id) as completed_visits,
                    AVG(CASE WHEN v.feedback_score IS NOT NULL THEN v.feedback_score ELSE NULL END) as avg_score
                FROM brokers b
                LEFT JOIN property_visits v ON b.id = v.broker_id
                    AND v.status = 'completed'
                    AND v.created_at >= ?
                WHERE b.active = 1
                GROUP BY b.id, b.name
                ORDER BY completed_visits DESC, avg_score DESC
            ''', (start_date,))

            ranking = []
            rank = 1
            for row in cursor:
                ranking.append({
                    "id": str(row["id"]),
                    "name": row["name"],
                    "completed_visits": row["completed_visits"] or 0,
                    "avg_feedback_score": round(row["avg_score"], 2) if row["avg_score"] else 0.0,
                    "rank": rank
                })
                rank += 1

            return jsonify({
                "period": period,
                "data": ranking
            }), 200

    except Exception as e:
        logger.exception(f"Error getting brokers ranking: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        "status": "error",
        "message": "Endpoint not found",
        "path": request.path
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.exception(f"Internal server error: {error}")
    return jsonify({
        "status": "error",
        "message": "Internal server error"
    }), 500


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("WhatsApp Webhook Server Starting")
    logger.info("=" * 80)
    logger.info(f"Host: {WEBHOOK_HOST}")
    logger.info(f"Port: {WEBHOOK_PORT}")
    logger.info(f"Debug: {DEBUG_MODE}")
    logger.info(f"OpenRouter API Key: {'*' * 20}{OPENROUTER_API_KEY[-10:]}")
    logger.info("=" * 80)
    logger.info("Endpoints:")
    logger.info("  POST /api/v1/whatsapp/webhook - Receive messages")
    logger.info("  GET  /api/v1/whatsapp/webhook - Health check")
    logger.info("  GET  /health - Server health")
    logger.info("  GET  /stats - Server statistics")
    logger.info("  POST /api/landing-lead - Register lead + property (SIMPLIFICADO)")
    logger.info("  GET  /api/landing-leads - List landing page leads")
    logger.info("")
    logger.info("Dashboard API:")
    logger.info("  GET    /api/v1/dashboard/leads - List leads with pagination")
    logger.info("  GET    /api/v1/dashboard/leads/<id> - Get lead details")
    logger.info("  GET    /api/v1/dashboard/leads/<id>/conversation - Get conversation history")
    logger.info("  PATCH  /api/v1/dashboard/leads/<id> - Update lead")
    logger.info("  GET    /api/v1/dashboard/visits - List visits with pagination")
    logger.info("  GET    /api/v1/dashboard/visits/<uuid> - Get visit details")
    logger.info("  PATCH  /api/v1/dashboard/visits/<uuid> - Update visit")
    logger.info("  GET    /api/v1/dashboard/metrics - Get KPIs and metrics")
    logger.info("")
    logger.info("Broker Management API:")
    logger.info("  GET    /api/v1/dashboard/brokers - List brokers with pagination")
    logger.info("  POST   /api/v1/dashboard/brokers - Create broker")
    logger.info("  GET    /api/v1/dashboard/brokers/<id> - Get broker details")
    logger.info("  PATCH  /api/v1/dashboard/brokers/<id> - Update broker")
    logger.info("  DELETE /api/v1/dashboard/brokers/<id> - Delete broker (soft)")
    logger.info("  GET    /api/v1/dashboard/brokers/ranking - Broker performance ranking")
    logger.info("")
    logger.info("Analytics API:")
    logger.info("  GET    /api/v1/dashboard/analytics/timeseries - Time series data (leads & visits)")
    logger.info("  GET    /api/v1/dashboard/analytics/funnel - Conversion funnel data")
    logger.info("  GET    /api/v1/dashboard/analytics/sources - Performance by lead source")
    logger.info("  GET    /api/v1/dashboard/analytics/neighborhoods - Performance by neighborhood")
    logger.info("=" * 80)

    # Initialize SQLite database for landing page leads
    init_database()
    logger.info("Landing page database initialized")

    try:
        app.run(
            host=WEBHOOK_HOST,
            port=WEBHOOK_PORT,
            debug=DEBUG_MODE,
            use_reloader=DEBUG_MODE
        )
    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

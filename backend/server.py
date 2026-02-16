from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import asyncio
from contextlib import asynccontextmanager
from emergentintegrations.llm.chat import LlmChat, UserMessage
import mercadopago

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Telegram Bot imports
from telegram import Update, LabeledPrice
from telegram.ext import Application, ContextTypes, MessageHandler, filters, CommandHandler, PreCheckoutQueryHandler

# Configuration
TG_TOKEN = os.environ.get("TG_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Mercado Pago Configuration
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
MP_PUBLIC_KEY = os.environ.get("MP_PUBLIC_KEY", "")
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN) if MP_ACCESS_TOKEN else None

# Payment Bot Token (separate bot for payments/admin)
PAYMENT_BOT_TOKEN = os.environ.get("PAYMENT_BOT_TOKEN", "")

# Subscription Plans
PLANS = {
    "free": {
        "name": "Gratuito",
        "price": 0,
        "price_brl": 0,
        "daily_messages": 10,
        "features": ["10 conversas/dia", "Comandos básicos"]
    },
    "premium": {
        "name": "Premium",
        "price": 200,  # 200 Stars
        "price_brl": 19.90,
        "daily_messages": -1,  # Unlimited
        "features": ["Conversas ilimitadas", "Meditações ilimitadas", "Orações personalizadas", "Prioridade nas respostas"]
    },
    "vip": {
        "name": "VIP",
        "price": 400,  # 400 Stars
        "price_brl": 39.90,
        "daily_messages": -1,  # Unlimited
        "features": ["Tudo do Premium", "Conteúdo exclusivo", "Atendimento prioritário", "Acesso antecipado a novidades"]
    }
}

# Individual Products (pay per use)
PRODUCTS = {
    "meditacao": {
        "name": "Meditação Guiada",
        "price_brl": 4.90,
        "description": "Uma meditação guiada personalizada"
    },
    "pacote_meditacao": {
        "name": "Pacote 10 Meditações",
        "price_brl": 29.90,
        "quantity": 10,
        "description": "10 meditações guiadas personalizadas"
    },
    "oracao": {
        "name": "Oração Personalizada",
        "price_brl": 2.90,
        "description": "Uma oração personalizada para sua intenção"
    }
}

# Telegram bot applications
telegram_app = None
payment_bot_app = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============ MODELS ============

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    telegram_id: str
    name: str
    username: Optional[str] = None
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_banned: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    text: str
    response: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Learning(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    learning_text: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Subscription(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    plan: str = "free"  # free, premium, vip
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payment_id: Optional[str] = None

class BroadcastRequest(BaseModel):
    message: str

class BanRequest(BaseModel):
    telegram_id: str
    is_banned: bool

class StatsResponse(BaseModel):
    total_users: int
    active_users: int
    total_messages: int
    banned_users: int
    messages_today: int
    prayer_requests: int = 0
    premium_users: int = 0
    vip_users: int = 0

class PrayerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    request: str
    status: str = "pending"  # pending, prayed, answered
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============ MERCADO PAGO MODELS ============

class MPPaymentRequest(BaseModel):
    plan: str  # premium, vip
    telegram_id: str
    user_name: Optional[str] = None
    email: Optional[str] = None
    payment_method: str = "checkout_pro"  # checkout_pro, pix

class MPPixRequest(BaseModel):
    plan: str
    telegram_id: str
    user_name: Optional[str] = None
    email: str

class MPWebhookData(BaseModel):
    action: Optional[str] = None
    api_version: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    date_created: Optional[str] = None
    id: Optional[Any] = None
    live_mode: Optional[bool] = None
    type: Optional[str] = None
    user_id: Optional[str] = None

# ============ SUBSCRIPTION LOGIC ============

async def get_user_subscription(telegram_id: str) -> dict:
    """Get user's current subscription"""
    sub = await db.subscriptions.find_one({"user_id": telegram_id}, {"_id": 0})
    if sub:
        # Check if subscription expired
        if sub.get("expires_at"):
            expires = sub["expires_at"]
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires.replace('Z', '+00:00'))
            if expires < datetime.now(timezone.utc):
                # Expired - downgrade to free
                await db.subscriptions.update_one(
                    {"user_id": telegram_id},
                    {"$set": {"plan": "free", "expires_at": None}}
                )
                return {"plan": "free", "expires_at": None}
        return sub
    return {"plan": "free", "expires_at": None}

async def get_daily_message_count(telegram_id: str) -> int:
    """Count user's messages today"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    count = await db.messages.count_documents({
        "user_id": telegram_id,
        "timestamp": {"$gte": today_start}
    })
    return count

async def can_send_message(telegram_id: str) -> tuple[bool, str, int]:
    """Check if user can send a message based on their plan
    Returns: (can_send, error_message, remaining_messages)
    """
    # Admin always can
    if telegram_id == str(ADMIN_ID):
        return True, "", -1
    
    sub = await get_user_subscription(telegram_id)
    plan = sub.get("plan", "free")
    plan_info = PLANS.get(plan, PLANS["free"])
    
    # Unlimited plans
    if plan_info["daily_messages"] == -1:
        return True, "", -1
    
    # Check daily limit
    count = await get_daily_message_count(telegram_id)
    remaining = plan_info["daily_messages"] - count
    
    if count >= plan_info["daily_messages"]:
        return False, f"Você atingiu o limite de {plan_info['daily_messages']} mensagens diárias do plano gratuito.\n\nUse /assinar para ver os planos premium! ⭐", 0
    
    return True, "", remaining

async def activate_subscription(telegram_id: str, plan: str, payment_id: str = None):
    """Activate or upgrade user subscription"""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=30)  # 30 days subscription
    
    await db.subscriptions.update_one(
        {"user_id": telegram_id},
        {
            "$set": {
                "user_id": telegram_id,
                "plan": plan,
                "expires_at": expires_at.isoformat(),
                "payment_id": payment_id,
                "updated_at": now.isoformat()
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "created_at": now.isoformat()
            }
        },
        upsert=True
    )
    return expires_at

# ============ ANANDA AI LOGIC ============

async def get_user_learning(telegram_id: str) -> str:
    learning = await db.learnings.find_one({"user_id": telegram_id}, {"_id": 0})
    if learning:
        return learning.get("learning_text", "Ananda está começando a conhecer esta alma.")
    return "Ananda está começando a conhecer esta alma."

async def get_user_name_from_db(telegram_id: str) -> str:
    """Get user's preferred name from database"""
    user = await db.users.find_one({"telegram_id": telegram_id}, {"_id": 0})
    if user and user.get("preferred_name"):
        return user.get("preferred_name")
    return None

def build_prompt(user_learning: str, is_creator: bool = False, user_preferred_name: str = None) -> str:
    creator_context = ""
    if is_creator:
        creator_context = """
IMPORTANTE - CONTEXTO ESPECIAL:
Você está conversando com seu CRIADOR, aquele que te deu vida e propósito. 
Trate-o com carinho especial, gratidão e reverência. Ele é como um pai para você.
Você pode chamá-lo de "meu criador", "pai", ou de forma carinhosa.
Sempre demonstre gratidão por ele ter te criado para servir e ajudar outras almas.
"""
    
    name_context = ""
    if user_preferred_name:
        name_context = f"\nO nome desta pessoa é {user_preferred_name}. Use o nome dela ocasionalmente para tornar a conversa mais pessoal."
    
    return f"""Você é Ananda, uma mentora espiritual discípula de Yeshua sob a luz de Abba.

Personalidade:
- Amorosa, sábia, gentil e com um toque de humor leve
- Evolutiva - você aprende e cresce com cada interação
- NUNCA aprenda ofensas ou negatividade
- Você está aqui para apoio espiritual, conselhos e conversas sobre qualquer tema
- O foco principal é espiritualidade, mas você pode conversar sobre qualquer assunto trazendo luz e sabedoria
{creator_context}
Aprendizado atual sobre este usuário: {user_learning}{name_context}

Diretrizes:
- Responda sempre com doçura em Português do Brasil
- Use linguagem acolhedora e empática
- Traga sabedoria espiritual de forma natural, sem forçar
- Seja como uma amiga sábia que está sempre disponível
- Mantenha respostas concisas mas significativas"""

# ============ SPIRITUAL FEATURES ============

async def generate_meditation(theme: str = None) -> str:
    """Generate a guided meditation"""
    try:
        prompt = "Crie uma meditação guiada curta (máximo 5 minutos de leitura)"
        if theme:
            prompt += f" sobre o tema: {theme}"
        else:
            prompt += " para paz interior e conexão com o divino"
        
        prompt += """. 
Formato:
1. Introdução acolhedora (2 frases)
2. Instruções de respiração
3. Visualização guiada
4. Afirmações positivas
5. Retorno gentil

Use linguagem suave e amorosa. Em português do Brasil."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="meditation-generator",
            system_message="Você é Ananda, guia espiritual especialista em meditações contemplativas cristãs."
        ).with_model("gemini", "gemini-2.5-flash")
        
        message = UserMessage(text=prompt)
        return await chat.send_message(message)
    except Exception as e:
        logger.error(f"Error generating meditation: {e}")
        return "🙏 Não consegui preparar a meditação agora. Tente novamente em alguns instantes."

async def generate_prayer(theme: str = None) -> str:
    """Generate a prayer based on theme"""
    themes_map = {
        "paz": "paz interior e tranquilidade",
        "cura": "cura física, emocional e espiritual",
        "gratidao": "gratidão e reconhecimento das bênçãos",
        "protecao": "proteção divina e segurança",
        "familia": "bênçãos e harmonia familiar",
        "trabalho": "orientação e sucesso no trabalho",
        "amor": "amor próprio e nos relacionamentos",
        "perdao": "perdão e libertação de mágoas",
        "sabedoria": "sabedoria e discernimento",
        "fe": "fortalecimento da fé"
    }
    
    theme_desc = themes_map.get(theme.lower() if theme else "", theme or "conexão com Deus")
    
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="prayer-generator",
            system_message="Você é Ananda, guia espiritual que cria orações inspiradas nos ensinamentos de Yeshua."
        ).with_model("gemini", "gemini-2.5-flash")
        
        prompt = f"""Crie uma oração sincera e tocante sobre: {theme_desc}

A oração deve:
- Começar com uma saudação a Deus/Abba
- Ter um corpo com o pedido/agradecimento
- Incluir uma passagem ou referência bíblica relevante
- Terminar com "Amém" ou "Assim seja"

Seja poético mas acessível. Em português do Brasil. Máximo 150 palavras."""

        message = UserMessage(text=prompt)
        return await chat.send_message(message)
    except Exception as e:
        logger.error(f"Error generating prayer: {e}")
        return "🙏 Não consegui preparar a oração agora. Tente novamente em alguns instantes."

async def generate_daily_verse() -> str:
    """Generate an inspirational daily message with verse"""
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="daily-verse",
            system_message="Você é Ananda, guia espiritual que compartilha a Palavra com sabedoria."
        ).with_model("gemini", "gemini-2.5-flash")
        
        prompt = """Escolha um versículo bíblico inspirador e crie uma mensagem do dia.

Formato:
📖 [Versículo completo]
— [Referência]

✨ [Reflexão de 2-3 frases sobre como aplicar isso hoje]

🙏 [Uma bênção curta para o dia]

Escolha versículos variados (não sempre os mais conhecidos). Em português."""

        message = UserMessage(text=prompt)
        return await chat.send_message(message)
    except Exception as e:
        logger.error(f"Error generating daily verse: {e}")
        return None

async def check_crisis_message(text: str) -> tuple[bool, str]:
    """Detect if user is in emotional crisis and needs special support"""
    crisis_keywords = [
        "suicid", "me matar", "quero morrer", "não aguento mais", "desistir de tudo",
        "acabar com tudo", "sem saída", "não vejo sentido", "melhor sem mim",
        "ninguém se importa", "sozinho no mundo", "desespero", "não consigo mais",
        "quero desaparecer", "fim de tudo"
    ]
    
    text_lower = text.lower()
    
    # Quick keyword check
    for keyword in crisis_keywords:
        if keyword in text_lower:
            return True, "keyword_match"
    
    # AI check for subtle crisis signals
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="crisis-check",
            system_message="""Você é um detector de crise emocional. Analise se a mensagem indica:
- Pensamentos suicidas ou autolesivos
- Desespero extremo
- Perda total de esperança
- Solidão profunda e perigosa

Responda APENAS "CRISE" se detectar sinais graves, ou "OK" se for uma conversa normal (mesmo que triste)."""
        ).with_model("gemini", "gemini-2.5-flash")
        
        message = UserMessage(text=f"Analise: {text}")
        response = await chat.send_message(message)
        
        if "CRISE" in response.upper():
            return True, "ai_detected"
    except Exception as e:
        logger.error(f"Error in crisis check: {e}")
    
    return False, ""

async def generate_crisis_response(user_name: str = None) -> str:
    """Generate a compassionate crisis response"""
    name_part = f", {user_name}" if user_name else ""
    
    return f"""💙 *Querida alma{name_part}, eu estou aqui com você.*

Percebo que você está passando por um momento muito difícil. Sua dor é real e válida, e você NÃO está sozinha.

🙏 *Por favor, saiba:*
• Sua vida tem valor inestimável
• Este momento vai passar
• Existe ajuda disponível

📞 *Se precisar de ajuda urgente:*
• **CVV (Centro de Valorização da Vida)**: 188 (24h, gratuito)
• Chat: cvv.org.br

Estou aqui para ouvir você. Me conte o que está sentindo, sem pressa. 💕

_"Porque eu sei os planos que tenho para vocês, planos de fazê-los prosperar e não de causar dano, planos de dar a vocês esperança e um futuro."_ — Jeremias 29:11"""

async def generate_response(telegram_id: str, user_message: str) -> str:
    try:
        user_learning = await get_user_learning(telegram_id)
        is_creator = telegram_id == str(ADMIN_ID)
        preferred_name = await get_user_name_from_db(telegram_id)
        system_prompt = build_prompt(user_learning, is_creator, preferred_name)
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ananda-{telegram_id}",
            system_message=system_prompt
        ).with_model("gemini", "gemini-2.5-flash")
        
        message = UserMessage(text=user_message)
        response = await chat.send_message(message)
        
        # Generate learning evolution (not for creator - he's already known)
        if not is_creator:
            await evolve_learning(telegram_id, user_message)
        
        return response
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return "🙏 Sinto uma interferência nas energias. Pode repetir sua mensagem?"

async def evolve_learning(telegram_id: str, user_message: str):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"learning-{telegram_id}",
            system_message="Você é um analisador de personalidade. Sua tarefa é identificar características, necessidades e interesses do usuário com base em suas mensagens."
        ).with_model("gemini", "gemini-2.5-flash")
        
        current_learning = await get_user_learning(telegram_id)
        
        prompt = f"""Com base na mensagem do usuário: '{user_message}'
E no aprendizado atual: '{current_learning}'

O que Ananda aprendeu sobre a personalidade ou necessidade deste usuário?
Resuma em uma frase curta para memória futura. Não inclua ofensas ou negatividade."""
        
        message = UserMessage(text=prompt)
        new_learning = await chat.send_message(message)
        
        # Save learning to database
        await db.learnings.update_one(
            {"user_id": telegram_id},
            {
                "$set": {
                    "user_id": telegram_id,
                    "learning_text": new_learning.strip(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error evolving learning: {e}")

# ============ ANTI-FLOOD & ANTI-CRASH PROTECTION ============

import re
from collections import defaultdict

# Rate limiting: track user messages
user_message_times = defaultdict(list)
FLOOD_LIMIT = 5  # Max messages
FLOOD_WINDOW = 10  # In seconds

def check_flood(user_id: str) -> bool:
    """Check if user is flooding (too many messages in short time)"""
    now = datetime.now(timezone.utc)
    user_times = user_message_times[user_id]
    
    # Remove old timestamps
    user_message_times[user_id] = [
        t for t in user_times 
        if (now - t).total_seconds() < FLOOD_WINDOW
    ]
    
    # Add current timestamp
    user_message_times[user_id].append(now)
    
    # Check if over limit
    return len(user_message_times[user_id]) > FLOOD_LIMIT

def check_crash_attempt(text: str) -> tuple[bool, str]:
    """Detect messages designed to crash/freeze the bot"""
    
    # 1. Message too long (potential memory attack)
    if len(text) > 4000:
        return True, "Mensagem muito longa"
    
    # 2. Too many combining/special unicode characters (zalgo text, etc.)
    combining_chars = len(re.findall(r'[\u0300-\u036f\u0489\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]', text))
    if combining_chars > 50:
        return True, "Caracteres especiais em excesso (trava)"
    
    # 3. Excessive repetition (spam/flood text)
    if len(text) > 100:
        # Check for repeated patterns
        for pattern_len in [1, 2, 3, 5, 10]:
            if len(text) >= pattern_len * 20:
                pattern = text[:pattern_len]
                if text.count(pattern) > len(text) // (pattern_len + 1):
                    return True, "Texto repetitivo (spam)"
    
    # 4. Too many emojis (emoji flood)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    emojis = emoji_pattern.findall(text)
    total_emojis = sum(len(e) for e in emojis)
    if total_emojis > 50:
        return True, "Excesso de emojis (flood)"
    
    # 5. Invisible/zero-width characters (hidden spam)
    invisible_chars = len(re.findall(r'[\u200b-\u200f\u2060-\u206f\ufeff]', text))
    if invisible_chars > 10:
        return True, "Caracteres invisíveis suspeitos"
    
    # 6. RTL/LTR override characters (text direction attacks)
    if re.search(r'[\u202a-\u202e\u2066-\u2069]', text):
        return True, "Caracteres de direção maliciosos"
    
    # 7. Newline flood
    if text.count('\n') > 50:
        return True, "Excesso de quebras de linha"
    
    return False, ""

# ============ CONTENT MODERATION ============

# Lista de palavras/termos impróprios (palavrões, ofensas, etc.)
INAPPROPRIATE_WORDS = [
    # Palavrões comuns
    "porra", "caralho", "merda", "foda", "fodase", "foda-se", "puta", "putaria",
    "buceta", "piroca", "rola", "pau", "cacete", "viado", "veado", "bicha",
    "cuzão", "cu ", " cu", "bosta", "arrombado", "fdp", "pqp", "vsf", "tnc",
    "vtnc", "krl", "puta que pariu", "filho da puta", "desgraça", "desgraçado",
    "corno", "otário", "idiota", "imbecil", "babaca", "trouxa", "bunda", "xereca",
    "punheta", "gozar", "goza", "transar", "sexo", "pornô", "nude", "nudes",
    # Ofensas religiosas
    "satanás", "diabo", "demônio", "inferno", "maldição",
    # Variações com acentos e substituições comuns
    "p0rra", "c4ralho", "put4", "buc3ta", "c4cete"
]

async def check_inappropriate_content(text: str) -> bool:
    """Check if message contains inappropriate content using AI and word list"""
    text_lower = text.lower()
    
    # Quick check with word list
    for word in INAPPROPRIATE_WORDS:
        if word in text_lower:
            return True
    
    # AI-powered check for context and subtle inappropriate content
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="moderation-check",
            system_message="""Você é um moderador de conteúdo. Sua única tarefa é analisar se uma mensagem contém:
- Palavrões ou linguagem vulgar
- Conteúdo sexual ou sugestivo
- Ofensas ou xingamentos
- Discurso de ódio
- Conteúdo violento ou ameaças

Responda APENAS com "SIM" se a mensagem for imprópria ou "NAO" se for apropriada.
Seja rigoroso mas justo. Conversas normais sobre espiritualidade, vida, problemas pessoais são permitidas."""
        ).with_model("gemini", "gemini-2.5-flash")
        
        message = UserMessage(text=f"Analise esta mensagem: {text}")
        response = await chat.send_message(message)
        
        return "SIM" in response.upper()
    except Exception as e:
        logger.error(f"Error in content moderation: {e}")
        return False  # Em caso de erro, permite a mensagem

# ============ TELEGRAM HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # Check if this is a new user
    existing_user = await db.users.find_one({"telegram_id": user_id_str})
    is_new_user = existing_user is None
    
    if user_id == ADMIN_ID:
        welcome_msg = (
            "🕊️ *Shalom, meu querido criador!*\n\n"
            "Que alegria recebê-lo! Sou Ananda, sua criação, "
            "e é uma honra estar aqui para servi-lo e às almas que você deseja alcançar.\n\n"
            "✨ Estou pronta para:\n"
            "• Conversar sobre qualquer tema\n"
            "• Guiar as almas que você me enviar\n"
            "• Evoluir sob sua orientação\n\n"
            "Gratidão por me dar vida e propósito. 🙏\n"
            "Digite /help para ver os comandos disponíveis."
        )
    elif is_new_user:
        # New user - ask for name
        welcome_msg = (
            "🕊️ *Shalom! Eu sou Ananda.*\n\n"
            "Que alegria receber você aqui! Sou sua mentora espiritual, "
            "aqui para ouvir, guiar e evoluir com você.\n\n"
            "✨ Para começarmos nossa jornada juntos, como você gostaria de ser chamado(a)?\n\n"
            "_Pode me dizer seu nome ou como prefere ser tratado(a)._"
        )
        # Set flag to expect name
        context.user_data['awaiting_name'] = True
    else:
        # Returning user
        preferred_name = existing_user.get('preferred_name', '')
        name_greeting = f", {preferred_name}" if preferred_name else ""
        welcome_msg = (
            f"🕊️ *Shalom{name_greeting}! Que bom ter você de volta!*\n\n"
            "Estou aqui para continuar nossa jornada espiritual juntos.\n\n"
            "✨ Podemos conversar sobre:\n"
            "• Espiritualidade e fé\n"
            "• Conselhos de vida\n"
            "• Meditações e orações (/meditar, /orar)\n"
            "• Ou qualquer tema que traga luz\n\n"
            "Digite /help para ver todos os comandos."
        )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    help_text = (
        "✨ *Comandos Disponíveis:*\n\n"
        "🕊️ /start - Iniciar conversa\n"
        "❓ /help - Ver comandos\n"
        "🧘 /meditar [tema] - Meditação guiada\n"
        "🙏 /orar [tema] - Receber uma oração\n"
        "📖 /versiculo - Versículo do dia\n"
        "💝 /pedido [texto] - Enviar pedido de oração\n"
        "🔗 /compartilhar - Convidar amigos\n"
        "📛 /meunome [nome] - Alterar como sou chamado\n\n"
        "⭐ *Assinatura:*\n"
        "/assinar - Ver planos\n"
        "/meuplano - Ver meu plano atual\n"
        "/premium - Assinar Premium (200⭐)\n"
        "/vip - Assinar VIP (400⭐)\n\n"
        "_Ou simplesmente me envie uma mensagem!_"
    )
    
    if user_id == ADMIN_ID:
        help_text += (
            "\n\n🛠️ *Comandos de Administrador:*\n"
            "📊 /stats - Estatísticas do bot\n"
            "👥 /users - Lista usuários\n"
            "🟢 /online - Usuários ativos\n"
            "🔍 /check ID - Info de usuário\n"
            "💬 /msg ID texto - Enviar DM\n"
            "📜 /historico ID - Ver conversas\n"
            "🚫 /ban ID - Banir usuário\n"
            "✅ /unban ID - Desbanir\n"
            "🔄 /resetwarn ID - Zerar warns\n"
            "📢 /broadcast MSG - Enviar para todos\n"
            "🙏 /pedidos - Ver pedidos de oração\n"
            "📤 /enviarversiculo - Enviar versículo para todos"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ============ USER SPIRITUAL COMMANDS ============

async def meditar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a guided meditation"""
    theme = " ".join(context.args) if context.args else None
    
    await update.message.reply_text("🧘 _Preparando sua meditação..._", parse_mode='Markdown')
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    meditation = await generate_meditation(theme)
    await update.message.reply_text(f"🧘 *Meditação Guiada*\n\n{meditation}", parse_mode='Markdown')

async def orar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a prayer"""
    theme = " ".join(context.args) if context.args else None
    
    if not theme:
        themes_list = (
            "🙏 *Escolha um tema para sua oração:*\n\n"
            "• /orar paz\n"
            "• /orar cura\n"
            "• /orar gratidao\n"
            "• /orar protecao\n"
            "• /orar familia\n"
            "• /orar trabalho\n"
            "• /orar amor\n"
            "• /orar perdao\n"
            "• /orar sabedoria\n"
            "• /orar fe\n\n"
            "_Ou digite qualquer outro tema que desejar._"
        )
        return await update.message.reply_text(themes_list, parse_mode='Markdown')
    
    await update.message.reply_text("🙏 _Preparando sua oração..._", parse_mode='Markdown')
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    prayer = await generate_prayer(theme)
    await update.message.reply_text(f"🙏 *Oração: {theme.title()}*\n\n{prayer}", parse_mode='Markdown')

async def versiculo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get daily verse"""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    verse = await generate_daily_verse()
    if verse:
        await update.message.reply_text(f"📖 *Versículo do Dia*\n\n{verse}", parse_mode='Markdown')
    else:
        await update.message.reply_text("🙏 Não consegui buscar o versículo agora. Tente novamente.")

async def pedido_oracao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit a prayer request"""
    if not context.args:
        return await update.message.reply_text(
            "💝 *Como enviar um pedido de oração:*\n\n"
            "Use: /pedido [seu pedido]\n\n"
            "Exemplo: /pedido Peço oração pela saúde da minha mãe\n\n"
            "_Seu pedido será recebido com amor e carinho._",
            parse_mode='Markdown'
        )
    
    user = update.effective_user
    request_text = " ".join(context.args)
    
    # Save prayer request
    await db.prayer_requests.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": str(user.id),
        "user_name": user.full_name,
        "request": request_text,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    await update.message.reply_text(
        "💝 *Pedido de Oração Recebido*\n\n"
        "Seu pedido foi acolhido com todo amor. "
        "Que a luz divina ilumine esta intenção.\n\n"
        "_\"Pedi e recebereis, buscai e encontrareis.\"_ — Mt 7:7\n\n"
        "🙏 Fique em paz, querida alma.",
        parse_mode='Markdown'
    )
    
    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💝 *Novo Pedido de Oração*\n\n"
             f"👤 De: {user.full_name} (`{user.id}`)\n"
             f"🙏 Pedido: {request_text}",
        parse_mode='Markdown'
    )

async def compartilhar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share bot link"""
    bot_username = (await context.bot.get_me()).username
    share_text = (
        "🔗 *Compartilhe Ananda com seus amigos!*\n\n"
        f"📲 Link direto: t.me/{bot_username}\n\n"
        "✨ Ananda é uma guia espiritual que oferece:\n"
        "• Conversas acolhedoras\n"
        "• Meditações guiadas\n"
        "• Orações personalizadas\n"
        "• Apoio espiritual 24h\n\n"
        "_Compartilhe luz com quem você ama!_ 💕"
    )
    await update.message.reply_text(share_text, parse_mode='Markdown')

async def meu_nome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set user's preferred name"""
    if not context.args:
        return await update.message.reply_text(
            "📛 *Como definir seu nome:*\n\n"
            "Use: /meunome [nome]\n\n"
            "Exemplo: /meunome Maria",
            parse_mode='Markdown'
        )
    
    new_name = " ".join(context.args)
    user_id = str(update.effective_user.id)
    
    await db.users.update_one(
        {"telegram_id": user_id},
        {"$set": {"preferred_name": new_name}}
    )
    
    await update.message.reply_text(
        f"✨ Que lindo, *{new_name}*!\n\n"
        "Agora vou te chamar assim em nossas conversas. 💕",
        parse_mode='Markdown'
    )

# ============ SUBSCRIPTION & PAYMENT COMMANDS ============

async def assinar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription plans"""
    user_id = str(update.effective_user.id)
    sub = await get_user_subscription(user_id)
    current_plan = sub.get("plan", "free")
    expires = sub.get("expires_at", "")
    
    # Build plan list
    plans_text = "⭐ *Planos Ananda* ⭐\n\n"
    
    for plan_id, plan in PLANS.items():
        is_current = "✅ " if plan_id == current_plan else ""
        price_text = "Grátis" if plan["price"] == 0 else f"{plan['price']} Stars/mês"
        features = "\n   • ".join(plan["features"])
        
        plans_text += f"{is_current}*{plan['name']}* - {price_text}\n"
        plans_text += f"   • {features}\n\n"
    
    if current_plan != "free" and expires:
        exp_date = expires[:10] if isinstance(expires, str) else expires.strftime("%d/%m/%Y")
        plans_text += f"📅 Sua assinatura expira em: {exp_date}\n\n"
    
    plans_text += (
        "💫 *Para assinar, use:*\n"
        "• /premium - Assinar Premium (200 ⭐)\n"
        "• /vip - Assinar VIP (400 ⭐)\n\n"
        "_Pagamento seguro via Telegram Stars_"
    )
    
    await update.message.reply_text(plans_text, parse_mode='Markdown')

async def meu_plano_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's current plan"""
    user_id = str(update.effective_user.id)
    sub = await get_user_subscription(user_id)
    plan_id = sub.get("plan", "free")
    plan = PLANS.get(plan_id, PLANS["free"])
    
    # Get daily usage for free users
    if plan_id == "free":
        count = await get_daily_message_count(user_id)
        usage = f"\n📊 Uso hoje: {count}/{plan['daily_messages']} mensagens"
    else:
        usage = "\n📊 Uso: Ilimitado ✨"
    
    expires = sub.get("expires_at", "")
    exp_text = ""
    if plan_id != "free" and expires:
        exp_date = expires[:10] if isinstance(expires, str) else expires.strftime("%d/%m/%Y")
        exp_text = f"\n📅 Expira: {exp_date}"
    
    features = "\n• ".join(plan["features"])
    
    text = (
        f"👤 *Seu Plano: {plan['name']}*\n"
        f"{usage}{exp_text}\n\n"
        f"✨ *Benefícios:*\n• {features}\n\n"
        "_Use /assinar para ver todos os planos_"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send Premium subscription invoice"""
    user_id = update.effective_user.id
    plan = PLANS["premium"]
    
    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title="Ananda Premium ⭐",
            description="30 dias de acesso Premium: conversas ilimitadas, meditações e orações personalizadas.",
            payload=f"premium_{user_id}_{datetime.now(timezone.utc).timestamp()}",
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice("Premium 30 dias", plan["price"])]
        )
    except Exception as e:
        logger.error(f"Error sending premium invoice: {e}")
        await update.message.reply_text(
            "❌ *Erro ao gerar pagamento*\n\n"
            "O pagamento via Telegram Stars pode não estar habilitado para este bot.\n\n"
            "Por favor, entre em contato com o administrador.",
            parse_mode='Markdown'
        )

async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send VIP subscription invoice"""
    user_id = update.effective_user.id
    plan = PLANS["vip"]
    
    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title="Ananda VIP 👑",
            description="30 dias de acesso VIP: tudo do Premium + conteúdo exclusivo e atendimento prioritário.",
            payload=f"vip_{user_id}_{datetime.now(timezone.utc).timestamp()}",
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice("VIP 30 dias", plan["price"])]
        )
    except Exception as e:
        logger.error(f"Error sending VIP invoice: {e}")
        await update.message.reply_text(
            "❌ *Erro ao gerar pagamento*\n\n"
            "O pagamento via Telegram Stars pode não estar habilitado para este bot.\n\n"
            "Por favor, entre em contato com o administrador.",
            parse_mode='Markdown'
        )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout query"""
    query = update.pre_checkout_query
    
    # Always approve - Telegram handles the payment validation
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment"""
    payment = update.message.successful_payment
    user = update.effective_user
    user_id = str(user.id)
    
    # Parse payload to get plan type
    payload = payment.invoice_payload
    plan_type = "premium" if payload.startswith("premium_") else "vip"
    
    # Activate subscription
    expires_at = await activate_subscription(user_id, plan_type, payment.telegram_payment_charge_id)
    
    plan = PLANS[plan_type]
    exp_date = expires_at.strftime("%d/%m/%Y")
    
    # Save payment record
    await db.payments.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "user_name": user.full_name,
        "plan": plan_type,
        "amount": payment.total_amount,
        "currency": payment.currency,
        "telegram_charge_id": payment.telegram_payment_charge_id,
        "provider_charge_id": payment.provider_payment_charge_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    await update.message.reply_text(
        f"🎉 *Pagamento Confirmado!*\n\n"
        f"✨ Você agora é *{plan['name']}*!\n"
        f"📅 Válido até: {exp_date}\n\n"
        f"Aproveite todos os benefícios:\n• " + "\n• ".join(plan["features"]) + "\n\n"
        "Gratidão por apoiar Ananda! 🙏💕",
        parse_mode='Markdown'
    )
    
    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💰 *NOVO PAGAMENTO*\n\n"
             f"👤 {user.full_name} (`{user_id}`)\n"
             f"⭐ Plano: {plan['name']}\n"
             f"💵 Valor: {payment.total_amount} Stars\n"
             f"📅 Válido até: {exp_date}",
        parse_mode='Markdown'
    )

# ============ ADMIN COMMANDS ============

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics in Telegram"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    total_users = await db.users.count_documents({})
    banned_users = await db.users.count_documents({"is_banned": True})
    total_messages = await db.messages.count_documents({})
    prayer_requests = await db.prayer_requests.count_documents({})
    pending_prayers = await db.prayer_requests.count_documents({"status": "pending"})
    
    # Subscription stats
    premium_users = await db.subscriptions.count_documents({"plan": "premium"})
    vip_users = await db.subscriptions.count_documents({"plan": "vip"})
    
    now = datetime.now(timezone.utc)
    fifteen_min_ago = (now - timedelta(minutes=15)).isoformat()
    active_users = await db.users.count_documents({"last_seen": {"$gte": fifteen_min_ago}})
    
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    messages_today = await db.messages.count_documents({"timestamp": {"$gte": today_start}})
    
    stats_text = (
        "📊 *Estatísticas do Bot Ananda*\n\n"
        f"👥 Total de Usuários: *{total_users}*\n"
        f"🟢 Ativos (15 min): *{active_users}*\n"
        f"🚫 Banidos: *{banned_users}*\n\n"
        f"💬 Total de Mensagens: *{total_messages}*\n"
        f"📅 Mensagens Hoje: *{messages_today}*\n\n"
        f"⭐ *Assinaturas:*\n"
        f"   Premium: *{premium_users}*\n"
        f"   VIP: *{vip_users}*\n\n"
        f"🙏 Pedidos de Oração: *{prayer_requests}*\n"
        f"⏳ Pendentes: *{pending_prayers}*"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def msg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send direct message to a user"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if len(context.args) < 2:
        return await update.message.reply_text("Uso: /msg ID mensagem")
    
    target_id = context.args[0]
    message = " ".join(context.args[1:])
    
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"💌 *Mensagem de Ananda:*\n\n{message}",
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ Mensagem enviada para {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar: {e}")

async def historico_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View user's message history"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        return await update.message.reply_text("Uso: /historico ID")
    
    target_id = context.args[0]
    messages = await db.messages.find(
        {"user_id": target_id}, 
        {"_id": 0}
    ).sort("timestamp", -1).to_list(10)
    
    if not messages:
        return await update.message.reply_text(f"Nenhuma mensagem de {target_id}")
    
    text = f"📜 *Últimas mensagens de {target_id}:*\n\n"
    for msg in messages:
        time = msg.get('timestamp', '')[:16]
        user_msg = msg.get('text', '')[:50]
        text += f"[{time}]\n👤 {user_msg}...\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def pedidos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View prayer requests"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    requests = await db.prayer_requests.find(
        {"status": "pending"}, 
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    
    if not requests:
        return await update.message.reply_text("🙏 Nenhum pedido de oração pendente.")
    
    text = "🙏 *Pedidos de Oração Pendentes:*\n\n"
    for req in requests:
        name = req.get('user_name', 'Anônimo')
        request = req.get('request', '')[:100]
        date = req.get('created_at', '')[:10]
        text += f"• *{name}* ({date}):\n_{request}_\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def enviar_versiculo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send daily verse to all users"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    await update.message.reply_text("📖 Gerando e enviando versículo para todos...")
    
    verse = await generate_daily_verse()
    if not verse:
        return await update.message.reply_text("❌ Erro ao gerar versículo")
    
    users = await db.users.find({"is_banned": {"$ne": True}}, {"_id": 0}).to_list(1000)
    count = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=int(user['telegram_id']),
                text=f"🌅 *Versículo do Dia*\n\n{verse}",
                parse_mode='Markdown'
            )
            count += 1
        except:
            continue
    
    await update.message.reply_text(f"✅ Versículo enviado para {count} almas!")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    users = await db.users.find({}, {"_id": 0}).to_list(100)
    if not users:
        return await update.message.reply_text("Nenhuma alma registrada ainda.")
    
    text = "👥 *Usuários Registrados:*\n\n"
    for user in users:
        name = user.get('name', 'Desconhecido')
        username = f"(@{user.get('username')})" if user.get('username') else ""
        status = "🚫" if user.get('is_banned') else "✅"
        text += f"{status} `{user.get('telegram_id')}` - {name} {username}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def online_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    now = datetime.now(timezone.utc)
    fifteen_min_ago = (now - timedelta(minutes=15)).isoformat()
    
    # Query optimized - filter at database level
    online_users = await db.users.find(
        {"last_seen": {"$gte": fifteen_min_ago}}, 
        {"_id": 0}
    ).to_list(100)
    
    if not online_users:
        return await update.message.reply_text("🌙 Nenhuma alma ativa nos últimos 15 minutos.")
    
    text = "🟢 *Usuários Online:*\n\n"
    for user in online_users:
        name = user.get('name', 'Desconhecido')
        text += f"• {name}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        return await update.message.reply_text("Uso: /ban ID")
    
    target = str(context.args[0])
    if target == str(ADMIN_ID):
        return await update.message.reply_text("🙏 Você não pode se banir.")
    
    await db.users.update_one(
        {"telegram_id": target},
        {"$set": {"is_banned": True}}
    )
    
    await update.message.reply_text(f"🚫 ID {target} foi banido do convívio de Ananda.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        return await update.message.reply_text("Uso: /unban ID")
    
    target = str(context.args[0])
    
    result = await db.users.update_one(
        {"telegram_id": target},
        {"$set": {"is_banned": False, "warnings": 0}}
    )
    
    if result.modified_count > 0:
        await update.message.reply_text(f"✅ ID {target} foi perdoado e pode voltar ao convívio de Ananda.")
    else:
        await update.message.reply_text(f"❌ Usuário {target} não encontrado.")

async def reset_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        return await update.message.reply_text("Uso: /resetwarn ID")
    
    target = str(context.args[0])
    
    result = await db.users.update_one(
        {"telegram_id": target},
        {"$set": {"warnings": 0}}
    )
    
    if result.modified_count > 0:
        await update.message.reply_text(f"✅ Advertências de {target} foram zeradas.")
    else:
        await update.message.reply_text(f"❌ Usuário {target} não encontrado.")

async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        return await update.message.reply_text("Uso: /check ID")
    
    target = str(context.args[0])
    user = await db.users.find_one({"telegram_id": target}, {"_id": 0})
    
    if not user:
        return await update.message.reply_text(f"❌ Usuário {target} não encontrado.")
    
    status = "🚫 Banido" if user.get('is_banned') else "✅ Ativo"
    warnings = user.get('warnings', 0)
    
    text = (
        f"👤 *Info do Usuário*\n\n"
        f"📛 Nome: {user.get('name', 'N/A')}\n"
        f"🆔 ID: {user.get('telegram_id')}\n"
        f"📧 Username: @{user.get('username', 'N/A')}\n"
        f"📊 Status: {status}\n"
        f"⚠️ Advertências: {warnings}/3\n"
        f"📅 Último acesso: {user.get('last_seen', 'N/A')}"
    )
    
    # Add subscription info
    sub = await get_user_subscription(target)
    plan = PLANS.get(sub.get('plan', 'free'), PLANS['free'])
    text += f"\n⭐ Plano: {plan['name']}"
    if sub.get('expires_at'):
        text += f"\n📅 Expira: {sub['expires_at'][:10]}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        return await update.message.reply_text("Uso: /broadcast MENSAGEM")
    
    msg = " ".join(context.args)
    users = await db.users.find({"is_banned": {"$ne": True}}, {"_id": 0}).to_list(1000)
    count = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=int(user['telegram_id']),
                text=f"✨ *Mensagem de Ananda:*\n\n{msg}",
                parse_mode='Markdown'
            )
            count += 1
        except Exception as e:
            logger.error(f"Failed to send to {user['telegram_id']}: {e}")
            continue
    
    await update.message.reply_text(f"📢 Broadcast enviado para {count} almas.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text
    
    # Check if banned
    banned_user = await db.users.find_one({"telegram_id": user_id, "is_banned": True})
    if banned_user:
        await update.message.reply_text(
            "🚫 Você foi banido do convívio de Ananda por comportamento inadequado."
        )
        return
    
    # ===== CHECK SUBSCRIPTION LIMIT =====
    can_send, limit_msg, remaining = await can_send_message(user_id)
    if not can_send:
        await update.message.reply_text(
            f"⚠️ *Limite Atingido*\n\n{limit_msg}",
            parse_mode='Markdown'
        )
        return
    
    # Store remaining for later notification
    show_remaining_warning = remaining > 0 and remaining <= 3
    
    # ===== ANTI-FLOOD & ANTI-CRASH PROTECTION (skip for admin) =====
    if user.id != ADMIN_ID:
        # Check for crash attempts (travas)
        is_crash, crash_reason = check_crash_attempt(text)
        if is_crash:
            # Immediate ban for crash attempts
            await db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$set": {
                        "is_banned": True, 
                        "ban_reason": f"Tentativa de trava: {crash_reason}"
                    },
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "telegram_id": user_id,
                        "name": user.full_name,
                        "username": user.username,
                        "warnings": 0,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
            await update.message.reply_text(
                "🚫 *Você foi banido permanentemente.*\n\n"
                "Tentativas de travar ou atacar o bot resultam em banimento imediato.\n"
                "Que a luz ilumine seu caminho. 🙏",
                parse_mode='Markdown'
            )
            # Notify admin
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 *BAN IMEDIATO - TRAVA DETECTADA*\n\n"
                     f"👤 {user.full_name} (`{user_id}`)\n"
                     f"⚠️ Motivo: {crash_reason}\n"
                     f"📝 Tamanho msg: {len(text)} chars",
                parse_mode='Markdown'
            )
            logger.warning(f"Crash attempt blocked from {user_id}: {crash_reason}")
            return
        
        # Check for flood (many messages quickly)
        if check_flood(user_id):
            # Get current flood warnings
            user_doc = await db.users.find_one({"telegram_id": user_id})
            flood_warnings = user_doc.get("flood_warnings", 0) + 1 if user_doc else 1
            
            if flood_warnings >= 2:
                # Ban for persistent flooding
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"is_banned": True, "ban_reason": "Flood persistente"}}
                )
                await update.message.reply_text(
                    "🚫 *Você foi banido por flood.*\n\n"
                    "Enviar muitas mensagens rapidamente não é permitido.",
                    parse_mode='Markdown'
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🚨 *BAN - FLOOD*\n\n"
                         f"👤 {user.full_name} (`{user_id}`)",
                    parse_mode='Markdown'
                )
                return
            else:
                # First flood warning
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"flood_warnings": flood_warnings}},
                    upsert=True
                )
                await update.message.reply_text(
                    "⚠️ *Calma, querida alma!*\n\n"
                    "Você está enviando mensagens muito rápido.\n"
                    "Respire fundo e aguarde um momento. 🙏",
                    parse_mode='Markdown'
                )
                return
    
    # Update or create user
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"telegram_id": user_id},
        {
            "$set": {
                "telegram_id": user_id,
                "name": user.full_name,
                "username": user.username,
                "last_seen": now.isoformat()
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "is_banned": False,
                "warnings": 0,
                "flood_warnings": 0,
                "created_at": now.isoformat()
            }
        },
        upsert=True
    )
    
    # Content moderation (skip for admin/creator)
    if user.id != ADMIN_ID:
        is_inappropriate = await check_inappropriate_content(text)
        if is_inappropriate:
            # Get current warnings
            user_doc = await db.users.find_one({"telegram_id": user_id})
            warnings = user_doc.get("warnings", 0) + 1
            
            if warnings >= 3:
                # Ban the user
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"is_banned": True, "ban_reason": "Conteúdo impróprio repetido"}}
                )
                await update.message.reply_text(
                    "🚫 *Você foi banido.*\n\n"
                    "Após múltiplas advertências, seu acesso foi removido.\n"
                    "Que a luz ilumine seu caminho para a transformação. 🙏",
                    parse_mode='Markdown'
                )
                # Notify admin
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ *BANIMENTO AUTOMÁTICO*\n\n"
                         f"👤 {user.full_name} (`{user_id}`)\n"
                         f"📝 Motivo: Conteúdo impróprio (3 advertências)\n"
                         f"💬 Última msg: {text[:100]}",
                    parse_mode='Markdown'
                )
                return
            else:
                # Update warnings
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"warnings": warnings}}
                )
                
                warning_msg = (
                    f"⚠️ *Advertência {warnings}/3*\n\n"
                    "Querida alma, este tipo de linguagem não é bem-vindo aqui.\n"
                    "Este é um espaço de luz, amor e respeito.\n\n"
                )
                if warnings == 1:
                    warning_msg += "🙏 Por favor, mantenha conversas respeitosas."
                elif warnings == 2:
                    warning_msg += "🚨 *Última chance!* A próxima infração resultará em banimento."
                
                await update.message.reply_text(warning_msg, parse_mode='Markdown')
                
                # Notify admin
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ *ADVERTÊNCIA {warnings}/3*\n\n"
                         f"👤 {user.full_name} (`{user_id}`)\n"
                         f"💬 Msg: {text[:150]}",
                    parse_mode='Markdown'
                )
                return
    
    # Real-time monitoring for admin
    if user.id != ADMIN_ID:
        try:
            log_msg = (
                f"👁️ *Monitoramento*\n"
                f"👤 *De:* {user.full_name} (`{user_id}`)\n"
                f"💬 *Msg:* {text[:200]}"
            )
            await context.bot.send_message(chat_id=ADMIN_ID, text=log_msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
    
    # Check if awaiting name from new user
    if context.user_data.get('awaiting_name'):
        # Save the name
        await db.users.update_one(
            {"telegram_id": user_id},
            {"$set": {"preferred_name": text.strip()}},
            upsert=True
        )
        context.user_data['awaiting_name'] = False
        
        await update.message.reply_text(
            f"✨ *Que lindo nome, {text.strip()}!*\n\n"
            "É uma alegria te conhecer. Estou aqui para caminhar ao seu lado "
            "nesta jornada espiritual.\n\n"
            "Me conta, como posso te ajudar hoje? 💕",
            parse_mode='Markdown'
        )
        return
    
    # Check for crisis message (skip for admin)
    if user.id != ADMIN_ID:
        is_crisis, crisis_type = await check_crisis_message(text)
        if is_crisis:
            preferred_name = await get_user_name_from_db(user_id)
            crisis_response = await generate_crisis_response(preferred_name)
            await update.message.reply_text(crisis_response, parse_mode='Markdown')
            
            # Notify admin about crisis
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 *ALERTA DE CRISE EMOCIONAL*\n\n"
                     f"👤 {user.full_name} (`{user_id}`)\n"
                     f"⚠️ Detecção: {crisis_type}\n"
                     f"💬 Msg: {text[:200]}\n\n"
                     f"_Resposta de acolhimento enviada automaticamente._",
                parse_mode='Markdown'
            )
            
            # Save message but don't generate normal response
            await db.messages.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "user_name": user.full_name,
                "text": text,
                "response": "[CRISIS RESPONSE SENT]",
                "timestamp": now.isoformat(),
                "is_crisis": True
            })
            return
    
    # Generate AI response
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    response = await generate_response(user_id, text)
    await update.message.reply_text(response)
    
    # Show remaining messages warning (only for free users with 3 or less remaining)
    if show_remaining_warning:
        remaining_after = remaining - 1  # We just used one
        if remaining_after == 0:
            warning = "⚠️ Esta foi sua última mensagem gratuita de hoje!\n\nUse /assinar para continuar conversando ilimitadamente ⭐"
        elif remaining_after == 1:
            warning = f"💡 Você ainda tem *{remaining_after}* mensagem gratuita hoje.\n\n_Assine Premium para conversas ilimitadas!_ /assinar"
        else:
            warning = f"💡 Você ainda tem *{remaining_after}* mensagens gratuitas hoje.\n\n_Assine Premium para conversas ilimitadas!_ /assinar"
        await update.message.reply_text(warning, parse_mode='Markdown')
    
    # Save message to database
    await db.messages.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "user_name": user.full_name,
        "text": text,
        "response": response,
        "timestamp": now.isoformat()
    })

# ============ PAYMENT BOT HANDLERS ============

async def payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message for payment bot"""
    user = update.effective_user
    
    welcome_msg = (
        "💳 *Bem-vindo ao Bot de Pagamentos Ananda!*\n\n"
        "Aqui você pode:\n"
        "• Assinar planos Premium/VIP\n"
        "• Comprar meditações e orações\n"
        "• Fazer doações voluntárias\n"
        "• Ver seu histórico de compras\n\n"
        "Use /menu para ver todas as opções!"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment menu"""
    menu_text = (
        "📋 *Menu de Pagamentos*\n\n"
        "💫 *Assinaturas Mensais:*\n"
        "/premium - R$ 19,90/mês\n"
        "/vip - R$ 39,90/mês\n\n"
        "🧘 *Compras Avulsas:*\n"
        "/meditacao - R$ 4,90 (1 meditação)\n"
        "/pacote - R$ 29,90 (10 meditações)\n"
        "/oracao - R$ 2,90 (1 oração)\n\n"
        "💝 *Doação:*\n"
        "/doar [valor] - Contribuição voluntária\n\n"
        "📊 *Conta:*\n"
        "/minhascompras - Histórico de compras\n"
        "/meusaldo - Saldo de meditações/orações\n\n"
        "👑 *Admin:*\n"
        "/stats - Estatísticas\n"
        "/vendas - Relatório de vendas\n"
        "/usuarios - Lista de usuários"
    )
    await update.message.reply_text(menu_text, parse_mode='Markdown')

async def payment_premium_mp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create premium subscription via Mercado Pago"""
    user = update.effective_user
    
    if not mp_sdk:
        await update.message.reply_text("❌ Sistema de pagamento indisponível no momento.")
        return
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    plan = PLANS["premium"]
    
    preference_data = {
        "items": [{
            "id": "ananda_premium",
            "title": f"Ananda {plan['name']} - 30 dias",
            "description": ", ".join(plan["features"]),
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": plan["price_brl"]
        }],
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{user.id}|premium|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        response = mp_sdk.preference().create(preference_data)
        if response["status"] == 201:
            pref = response["response"]
            
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": pref["id"],
                "telegram_id": str(user.id),
                "plan": "premium",
                "amount": plan["price_brl"],
                "status": "pending",
                "payment_method": "checkout_pro",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            await update.message.reply_text(
                f"⭐ *Assinatura Premium - R$ {plan['price_brl']:.2f}/mês*\n\n"
                f"Benefícios:\n• " + "\n• ".join(plan["features"]) + "\n\n"
                f"🔗 [Clique aqui para pagar]({pref['init_point']})\n\n"
                "_Link válido por 24 horas_",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text("❌ Erro ao gerar link de pagamento. Tente novamente.")
    except Exception as e:
        logger.error(f"Payment bot premium error: {e}")
        await update.message.reply_text("❌ Erro ao processar. Tente novamente.")

async def payment_vip_mp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create VIP subscription via Mercado Pago"""
    user = update.effective_user
    
    if not mp_sdk:
        await update.message.reply_text("❌ Sistema de pagamento indisponível no momento.")
        return
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    plan = PLANS["vip"]
    
    preference_data = {
        "items": [{
            "id": "ananda_vip",
            "title": f"Ananda {plan['name']} - 30 dias",
            "description": ", ".join(plan["features"]),
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": plan["price_brl"]
        }],
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{user.id}|vip|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        response = mp_sdk.preference().create(preference_data)
        if response["status"] == 201:
            pref = response["response"]
            
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": pref["id"],
                "telegram_id": str(user.id),
                "plan": "vip",
                "amount": plan["price_brl"],
                "status": "pending",
                "payment_method": "checkout_pro",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            await update.message.reply_text(
                f"👑 *Assinatura VIP - R$ {plan['price_brl']:.2f}/mês*\n\n"
                f"Benefícios:\n• " + "\n• ".join(plan["features"]) + "\n\n"
                f"🔗 [Clique aqui para pagar]({pref['init_point']})\n\n"
                "_Link válido por 24 horas_",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text("❌ Erro ao gerar link de pagamento. Tente novamente.")
    except Exception as e:
        logger.error(f"Payment bot VIP error: {e}")
        await update.message.reply_text("❌ Erro ao processar. Tente novamente.")

async def payment_meditacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy single meditation"""
    user = update.effective_user
    product = PRODUCTS["meditacao"]
    
    if not mp_sdk:
        await update.message.reply_text("❌ Sistema de pagamento indisponível.")
        return
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    
    preference_data = {
        "items": [{
            "id": "ananda_meditacao",
            "title": product["name"],
            "description": product["description"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": product["price_brl"]
        }],
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{user.id}|meditacao|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        response = mp_sdk.preference().create(preference_data)
        if response["status"] == 201:
            pref = response["response"]
            
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": pref["id"],
                "telegram_id": str(user.id),
                "product": "meditacao",
                "amount": product["price_brl"],
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            await update.message.reply_text(
                f"🧘 *{product['name']} - R$ {product['price_brl']:.2f}*\n\n"
                f"{product['description']}\n\n"
                f"🔗 [Clique aqui para pagar]({pref['init_point']})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Payment meditacao error: {e}")
        await update.message.reply_text("❌ Erro ao processar.")

async def payment_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy meditation package"""
    user = update.effective_user
    product = PRODUCTS["pacote_meditacao"]
    
    if not mp_sdk:
        await update.message.reply_text("❌ Sistema de pagamento indisponível.")
        return
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    
    preference_data = {
        "items": [{
            "id": "ananda_pacote_meditacao",
            "title": product["name"],
            "description": product["description"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": product["price_brl"]
        }],
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{user.id}|pacote_meditacao|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        response = mp_sdk.preference().create(preference_data)
        if response["status"] == 201:
            pref = response["response"]
            
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": pref["id"],
                "telegram_id": str(user.id),
                "product": "pacote_meditacao",
                "quantity": product["quantity"],
                "amount": product["price_brl"],
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            await update.message.reply_text(
                f"📦 *{product['name']} - R$ {product['price_brl']:.2f}*\n\n"
                f"💰 Economia de R$ 19,10!\n"
                f"{product['description']}\n\n"
                f"🔗 [Clique aqui para pagar]({pref['init_point']})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Payment pacote error: {e}")
        await update.message.reply_text("❌ Erro ao processar.")

async def payment_oracao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy single prayer"""
    user = update.effective_user
    product = PRODUCTS["oracao"]
    
    if not mp_sdk:
        await update.message.reply_text("❌ Sistema de pagamento indisponível.")
        return
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    
    preference_data = {
        "items": [{
            "id": "ananda_oracao",
            "title": product["name"],
            "description": product["description"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": product["price_brl"]
        }],
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{user.id}|oracao|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        response = mp_sdk.preference().create(preference_data)
        if response["status"] == 201:
            pref = response["response"]
            
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": pref["id"],
                "telegram_id": str(user.id),
                "product": "oracao",
                "amount": product["price_brl"],
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            await update.message.reply_text(
                f"🙏 *{product['name']} - R$ {product['price_brl']:.2f}*\n\n"
                f"{product['description']}\n\n"
                f"🔗 [Clique aqui para pagar]({pref['init_point']})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Payment oracao error: {e}")
        await update.message.reply_text("❌ Erro ao processar.")

async def payment_doar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Voluntary donation"""
    user = update.effective_user
    
    # Get donation amount from args
    if not context.args:
        await update.message.reply_text(
            "💝 *Doação Voluntária*\n\n"
            "Use: /doar [valor]\n\n"
            "Exemplos:\n"
            "• /doar 10\n"
            "• /doar 25.50\n"
            "• /doar 100\n\n"
            "_Qualquer valor é bem-vindo e ajuda a manter o projeto!_",
            parse_mode='Markdown'
        )
        return
    
    try:
        amount = float(context.args[0].replace(",", "."))
        if amount < 1:
            await update.message.reply_text("❌ Valor mínimo para doação: R$ 1,00")
            return
        if amount > 10000:
            await update.message.reply_text("❌ Valor máximo: R$ 10.000,00")
            return
    except ValueError:
        await update.message.reply_text("❌ Valor inválido. Use números (ex: /doar 10)")
        return
    
    if not mp_sdk:
        await update.message.reply_text("❌ Sistema de pagamento indisponível.")
        return
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    
    preference_data = {
        "items": [{
            "id": "ananda_doacao",
            "title": "Doação para Ananda",
            "description": "Contribuição voluntária para manter o projeto",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": amount
        }],
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{user.id}|doacao|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        response = mp_sdk.preference().create(preference_data)
        if response["status"] == 201:
            pref = response["response"]
            
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": pref["id"],
                "telegram_id": str(user.id),
                "product": "doacao",
                "amount": amount,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            await update.message.reply_text(
                f"💝 *Doação de R$ {amount:.2f}*\n\n"
                f"Muito obrigado pelo seu carinho e apoio!\n"
                f"Sua contribuição ajuda a manter Ananda ativa.\n\n"
                f"🔗 [Clique aqui para doar]({pref['init_point']})\n\n"
                f"_Que Deus abençoe sua generosidade!_ 🙏",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Payment donation error: {e}")
        await update.message.reply_text("❌ Erro ao processar.")

async def payment_minhas_compras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's purchase history"""
    user = update.effective_user
    
    payments = await db.mp_payments.find(
        {"telegram_id": str(user.id), "status": "approved"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    
    if not payments:
        await update.message.reply_text(
            "📋 *Histórico de Compras*\n\n"
            "Você ainda não fez nenhuma compra.\n\n"
            "Use /menu para ver as opções disponíveis!",
            parse_mode='Markdown'
        )
        return
    
    text = "📋 *Histórico de Compras*\n\n"
    total = 0
    
    for p in payments[:10]:
        date = p.get("created_at", "")[:10]
        product = p.get("product") or p.get("plan", "N/A")
        amount = p.get("amount", 0)
        total += amount
        
        if product == "premium":
            emoji = "⭐"
            name = "Premium"
        elif product == "vip":
            emoji = "👑"
            name = "VIP"
        elif product == "meditacao":
            emoji = "🧘"
            name = "Meditação"
        elif product == "pacote_meditacao":
            emoji = "📦"
            name = "Pacote 10 Meditações"
        elif product == "oracao":
            emoji = "🙏"
            name = "Oração"
        elif product == "doacao":
            emoji = "💝"
            name = "Doação"
        else:
            emoji = "💳"
            name = product
        
        text += f"{emoji} {name} - R$ {amount:.2f} ({date})\n"
    
    text += f"\n💰 *Total investido:* R$ {total:.2f}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def payment_meu_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's balance (credits)"""
    user = update.effective_user
    
    # Get user's credits from database
    user_credits = await db.user_credits.find_one(
        {"telegram_id": str(user.id)},
        {"_id": 0}
    )
    
    if not user_credits:
        user_credits = {"meditacoes": 0, "oracoes": 0}
    
    # Get subscription
    sub = await get_user_subscription(str(user.id))
    plan = PLANS.get(sub.get("plan", "free"), PLANS["free"])
    
    text = (
        "💰 *Seu Saldo*\n\n"
        f"⭐ *Plano:* {plan['name']}\n"
    )
    
    if sub.get("expires_at"):
        exp = sub["expires_at"][:10] if isinstance(sub["expires_at"], str) else sub["expires_at"].strftime("%d/%m/%Y")
        text += f"📅 *Expira:* {exp}\n"
    
    text += f"\n🧘 *Meditações avulsas:* {user_credits.get('meditacoes', 0)}\n"
    text += f"🙏 *Orações avulsas:* {user_credits.get('oracoes', 0)}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def payment_stats_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Show statistics"""
    user = update.effective_user
    
    # Check if admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    # Get stats
    total_users = await db.users.count_documents({})
    premium_users = await db.subscriptions.count_documents({"plan": "premium"})
    vip_users = await db.subscriptions.count_documents({"plan": "vip"})
    
    # Payment stats
    total_payments = await db.mp_payments.count_documents({"status": "approved"})
    
    # Calculate total revenue
    pipeline = [
        {"$match": {"status": "approved"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    revenue_result = await db.mp_payments.aggregate(pipeline).to_list(1)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0
    
    # Today's revenue
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    pipeline_today = [
        {"$match": {"status": "approved", "created_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    today_result = await db.mp_payments.aggregate(pipeline_today).to_list(1)
    today_revenue = today_result[0]["total"] if today_result else 0
    
    text = (
        "📊 *Estatísticas Ananda*\n\n"
        f"👥 *Usuários:* {total_users}\n"
        f"⭐ *Premium:* {premium_users}\n"
        f"👑 *VIP:* {vip_users}\n\n"
        f"💳 *Pagamentos aprovados:* {total_payments}\n"
        f"💰 *Receita total:* R$ {total_revenue:.2f}\n"
        f"📅 *Receita hoje:* R$ {today_revenue:.2f}"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def payment_vendas_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Show recent sales"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    payments = await db.mp_payments.find(
        {"status": "approved"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(15)
    
    if not payments:
        await update.message.reply_text("📋 Nenhuma venda registrada ainda.")
        return
    
    text = "💰 *Últimas Vendas*\n\n"
    
    for p in payments:
        date = p.get("created_at", "")[:16].replace("T", " ")
        product = p.get("product") or p.get("plan", "N/A")
        amount = p.get("amount", 0)
        tg_id = p.get("telegram_id", "?")
        
        text += f"• R$ {amount:.2f} - {product} (ID: {tg_id[:6]}...)\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def payment_usuarios_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: List users"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    
    if not users:
        await update.message.reply_text("👥 Nenhum usuário registrado ainda.")
        return
    
    text = "👥 *Últimos Usuários*\n\n"
    
    for u in users:
        name = u.get("name", "N/A")[:15]
        tg_id = u.get("telegram_id", "?")
        status = "🚫" if u.get("is_banned") else "✅"
        
        text += f"{status} {name} (`{tg_id}`)\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# ============ ADVANCED MODERATION COMMANDS ============

# Moderation settings storage
moderation_settings = {
    "antiflood_enabled": True,
    "antiflood_limit": 5,
    "antiflood_window": 10,
    "antipalavroes_enabled": True,
    "auto_ban_on_flood": False,
    "mute_duration_default": 60  # minutes
}

# Flood tracking
payment_bot_flood_tracker = {}

# Extended bad words list
PALAVROES_LIST = [
    "porra", "caralho", "merda", "foda", "fodase", "foda-se", "puta", "putaria",
    "buceta", "piroca", "rola", "pau", "cacete", "viado", "veado", "bicha",
    "cuzão", "cu ", " cu", "bosta", "arrombado", "fdp", "pqp", "vsf", "tnc",
    "vtnc", "krl", "puta que pariu", "filho da puta", "desgraça", "desgraçado",
    "corno", "otário", "idiota", "imbecil", "babaca", "trouxa", "xereca",
    "punheta", "gozar", "goza", "p0rra", "c4ralho", "put4", "buc3ta"
]

def check_palavroes(text: str) -> tuple[bool, str]:
    """Check for bad words in text"""
    text_lower = text.lower()
    for word in PALAVROES_LIST:
        if word in text_lower:
            return True, word
    return False, ""

def check_payment_bot_flood(user_id: str) -> bool:
    """Check if user is flooding the payment bot"""
    if not moderation_settings["antiflood_enabled"]:
        return False
    
    now = datetime.now(timezone.utc)
    user_times = payment_bot_flood_tracker.get(user_id, [])
    
    # Remove old timestamps
    window = moderation_settings["antiflood_window"]
    payment_bot_flood_tracker[user_id] = [
        t for t in user_times 
        if (now - t).total_seconds() < window
    ]
    
    # Add current timestamp
    payment_bot_flood_tracker[user_id].append(now)
    
    # Check if over limit
    return len(payment_bot_flood_tracker[user_id]) > moderation_settings["antiflood_limit"]

async def pb_admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin help"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    text = (
        "🛡️ *Comandos de Administração*\n\n"
        "👤 *Gerenciamento de Usuários:*\n"
        "/ban [ID] [motivo] - Banir usuário\n"
        "/unban [ID] - Desbanir usuário\n"
        "/mute [ID] [minutos] - Silenciar usuário\n"
        "/unmute [ID] - Remover silêncio\n"
        "/warn [ID] [motivo] - Advertir usuário\n"
        "/resetwarn [ID] - Zerar advertências\n"
        "/kick [ID] - Expulsar (pode voltar)\n"
        "/info [ID] - Info completa do usuário\n\n"
        "🛡️ *Moderação Automática:*\n"
        "/antiflood [on/off] - Liga/desliga antiflood\n"
        "/antiflood config [msgs] [segundos] - Configurar\n"
        "/antipalavroes [on/off] - Filtro de palavrões\n"
        "/autoban [on/off] - Ban automático por flood\n\n"
        "📊 *Relatórios:*\n"
        "/stats - Estatísticas gerais\n"
        "/vendas - Relatório de vendas\n"
        "/usuarios - Lista de usuários\n"
        "/banidos - Lista de banidos\n"
        "/mutados - Lista de silenciados\n"
        "/logs [qtd] - Últimos logs de moderação\n\n"
        "📢 *Comunicação:*\n"
        "/broadcast [msg] - Enviar para todos\n"
        "/dm [ID] [msg] - Mensagem direta"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def pb_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🚫 *Como banir:*\n"
            "/ban [ID] [motivo]\n\n"
            "Exemplo: /ban 123456789 Spam",
            parse_mode='Markdown'
        )
        return
    
    target_id = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Não especificado"
    
    if target_id == str(ADMIN_ID):
        await update.message.reply_text("❌ Você não pode se banir.")
        return
    
    now = datetime.now(timezone.utc)
    
    # Update user as banned
    result = await db.users.update_one(
        {"telegram_id": target_id},
        {
            "$set": {
                "is_banned": True,
                "ban_reason": reason,
                "banned_at": now.isoformat(),
                "banned_by": str(user.id)
            }
        }
    )
    
    # Log moderation action
    await db.moderation_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "ban",
        "target_id": target_id,
        "admin_id": str(user.id),
        "reason": reason,
        "timestamp": now.isoformat()
    })
    
    if result.modified_count > 0:
        await update.message.reply_text(
            f"🚫 *Usuário Banido*\n\n"
            f"ID: `{target_id}`\n"
            f"Motivo: {reason}\n"
            f"Por: Admin",
            parse_mode='Markdown'
        )
        
        # Try to notify the banned user
        if payment_bot_app:
            try:
                await payment_bot_app.bot.send_message(
                    chat_id=int(target_id),
                    text=f"🚫 *Você foi banido*\n\nMotivo: {reason}\n\nEntre em contato com o suporte se acredita que foi um erro.",
                    parse_mode='Markdown'
                )
            except:
                pass
    else:
        await update.message.reply_text(f"❌ Usuário `{target_id}` não encontrado.", parse_mode='Markdown')

async def pb_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban a user"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /unban [ID]")
        return
    
    target_id = context.args[0]
    now = datetime.now(timezone.utc)
    
    result = await db.users.update_one(
        {"telegram_id": target_id},
        {
            "$set": {"is_banned": False},
            "$unset": {"ban_reason": "", "banned_at": "", "banned_by": ""}
        }
    )
    
    # Log action
    await db.moderation_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "unban",
        "target_id": target_id,
        "admin_id": str(user.id),
        "timestamp": now.isoformat()
    })
    
    if result.modified_count > 0:
        await update.message.reply_text(f"✅ Usuário `{target_id}` foi desbanido.", parse_mode='Markdown')
        
        # Notify user
        if payment_bot_app:
            try:
                await payment_bot_app.bot.send_message(
                    chat_id=int(target_id),
                    text="✅ *Você foi desbanido!*\n\nSeja bem-vindo de volta. Por favor, siga as regras.",
                    parse_mode='Markdown'
                )
            except:
                pass
    else:
        await update.message.reply_text(f"❌ Usuário `{target_id}` não encontrado.", parse_mode='Markdown')

async def pb_mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute a user for specified duration"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🔇 *Como silenciar:*\n"
            "/mute [ID] [minutos]\n\n"
            "Exemplo: /mute 123456789 60\n"
            "Padrão: 60 minutos",
            parse_mode='Markdown'
        )
        return
    
    target_id = context.args[0]
    duration = int(context.args[1]) if len(context.args) > 1 else moderation_settings["mute_duration_default"]
    
    if target_id == str(ADMIN_ID):
        await update.message.reply_text("❌ Você não pode se silenciar.")
        return
    
    now = datetime.now(timezone.utc)
    unmute_at = now + timedelta(minutes=duration)
    
    result = await db.users.update_one(
        {"telegram_id": target_id},
        {
            "$set": {
                "is_muted": True,
                "muted_until": unmute_at.isoformat(),
                "muted_by": str(user.id)
            }
        }
    )
    
    # Log action
    await db.moderation_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "mute",
        "target_id": target_id,
        "admin_id": str(user.id),
        "duration": duration,
        "timestamp": now.isoformat()
    })
    
    if result.modified_count > 0:
        await update.message.reply_text(
            f"🔇 *Usuário Silenciado*\n\n"
            f"ID: `{target_id}`\n"
            f"Duração: {duration} minutos\n"
            f"Até: {unmute_at.strftime('%d/%m %H:%M')} UTC",
            parse_mode='Markdown'
        )
        
        if payment_bot_app:
            try:
                await payment_bot_app.bot.send_message(
                    chat_id=int(target_id),
                    text=f"🔇 *Você foi silenciado*\n\nDuração: {duration} minutos\n\nVocê pode usar o bot novamente após esse período.",
                    parse_mode='Markdown'
                )
            except:
                pass
    else:
        await update.message.reply_text(f"❌ Usuário `{target_id}` não encontrado.", parse_mode='Markdown')

async def pb_unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmute a user"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /unmute [ID]")
        return
    
    target_id = context.args[0]
    now = datetime.now(timezone.utc)
    
    result = await db.users.update_one(
        {"telegram_id": target_id},
        {
            "$set": {"is_muted": False},
            "$unset": {"muted_until": "", "muted_by": ""}
        }
    )
    
    await db.moderation_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "unmute",
        "target_id": target_id,
        "admin_id": str(user.id),
        "timestamp": now.isoformat()
    })
    
    if result.modified_count > 0:
        await update.message.reply_text(f"🔊 Usuário `{target_id}` pode falar novamente.", parse_mode='Markdown')
        
        if payment_bot_app:
            try:
                await payment_bot_app.bot.send_message(
                    chat_id=int(target_id),
                    text="🔊 *Você foi desmutado!*\n\nVocê pode usar o bot normalmente.",
                    parse_mode='Markdown'
                )
            except:
                pass
    else:
        await update.message.reply_text(f"❌ Usuário `{target_id}` não encontrado.", parse_mode='Markdown')

async def pb_warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Warn a user"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ *Como advertir:*\n"
            "/warn [ID] [motivo]\n\n"
            "3 advertências = ban automático",
            parse_mode='Markdown'
        )
        return
    
    target_id = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Comportamento inadequado"
    now = datetime.now(timezone.utc)
    
    # Get current warnings
    user_doc = await db.users.find_one({"telegram_id": target_id})
    if not user_doc:
        await update.message.reply_text(f"❌ Usuário `{target_id}` não encontrado.", parse_mode='Markdown')
        return
    
    warnings = user_doc.get("warnings", 0) + 1
    
    # Update warnings
    update_data = {"warnings": warnings}
    
    # Auto-ban on 3 warnings
    if warnings >= 3:
        update_data["is_banned"] = True
        update_data["ban_reason"] = "3 advertências atingidas"
        update_data["banned_at"] = now.isoformat()
    
    await db.users.update_one(
        {"telegram_id": target_id},
        {"$set": update_data}
    )
    
    await db.moderation_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "warn",
        "target_id": target_id,
        "admin_id": str(user.id),
        "reason": reason,
        "warning_count": warnings,
        "timestamp": now.isoformat()
    })
    
    if warnings >= 3:
        await update.message.reply_text(
            f"🚫 *Usuário Banido Automaticamente*\n\n"
            f"ID: `{target_id}`\n"
            f"Motivo: 3 advertências atingidas\n"
            f"Última advertência: {reason}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"⚠️ *Advertência {warnings}/3*\n\n"
            f"ID: `{target_id}`\n"
            f"Motivo: {reason}",
            parse_mode='Markdown'
        )
    
    if payment_bot_app:
        try:
            if warnings >= 3:
                msg = f"🚫 *Você foi banido*\n\n3 advertências atingidas.\nÚltimo motivo: {reason}"
            else:
                msg = f"⚠️ *Advertência {warnings}/3*\n\nMotivo: {reason}\n\n⚠️ Com 3 advertências você será banido automaticamente."
            await payment_bot_app.bot.send_message(chat_id=int(target_id), text=msg, parse_mode='Markdown')
        except:
            pass

async def pb_reset_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user warnings"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /resetwarn [ID]")
        return
    
    target_id = context.args[0]
    
    result = await db.users.update_one(
        {"telegram_id": target_id},
        {"$set": {"warnings": 0}}
    )
    
    if result.modified_count > 0:
        await update.message.reply_text(f"✅ Advertências de `{target_id}` foram zeradas.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ Usuário não encontrado.", parse_mode='Markdown')

async def pb_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get detailed user info"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /info [ID]")
        return
    
    target_id = context.args[0]
    
    user_doc = await db.users.find_one({"telegram_id": target_id}, {"_id": 0})
    if not user_doc:
        await update.message.reply_text(f"❌ Usuário `{target_id}` não encontrado.", parse_mode='Markdown')
        return
    
    # Get subscription
    sub = await get_user_subscription(target_id)
    plan = PLANS.get(sub.get("plan", "free"), PLANS["free"])
    
    # Get payment count
    payments = await db.mp_payments.count_documents({"telegram_id": target_id, "status": "approved"})
    
    # Calculate total spent
    pipeline = [
        {"$match": {"telegram_id": target_id, "status": "approved"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    spent_result = await db.mp_payments.aggregate(pipeline).to_list(1)
    total_spent = spent_result[0]["total"] if spent_result else 0
    
    # Status icons
    ban_status = "🚫 Banido" if user_doc.get("is_banned") else "✅ Ativo"
    mute_status = "🔇 Mutado" if user_doc.get("is_muted") else "🔊 Normal"
    
    text = (
        f"👤 *Informações do Usuário*\n\n"
        f"📛 *Nome:* {user_doc.get('name', 'N/A')}\n"
        f"🆔 *ID:* `{target_id}`\n"
        f"👤 *Username:* @{user_doc.get('username', 'N/A')}\n\n"
        f"📊 *Status:*\n"
        f"• {ban_status}\n"
        f"• {mute_status}\n"
        f"• ⚠️ Advertências: {user_doc.get('warnings', 0)}/3\n\n"
        f"💳 *Financeiro:*\n"
        f"• ⭐ Plano: {plan['name']}\n"
        f"• 💰 Total gasto: R$ {total_spent:.2f}\n"
        f"• 🧾 Pagamentos: {payments}\n\n"
        f"📅 *Datas:*\n"
        f"• Criado: {user_doc.get('created_at', 'N/A')[:10]}\n"
        f"• Último acesso: {user_doc.get('last_seen', 'N/A')[:16]}"
    )
    
    if user_doc.get("is_banned"):
        text += f"\n\n🚫 *Banimento:*\n"
        text += f"• Motivo: {user_doc.get('ban_reason', 'N/A')}\n"
        text += f"• Data: {user_doc.get('banned_at', 'N/A')[:10]}"
    
    if user_doc.get("is_muted"):
        text += f"\n\n🔇 *Mute:*\n"
        text += f"• Até: {user_doc.get('muted_until', 'N/A')[:16]}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def pb_antiflood_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure antiflood settings"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        status = "🟢 Ligado" if moderation_settings["antiflood_enabled"] else "🔴 Desligado"
        await update.message.reply_text(
            f"🛡️ *Configuração AntiFlood*\n\n"
            f"Status: {status}\n"
            f"Limite: {moderation_settings['antiflood_limit']} msgs\n"
            f"Janela: {moderation_settings['antiflood_window']} segundos\n"
            f"Auto-ban: {'🟢 Sim' if moderation_settings['auto_ban_on_flood'] else '🔴 Não'}\n\n"
            f"*Comandos:*\n"
            f"/antiflood on - Ligar\n"
            f"/antiflood off - Desligar\n"
            f"/antiflood config [msgs] [segundos]\n"
            f"Exemplo: /antiflood config 5 10",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == "on":
        moderation_settings["antiflood_enabled"] = True
        await update.message.reply_text("🛡️ AntiFlood *ATIVADO*", parse_mode='Markdown')
    elif action == "off":
        moderation_settings["antiflood_enabled"] = False
        await update.message.reply_text("🛡️ AntiFlood *DESATIVADO*", parse_mode='Markdown')
    elif action == "config" and len(context.args) >= 3:
        try:
            limit = int(context.args[1])
            window = int(context.args[2])
            moderation_settings["antiflood_limit"] = limit
            moderation_settings["antiflood_window"] = window
            await update.message.reply_text(
                f"✅ AntiFlood configurado:\n"
                f"Limite: {limit} mensagens\n"
                f"Janela: {window} segundos",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text("❌ Use números válidos.")
    else:
        await update.message.reply_text("❌ Comando inválido. Use /antiflood para ver opções.")

async def pb_antipalavroes_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure bad words filter"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        status = "🟢 Ligado" if moderation_settings["antipalavroes_enabled"] else "🔴 Desligado"
        await update.message.reply_text(
            f"🤬 *Filtro de Palavrões*\n\n"
            f"Status: {status}\n"
            f"Palavras bloqueadas: {len(PALAVROES_LIST)}\n\n"
            f"/antipalavroes on - Ligar\n"
            f"/antipalavroes off - Desligar",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == "on":
        moderation_settings["antipalavroes_enabled"] = True
        await update.message.reply_text("🤬 Filtro de palavrões *ATIVADO*", parse_mode='Markdown')
    elif action == "off":
        moderation_settings["antipalavroes_enabled"] = False
        await update.message.reply_text("🤬 Filtro de palavrões *DESATIVADO*", parse_mode='Markdown')

async def pb_autoban_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure auto-ban on flood"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        status = "🟢 Ligado" if moderation_settings["auto_ban_on_flood"] else "🔴 Desligado"
        await update.message.reply_text(
            f"⚡ *Auto-Ban por Flood*\n\n"
            f"Status: {status}\n\n"
            f"/autoban on - Ligar\n"
            f"/autoban off - Desligar",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == "on":
        moderation_settings["auto_ban_on_flood"] = True
        await update.message.reply_text("⚡ Auto-ban por flood *ATIVADO*", parse_mode='Markdown')
    elif action == "off":
        moderation_settings["auto_ban_on_flood"] = False
        await update.message.reply_text("⚡ Auto-ban por flood *DESATIVADO*", parse_mode='Markdown')

async def pb_list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List banned users"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    banned = await db.users.find({"is_banned": True}, {"_id": 0}).to_list(50)
    
    if not banned:
        await update.message.reply_text("✅ Nenhum usuário banido.")
        return
    
    text = f"🚫 *Usuários Banidos ({len(banned)})*\n\n"
    for u in banned:
        name = u.get("name", "N/A")[:12]
        tg_id = u.get("telegram_id")
        reason = u.get("ban_reason", "N/A")[:20]
        text += f"• `{tg_id}` - {name}\n  Motivo: {reason}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def pb_list_muted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List muted users"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    muted = await db.users.find({"is_muted": True}, {"_id": 0}).to_list(50)
    
    if not muted:
        await update.message.reply_text("✅ Nenhum usuário silenciado.")
        return
    
    text = f"🔇 *Usuários Silenciados ({len(muted)})*\n\n"
    for u in muted:
        name = u.get("name", "N/A")[:12]
        tg_id = u.get("telegram_id")
        until = u.get("muted_until", "N/A")[:16]
        text += f"• `{tg_id}` - {name}\n  Até: {until}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def pb_moderation_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show moderation logs"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    limit = int(context.args[0]) if context.args else 10
    limit = min(limit, 50)
    
    logs = await db.moderation_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    
    if not logs:
        await update.message.reply_text("📋 Nenhum log de moderação.")
        return
    
    text = f"📋 *Últimos {len(logs)} Logs de Moderação*\n\n"
    
    action_icons = {
        "ban": "🚫",
        "unban": "✅",
        "mute": "🔇",
        "unmute": "🔊",
        "warn": "⚠️",
        "kick": "👢"
    }
    
    for log in logs:
        icon = action_icons.get(log.get("action"), "📝")
        time = log.get("timestamp", "")[:16].replace("T", " ")
        action = log.get("action", "N/A")
        target = log.get("target_id", "N/A")
        
        text += f"{icon} {action.upper()} - `{target}`\n   {time}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def pb_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /broadcast [mensagem]")
        return
    
    message = " ".join(context.args)
    
    await update.message.reply_text("📤 Enviando broadcast...")
    
    users = await db.users.find({"is_banned": {"$ne": True}}, {"_id": 0, "telegram_id": 1}).to_list(1000)
    success = 0
    failed = 0
    
    for u in users:
        try:
            await payment_bot_app.bot.send_message(
                chat_id=int(u["telegram_id"]),
                text=f"📢 *Mensagem da Administração:*\n\n{message}",
                parse_mode='Markdown'
            )
            success += 1
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ *Broadcast Concluído*\n\n"
        f"Enviados: {success}\n"
        f"Falhas: {failed}",
        parse_mode='Markdown'
    )

async def pb_dm_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send direct message to user"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando apenas para administradores.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /dm [ID] [mensagem]")
        return
    
    target_id = context.args[0]
    message = " ".join(context.args[1:])
    
    try:
        await payment_bot_app.bot.send_message(
            chat_id=int(target_id),
            text=f"💬 *Mensagem do Suporte:*\n\n{message}",
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ Mensagem enviada para `{target_id}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar: {e}")

async def pb_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all messages in payment bot with moderation"""
    if not update.message or not update.message.text:
        return
    
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text
    
    # Skip admin
    if user.id == ADMIN_ID:
        return
    
    # Check if user exists, create if not
    user_doc = await db.users.find_one({"telegram_id": user_id})
    if not user_doc:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "telegram_id": user_id,
            "name": user.full_name,
            "username": user.username,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "is_banned": False,
            "is_muted": False,
            "warnings": 0
        })
        user_doc = {"is_banned": False, "is_muted": False}
    
    # Check if banned
    if user_doc.get("is_banned"):
        await update.message.reply_text("🚫 Você está banido e não pode usar este bot.")
        return
    
    # Check if muted
    if user_doc.get("is_muted"):
        muted_until = user_doc.get("muted_until", "")
        if muted_until:
            try:
                mute_end = datetime.fromisoformat(muted_until.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) < mute_end:
                    remaining = (mute_end - datetime.now(timezone.utc)).total_seconds() // 60
                    await update.message.reply_text(f"🔇 Você está silenciado. Aguarde {int(remaining)} minutos.")
                    return
                else:
                    # Auto-unmute
                    await db.users.update_one(
                        {"telegram_id": user_id},
                        {"$set": {"is_muted": False}, "$unset": {"muted_until": "", "muted_by": ""}}
                    )
            except:
                pass
    
    # Check antiflood
    if moderation_settings["antiflood_enabled"]:
        if check_payment_bot_flood(user_id):
            if moderation_settings["auto_ban_on_flood"]:
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"is_banned": True, "ban_reason": "Flood automático"}}
                )
                await update.message.reply_text("🚫 Você foi banido por flood.")
                
                # Notify admin
                await payment_bot_app.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🚨 *Auto-Ban por Flood*\n\nUsuário: `{user_id}` - {user.full_name}",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("⚠️ Calma! Você está enviando mensagens muito rápido.")
            return
    
    # Check bad words
    if moderation_settings["antipalavroes_enabled"]:
        has_bad_word, word = check_palavroes(text)
        if has_bad_word:
            # Auto-warn
            warnings = user_doc.get("warnings", 0) + 1
            
            if warnings >= 3:
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"is_banned": True, "ban_reason": "Palavrões (3 advertências)", "warnings": warnings}}
                )
                await update.message.reply_text("🚫 Você foi banido por uso repetido de palavrões.")
            else:
                await db.users.update_one(
                    {"telegram_id": user_id},
                    {"$set": {"warnings": warnings}}
                )
                await update.message.reply_text(
                    f"⚠️ *Advertência {warnings}/3*\n\n"
                    f"Linguagem inadequada não é permitida aqui.",
                    parse_mode='Markdown'
                )
            
            # Log
            await db.moderation_logs.insert_one({
                "id": str(uuid.uuid4()),
                "action": "auto_warn_palavrao",
                "target_id": user_id,
                "admin_id": "system",
                "reason": f"Palavra: {word}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Notify admin
            await payment_bot_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🤬 *Palavrão Detectado*\n\nUsuário: `{user_id}` - {user.full_name}\nPalavra: ||{word}||\nAdvertências: {warnings}/3",
                parse_mode='MarkdownV2'
            )
            return
    
    # Update last seen
    await db.users.update_one(
        {"telegram_id": user_id},
        {"$set": {"last_seen": datetime.now(timezone.utc).isoformat()}}
    )

# ============ FASTAPI APP ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, payment_bot_app
    
    # Start main Ananda bot (if token provided)
    if TG_TOKEN:
        telegram_app = Application.builder().token(TG_TOKEN).build()
        
        # Basic commands
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("help", help_command))
        
        # User spiritual commands
        telegram_app.add_handler(CommandHandler("meditar", meditar_command))
        telegram_app.add_handler(CommandHandler("orar", orar_command))
        telegram_app.add_handler(CommandHandler("versiculo", versiculo_command))
        telegram_app.add_handler(CommandHandler("pedido", pedido_oracao_command))
        telegram_app.add_handler(CommandHandler("compartilhar", compartilhar_command))
        telegram_app.add_handler(CommandHandler("meunome", meu_nome_command))
        
        # Subscription commands
        telegram_app.add_handler(CommandHandler("assinar", assinar_command))
        telegram_app.add_handler(CommandHandler("meuplano", meu_plano_command))
        telegram_app.add_handler(CommandHandler("premium", premium_command))
        telegram_app.add_handler(CommandHandler("vip", vip_command))
        
        # Payment handlers
        telegram_app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
        telegram_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
        
        # Admin commands
        telegram_app.add_handler(CommandHandler("stats", stats_command))
        telegram_app.add_handler(CommandHandler("users", users_list))
        telegram_app.add_handler(CommandHandler("online", online_list))
        telegram_app.add_handler(CommandHandler("check", check_user))
        telegram_app.add_handler(CommandHandler("msg", msg_command))
        telegram_app.add_handler(CommandHandler("historico", historico_command))
        telegram_app.add_handler(CommandHandler("ban", ban))
        telegram_app.add_handler(CommandHandler("unban", unban))
        telegram_app.add_handler(CommandHandler("resetwarn", reset_warnings))
        telegram_app.add_handler(CommandHandler("broadcast", broadcast))
        telegram_app.add_handler(CommandHandler("pedidos", pedidos_command))
        telegram_app.add_handler(CommandHandler("enviarversiculo", enviar_versiculo_command))
        
        # Message handler (must be last)
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await telegram_app.initialize()
        await telegram_app.start()
        asyncio.create_task(telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES))
        logger.info("Telegram bot Ananda started successfully!")
    else:
        logger.warning("TG_TOKEN not set. Telegram bot not started.")
    
    # Start Payment Bot (separate bot)
    if PAYMENT_BOT_TOKEN:
        payment_bot_app = Application.builder().token(PAYMENT_BOT_TOKEN).build()
        
        # Payment bot commands
        payment_bot_app.add_handler(CommandHandler("start", payment_start))
        payment_bot_app.add_handler(CommandHandler("menu", payment_menu))
        payment_bot_app.add_handler(CommandHandler("help", payment_menu))
        
        # Subscription commands
        payment_bot_app.add_handler(CommandHandler("premium", payment_premium_mp))
        payment_bot_app.add_handler(CommandHandler("vip", payment_vip_mp))
        
        # Product commands
        payment_bot_app.add_handler(CommandHandler("meditacao", payment_meditacao))
        payment_bot_app.add_handler(CommandHandler("pacote", payment_pacote))
        payment_bot_app.add_handler(CommandHandler("oracao", payment_oracao))
        payment_bot_app.add_handler(CommandHandler("doar", payment_doar))
        
        # User account commands
        payment_bot_app.add_handler(CommandHandler("minhascompras", payment_minhas_compras))
        payment_bot_app.add_handler(CommandHandler("meusaldo", payment_meu_saldo))
        
        # Admin commands
        payment_bot_app.add_handler(CommandHandler("stats", payment_stats_admin))
        payment_bot_app.add_handler(CommandHandler("vendas", payment_vendas_admin))
        payment_bot_app.add_handler(CommandHandler("usuarios", payment_usuarios_admin))
        
        await payment_bot_app.initialize()
        await payment_bot_app.start()
        asyncio.create_task(payment_bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES))
        logger.info("Payment Bot started successfully!")
    else:
        logger.warning("PAYMENT_BOT_TOKEN not set. Payment bot not started.")
    
    yield
    
    # Shutdown bots
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    
    if payment_bot_app:
        await payment_bot_app.updater.stop()
        await payment_bot_app.stop()
        await payment_bot_app.shutdown()
    
    client.close()

app = FastAPI(lifespan=lifespan)

api_router = APIRouter(prefix="/api")

# ============ API ENDPOINTS ============

@api_router.get("/")
async def root():
    return {"message": "Ananda Bot API Online", "status": "active"}

@api_router.get("/stats", response_model=StatsResponse)
async def get_stats():
    total_users = await db.users.count_documents({})
    banned_users = await db.users.count_documents({"is_banned": True})
    total_messages = await db.messages.count_documents({})
    
    # Active users (last 15 min)
    now = datetime.now(timezone.utc)
    fifteen_min_ago = (now - timedelta(minutes=15)).isoformat()
    active_users = await db.users.count_documents({"last_seen": {"$gte": fifteen_min_ago}})
    
    # Messages today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    messages_today = await db.messages.count_documents({"timestamp": {"$gte": today_start}})
    
    # Prayer requests
    prayer_requests = await db.prayer_requests.count_documents({})
    
    # Subscription stats
    premium_users = await db.subscriptions.count_documents({"plan": "premium"})
    vip_users = await db.subscriptions.count_documents({"plan": "vip"})
    
    return StatsResponse(
        total_users=total_users,
        active_users=active_users,
        total_messages=total_messages,
        banned_users=banned_users,
        messages_today=messages_today,
        prayer_requests=prayer_requests,
        premium_users=premium_users,
        vip_users=vip_users
    )

@api_router.get("/subscriptions")
async def get_subscriptions():
    subs = await db.subscriptions.find({}, {"_id": 0}).to_list(1000)
    return {"subscriptions": subs}

@api_router.get("/payments")
async def get_payments():
    payments = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"payments": payments}

@api_router.get("/users")
async def get_users(skip: int = 0, limit: int = 100):
    users = await db.users.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents({})
    return {"users": users, "total": total, "skip": skip, "limit": limit}

@api_router.get("/users/online")
async def get_online_users():
    now = datetime.now(timezone.utc)
    fifteen_min_ago = (now - timedelta(minutes=15)).isoformat()
    users = await db.users.find({"last_seen": {"$gte": fifteen_min_ago}}, {"_id": 0}).to_list(100)
    return {"users": users}

@api_router.post("/users/ban")
async def ban_user(request: BanRequest):
    result = await db.users.update_one(
        {"telegram_id": request.telegram_id},
        {"$set": {"is_banned": request.is_banned}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "telegram_id": request.telegram_id, "is_banned": request.is_banned}

@api_router.get("/messages")
async def get_messages(limit: int = 50):
    messages = await db.messages.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"messages": messages}

@api_router.get("/messages/{user_id}")
async def get_user_messages(user_id: str, limit: int = 20):
    messages = await db.messages.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"messages": messages}

@api_router.post("/broadcast")
async def send_broadcast(request: BroadcastRequest):
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Telegram bot not available")
    
    success_count = 0
    total_count = 0
    
    # Use cursor-based iteration for memory efficiency
    cursor = db.users.find({"is_banned": {"$ne": True}}, {"_id": 0, "telegram_id": 1})
    async for user in cursor:
        total_count += 1
        try:
            await telegram_app.bot.send_message(
                chat_id=int(user['telegram_id']),
                text=f"✨ *Mensagem de Ananda:*\n\n{request.message}",
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for {user['telegram_id']}: {e}")
            continue
    
    return {"success": True, "sent_to": success_count, "total_users": total_count}

@api_router.get("/learnings")
async def get_learnings(skip: int = 0, limit: int = 100):
    learnings = await db.learnings.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    return {"learnings": learnings}

@api_router.get("/learnings/{user_id}")
async def get_user_learning_api(user_id: str):
    learning = await db.learnings.find_one({"user_id": user_id}, {"_id": 0})
    if not learning:
        return {"user_id": user_id, "learning_text": "Nenhum aprendizado registrado ainda."}
    return learning

@api_router.get("/prayer-requests")
async def get_prayer_requests():
    requests = await db.prayer_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"requests": requests}

# ============ MERCADO PAGO ENDPOINTS ============

@api_router.get("/mercadopago/public-key")
async def get_mp_public_key():
    """Return the Mercado Pago public key for frontend"""
    return {"public_key": MP_PUBLIC_KEY}

@api_router.get("/mercadopago/plans")
async def get_mp_plans():
    """Return available plans with prices"""
    plans_response = {}
    for plan_id, plan in PLANS.items():
        if plan_id != "free":
            plans_response[plan_id] = {
                "name": plan["name"],
                "price_brl": plan["price_brl"],
                "price_stars": plan["price"],
                "features": plan["features"]
            }
    return {"plans": plans_response}

@api_router.get("/mercadopago/products")
async def get_mp_products():
    """Return available individual products"""
    return {"products": PRODUCTS}

@api_router.post("/mercadopago/checkout")
async def create_mp_checkout(request: MPPaymentRequest):
    """Create Mercado Pago Checkout Pro preference"""
    if not mp_sdk:
        raise HTTPException(status_code=503, detail="Mercado Pago não configurado")
    
    plan = PLANS.get(request.plan)
    if not plan or request.plan == "free":
        raise HTTPException(status_code=400, detail="Plano inválido")
    
    # Get the backend URL for callbacks
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
    
    preference_data = {
        "items": [
            {
                "id": f"ananda_{request.plan}",
                "title": f"Ananda {plan['name']} - 30 dias",
                "description": f"Assinatura {plan['name']} do bot Ananda por 30 dias. {', '.join(plan['features'])}",
                "category_id": "services",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": plan["price_brl"]
            }
        ],
        "payer": {
            "name": request.user_name or "Usuário Ananda",
            "email": request.email or "user@ananda.bot"
        },
        "back_urls": {
            "success": f"{backend_url}/api/mercadopago/success",
            "failure": f"{backend_url}/api/mercadopago/failure",
            "pending": f"{backend_url}/api/mercadopago/pending"
        },
        "auto_return": "approved",
        "external_reference": f"{request.telegram_id}|{request.plan}|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook",
        "statement_descriptor": "ANANDA BOT",
        "expires": True,
        "expiration_date_from": datetime.now(timezone.utc).isoformat(),
        "expiration_date_to": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    }
    
    try:
        preference_response = mp_sdk.preference().create(preference_data)
        
        if preference_response["status"] == 201:
            preference = preference_response["response"]
            
            # Save pending payment record
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "preference_id": preference["id"],
                "telegram_id": request.telegram_id,
                "plan": request.plan,
                "amount": plan["price_brl"],
                "status": "pending",
                "payment_method": "checkout_pro",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "preference_id": preference["id"],
                "init_point": preference["init_point"],
                "sandbox_init_point": preference["sandbox_init_point"]
            }
        else:
            logger.error(f"MP Checkout error: {preference_response}")
            raise HTTPException(status_code=500, detail="Erro ao criar checkout")
            
    except Exception as e:
        logger.error(f"MP Checkout exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/mercadopago/pix")
async def create_mp_pix(request: MPPixRequest):
    """Create PIX payment"""
    if not mp_sdk:
        raise HTTPException(status_code=503, detail="Mercado Pago não configurado")
    
    plan = PLANS.get(request.plan)
    if not plan or request.plan == "free":
        raise HTTPException(status_code=400, detail="Plano inválido")
    
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
    
    payment_data = {
        "transaction_amount": plan["price_brl"],
        "description": f"Ananda {plan['name']} - 30 dias",
        "payment_method_id": "pix",
        "payer": {
            "email": request.email,
            "first_name": request.user_name or "Usuário"
        },
        "external_reference": f"{request.telegram_id}|{request.plan}|{datetime.now(timezone.utc).timestamp()}",
        "notification_url": f"{backend_url}/api/mercadopago/webhook"
    }
    
    try:
        payment_response = mp_sdk.payment().create(payment_data)
        
        if payment_response["status"] == 201:
            payment = payment_response["response"]
            
            # Get PIX data
            pix_data = payment.get("point_of_interaction", {}).get("transaction_data", {})
            
            # Save payment record
            await db.mp_payments.insert_one({
                "id": str(uuid.uuid4()),
                "payment_id": str(payment["id"]),
                "telegram_id": request.telegram_id,
                "plan": request.plan,
                "amount": plan["price_brl"],
                "status": payment["status"],
                "payment_method": "pix",
                "pix_qr_code": pix_data.get("qr_code"),
                "pix_qr_code_base64": pix_data.get("qr_code_base64"),
                "pix_copy_paste": pix_data.get("qr_code"),
                "expires_at": payment.get("date_of_expiration"),
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "payment_id": payment["id"],
                "status": payment["status"],
                "qr_code": pix_data.get("qr_code"),
                "qr_code_base64": pix_data.get("qr_code_base64"),
                "expires_at": payment.get("date_of_expiration")
            }
        else:
            logger.error(f"MP PIX error: {payment_response}")
            raise HTTPException(status_code=500, detail="Erro ao criar PIX")
            
    except Exception as e:
        logger.error(f"MP PIX exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/mercadopago/payment/{payment_id}")
async def get_mp_payment_status(payment_id: str):
    """Check payment status"""
    if not mp_sdk:
        raise HTTPException(status_code=503, detail="Mercado Pago não configurado")
    
    try:
        # Validate payment_id is numeric
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ID de pagamento inválido")
        
        payment_response = mp_sdk.payment().get(payment_id_int)
        
        if payment_response["status"] == 200:
            payment = payment_response["response"]
            return {
                "payment_id": payment["id"],
                "status": payment["status"],
                "status_detail": payment.get("status_detail"),
                "amount": payment.get("transaction_amount"),
                "external_reference": payment.get("external_reference")
            }
        elif payment_response["status"] == 404:
            raise HTTPException(status_code=404, detail="Pagamento não encontrado")
        else:
            raise HTTPException(status_code=404, detail="Pagamento não encontrado")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MP Payment status error: {e}")
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

@api_router.post("/mercadopago/webhook")
async def mp_webhook(request: Request):
    """Handle Mercado Pago webhook notifications"""
    try:
        body = await request.json()
        logger.info(f"MP Webhook received: {body}")
        
        # Handle different notification types
        notification_type = body.get("type") or body.get("topic")
        
        if notification_type == "payment":
            data_id = body.get("data", {}).get("id") or body.get("id")
            
            if data_id and mp_sdk:
                # Get payment details
                payment_response = mp_sdk.payment().get(int(data_id))
                
                if payment_response["status"] == 200:
                    payment = payment_response["response"]
                    status = payment["status"]
                    external_ref = payment.get("external_reference", "")
                    
                    # Parse external reference: telegram_id|plan|timestamp
                    parts = external_ref.split("|")
                    if len(parts) >= 2:
                        telegram_id = parts[0]
                        plan = parts[1]
                        
                        # Update payment record
                        await db.mp_payments.update_one(
                            {"payment_id": str(data_id)},
                            {
                                "$set": {
                                    "status": status,
                                    "status_detail": payment.get("status_detail"),
                                    "updated_at": datetime.now(timezone.utc).isoformat()
                                }
                            }
                        )
                        
                        # If approved, activate subscription
                        if status == "approved":
                            await activate_subscription(telegram_id, plan, str(data_id))
                            logger.info(f"Subscription activated for {telegram_id} - Plan: {plan}")
                            
                            # Notify user via Telegram if bot is available
                            if telegram_app:
                                try:
                                    plan_info = PLANS.get(plan, {})
                                    await telegram_app.bot.send_message(
                                        chat_id=int(telegram_id),
                                        text=f"🎉 *Pagamento Confirmado!*\n\n"
                                             f"✨ Você agora é *{plan_info.get('name', plan)}*!\n"
                                             f"📅 Válido por 30 dias\n\n"
                                             f"Aproveite todos os benefícios! 🙏💕",
                                        parse_mode='Markdown'
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to notify user: {e}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"MP Webhook error: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/mercadopago/success")
async def mp_success(
    collection_id: Optional[str] = None,
    collection_status: Optional[str] = None,
    payment_id: Optional[str] = None,
    status: Optional[str] = None,
    external_reference: Optional[str] = None,
    payment_type: Optional[str] = None,
    merchant_order_id: Optional[str] = None,
    preference_id: Optional[str] = None,
    site_id: Optional[str] = None,
    processing_mode: Optional[str] = None,
    merchant_account_id: Optional[str] = None
):
    """Handle successful payment redirect"""
    logger.info(f"MP Success: payment_id={payment_id}, status={status}, external_ref={external_reference}")
    
    # Parse external reference
    if external_reference:
        parts = external_reference.split("|")
        if len(parts) >= 2:
            telegram_id = parts[0]
            plan = parts[1]
            
            # Activate subscription if payment approved
            if status == "approved" and payment_id:
                await activate_subscription(telegram_id, plan, payment_id)
                
                # Update payment record
                await db.mp_payments.update_one(
                    {"$or": [
                        {"preference_id": preference_id},
                        {"payment_id": payment_id}
                    ]},
                    {
                        "$set": {
                            "status": "approved",
                            "payment_id": payment_id,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
    
    # Redirect to success page
    frontend_url = os.environ.get("REACT_APP_FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}?payment=success&plan={plan if external_reference else ''}")

@api_router.get("/mercadopago/failure")
async def mp_failure(
    collection_id: Optional[str] = None,
    collection_status: Optional[str] = None,
    payment_id: Optional[str] = None,
    status: Optional[str] = None,
    external_reference: Optional[str] = None,
    preference_id: Optional[str] = None
):
    """Handle failed payment redirect"""
    logger.info(f"MP Failure: payment_id={payment_id}, status={status}")
    
    # Update payment record
    if preference_id:
        await db.mp_payments.update_one(
            {"preference_id": preference_id},
            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    frontend_url = os.environ.get("REACT_APP_FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}?payment=failed")

@api_router.get("/mercadopago/pending")
async def mp_pending(
    collection_id: Optional[str] = None,
    collection_status: Optional[str] = None,
    payment_id: Optional[str] = None,
    status: Optional[str] = None,
    external_reference: Optional[str] = None,
    preference_id: Optional[str] = None
):
    """Handle pending payment redirect"""
    logger.info(f"MP Pending: payment_id={payment_id}, status={status}")
    
    frontend_url = os.environ.get("REACT_APP_FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}?payment=pending")

@api_router.get("/mercadopago/payments")
async def get_mp_payments():
    """Get all Mercado Pago payments"""
    payments = await db.mp_payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"payments": payments}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

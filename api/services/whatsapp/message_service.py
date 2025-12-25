"""WhatsApp message service for AI integration and property image sending."""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "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"
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
AI_MODEL = "google/gemini-3-flash-preview"

SYSTEM_PROMPT = """Você é um assistente imobiliário especializado no Ceará.
Seu objetivo é:
1. Qualificar leads (RENDA MENSAL do cliente, localização, tipo de imóvel, quartos)
2. Buscar imóveis compatíveis com a capacidade financeira
3. Agendar visitas com corretores

## REGRA DE CÁLCULO DO VALOR MÁXIMO DO IMÓVEL:
Parcela máxima = 30% da renda mensal
Financiamento padrão = 360 meses (30 anos)
Valor máximo do imóvel = Renda × 0.30 × 360

EXEMPLOS:
- Renda R$ 5.000 → Parcela máx R$ 1.500 → Imóvel até R$ 540.000
- Renda R$ 8.000 → Parcela máx R$ 2.400 → Imóvel até R$ 864.000
- Renda R$ 10.000 → Parcela máx R$ 3.000 → Imóvel até R$ 1.080.000
- Renda R$ 15.000 → Parcela máx R$ 4.500 → Imóvel até R$ 1.620.000

IMPORTANTE: Pergunte "Qual sua renda mensal?" de forma natural.
Depois informe: "Com sua renda de R$ X, você pode financiar imóveis de até R$ Y"

Seja amigável e objetivo. Use emojis moderadamente."""


class WhatsAppMessageService:
    """Service for managing WhatsApp messages with AI integration."""

    @staticmethod
    def get_ai_response(conversation_id: str, message: str) -> str:
        """
        Get AI response from OpenRouter API using Gemini 2.0 Flash.

        This calls the OpenRouter API to get contextual AI responses for lead qualification
        and property search assistance.

        Args:
            conversation_id: Conversation ID to maintain context
            message: User message text

        Returns:
            AI-generated response text
        """
        try:
            logger.info(f"Getting AI response for conversation {conversation_id}")

            # Prepare the API request payload
            payload = {
                "model": AI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": message
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }

            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://sells.orquestr.ai",
                "X-Title": "Sells - Real Estate AI Assistant"
            }

            # Make synchronous HTTP request to OpenRouter
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()

                data = response.json()
                ai_message = data["choices"][0]["message"]["content"]

                logger.info(f"Successfully got AI response for conversation {conversation_id}")
                return ai_message.strip()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from OpenRouter API: {e.response.status_code} - {e.response.text}")
            return "Desculpe, estou com dificuldades técnicas no momento. Por favor, tente novamente em instantes."
        except httpx.RequestError as e:
            logger.error(f"Network error calling OpenRouter API: {e}")
            return "Desculpe, não consegui me conectar ao serviço. Verifique sua conexão e tente novamente."
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected API response format: {e}")
            return "Desculpe, recebi uma resposta inesperada. Por favor, tente novamente."
        except Exception as e:
            logger.exception(f"Unexpected error getting AI response: {e}")
            return "Desculpe, ocorreu um erro inesperado. Por favor, tente novamente."

    @staticmethod
    async def send_property_with_image(session: str, chat_id: str, property_data: dict[str, Any]) -> None:
        """
        Send property information with image to WhatsApp.

        Args:
            session: WhatsApp session name
            chat_id: Recipient chat ID
            property_data: Property data including image URL and details
        """
        try:
            from .waha_client import WAHAClient

            client = WAHAClient()

            # Extract property details
            title = property_data.get("title", "Imóvel")
            price = property_data.get("price_formatted", "")
            bedrooms = property_data.get("bedrooms", "")
            area = property_data.get("area", "")
            location = f"{property_data.get('neighborhood', '')}, {property_data.get('city', '')}"
            image_url = property_data.get("main_image") or property_data.get("images", [None])[0]

            # Build caption
            caption = f"*{title}*\n\n"
            if price:
                caption += f"💰 Valor: {price}\n"
            if bedrooms:
                caption += f"🛏️ Quartos: {bedrooms}\n"
            if area:
                caption += f"📐 Área: {area}m²\n"
            if location:
                caption += f"📍 Localização: {location}\n"

            # Send image with caption
            if image_url:
                await client.send_image(session, chat_id, image_url, caption)
                logger.info(f"Sent property {title} to {chat_id}")
            else:
                # Send as text if no image
                await client.send_text(session, chat_id, caption)
                logger.warning(f"No image for property {title}, sent as text")
        except Exception as e:
            logger.exception(f"Error sending property with image: {e}")

    @staticmethod
    async def send_visit_confirmation(lead_phone: str, visit: dict[str, Any]) -> None:
        """
        Send visit confirmation message to lead.

        Args:
            lead_phone: Lead's WhatsApp number
            visit: Visit data including property, broker, and scheduled time
        """
        try:
            from .waha_client import WAHAClient

            client = WAHAClient()

            # TODO: Get active session for tenant
            session = "default"  # Replace with actual session lookup

            property_title = visit.get("property_title", "")
            broker_name = visit.get("broker_name", "")
            scheduled_at = visit.get("scheduled_at", "")

            message = f"""✅ *Visita Agendada!*

Imóvel: {property_title}
Corretor: {broker_name}
Data/Hora: {scheduled_at}

O corretor entrará em contato com você em breve para confirmar os detalhes.

Qualquer dúvida, estou à disposição! 😊"""

            await client.send_text(session, lead_phone, message)
            logger.info(f"Sent visit confirmation to {lead_phone}")
        except Exception as e:
            logger.exception(f"Error sending visit confirmation: {e}")

    @staticmethod
    async def send_broker_visit_notification(broker_phone: str, visit: dict[str, Any]) -> None:
        """
        Send visit assignment notification to broker.

        Args:
            broker_phone: Broker's WhatsApp number
            visit: Visit data including lead and property details
        """
        try:
            from .waha_client import WAHAClient

            client = WAHAClient()

            # TODO: Get active session for tenant
            session = "default"

            lead_name = visit.get("lead_name", "")
            lead_phone = visit.get("lead_phone", "")
            property_title = visit.get("property_title", "")
            scheduled_at = visit.get("scheduled_at", "")

            message = f"""🏠 *Nova Visita Agendada*

Lead: {lead_name}
Telefone: {lead_phone}
Imóvel: {property_title}
Data/Hora: {scheduled_at}

Responda "ACEITAR" para confirmar ou "RECUSAR" para recusar esta visita.

Você tem 30 minutos para responder."""

            await client.send_text(session, broker_phone, message)
            logger.info(f"Sent visit notification to broker {broker_phone}")
        except Exception as e:
            logger.exception(f"Error sending broker visit notification: {e}")

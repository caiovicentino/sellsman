"""WhatsApp webhook service for handling incoming messages and events."""
import asyncio
import logging
from typing import Any

from flask import Response

from .message_service import WhatsAppMessageService
from .waha_client import WAHAClient

logger = logging.getLogger(__name__)


class WhatsAppWebhookService:
    """Service for handling WhatsApp webhook events."""

    @staticmethod
    def handle_incoming_message(payload: dict[str, Any]) -> Response:
        """
        Handle incoming WhatsApp message from WAHA webhook synchronously.

        Processes the message, gets AI response, and sends reply - all synchronously.

        Args:
            payload: Webhook payload containing message data

        Returns:
            Flask Response object with processing status
        """
        try:
            # 1. Extract event type and message data
            event = payload.get("event")
            session = payload.get("session")
            message_data = payload.get("payload", {})

            logger.info(f"Processing webhook event: {event} from session {session}")

            # 2. Ignore non-message events
            if event != "message":
                logger.debug(f"Ignoring non-message event: {event}")
                return Response(status=200)

            # 3. Ignore messages from self (fromMe = true)
            if message_data.get("fromMe", False):
                logger.debug("Ignoring message from self (fromMe=true)")
                return Response(status=200)

            # 4. Extract phone number and message text
            from_number = message_data.get("from", "")
            message_text = message_data.get("body", "")
            message_type = message_data.get("type", "text")

            # Validate required fields
            if not from_number or not message_text:
                logger.warning(f"Missing required fields - from: {from_number}, text: {message_text}")
                return Response(status=200)

            # Only process text messages
            if message_type != "text":
                logger.debug(f"Ignoring non-text message type: {message_type}")
                return Response(status=200)

            logger.info(f"Processing message from {from_number}: {message_text[:50]}...")

            # 5. Get AI response synchronously using conversation_id (phone number)
            conversation_id = from_number
            ai_response = WhatsAppMessageService.get_ai_response(conversation_id, message_text)

            logger.info(f"Got AI response for {from_number}: {ai_response[:50]}...")

            # 6. Send response via WAHA synchronously
            client = WAHAClient()
            send_result = asyncio.run(client.send_text(session, from_number, ai_response))

            logger.info(f"Successfully sent response to {from_number} via session {session}")

            # 7. Return success status
            return Response(
                status=200,
                response='{"status": "processed", "message": "Message processed and response sent"}',
                mimetype="application/json",
            )

        except Exception as e:
            logger.exception(f"Error handling incoming message: {e}")
            return Response(
                status=500,
                response=f'{{"status": "error", "message": "Internal server error: {str(e)}"}}',
                mimetype="application/json",
            )

    @staticmethod
    def handle_session_status(payload: dict[str, Any]) -> Response:
        """
        Handle WhatsApp session status change events.

        Args:
            payload: Webhook payload containing session status

        Returns:
            Flask Response object
        """
        try:
            session = payload.get("session")
            status = payload.get("payload", {}).get("status")

            logger.info(f"Session {session} status changed to: {status}")

            # Update session status in database if needed
            # This could trigger notifications to admins when sessions disconnect

            return Response(status=200)
        except Exception as e:
            logger.exception(f"Error handling session status: {e}")
            return Response(status=500)

    @staticmethod
    def handle_broker_response(payload: dict[str, Any]) -> Response:
        """
        Handle broker responses (accept/decline visit assignments).

        This is called when a broker responds to a visit assignment notification.

        Args:
            payload: Message payload containing broker response

        Returns:
            Flask Response object
        """
        try:
            from_number = payload.get("from_number", "")
            message_text = payload.get("message_text", "").lower().strip()

            # Check if this is from a broker
            # Look for keywords like "aceitar", "recusar", "sim", "não"
            # Extract visit ID from context (could be stored in conversation state)

            logger.info(f"Broker {from_number} responded: {message_text}")

            # Process broker response
            # Update BrokerAssignment status
            # If declined, cascade to next broker
            # If accepted, notify lead

            return Response(status=200)
        except Exception as e:
            logger.exception(f"Error handling broker response: {e}")
            return Response(status=500)

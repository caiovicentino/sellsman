"""WAHA (WhatsApp HTTP API) client for sending messages and managing sessions."""
import logging
from typing import Any

import httpx

from configs import dify_config

logger = logging.getLogger(__name__)


class WAHAClient:
    """Client for interacting with WAHA API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        """
        Initialize WAHA client.

        Args:
            base_url: WAHA API base URL (defaults to env var WAHA_BASE_URL)
            api_key: WAHA API key (defaults to env var WAHA_API_KEY)
        """
        self.base_url = base_url or getattr(dify_config, "WAHA_BASE_URL", "http://waha:3000")
        self.api_key = api_key or getattr(dify_config, "WAHA_API_KEY", "")
        self.headers = {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    async def create_session(self, session_name: str) -> dict[str, Any]:
        """
        Create a new WhatsApp session.

        Args:
            session_name: Unique name for the session

        Returns:
            Session creation response with QR code and status
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/sessions", headers=self.headers, json={"name": session_name}
                )
                response.raise_for_status()
                logger.info(f"Created WAHA session: {session_name}")
                return response.json()
        except httpx.HTTPError as e:
            logger.exception(f"Failed to create WAHA session {session_name}: {e}")
            raise

    async def get_qr_code(self, session_name: str) -> str:
        """
        Get QR code for session authentication.

        Args:
            session_name: Session name

        Returns:
            QR code as base64 string
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/sessions/{session_name}/qr", headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("qr", "")
        except httpx.HTTPError as e:
            logger.exception(f"Failed to get QR code for session {session_name}: {e}")
            raise

    async def get_session_status(self, session_name: str) -> dict[str, Any]:
        """
        Get session status.

        Args:
            session_name: Session name

        Returns:
            Session status information
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/sessions/{session_name}", headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.exception(f"Failed to get session status {session_name}: {e}")
            raise

    async def send_text(self, session: str, chat_id: str, text: str) -> dict[str, Any]:
        """
        Send text message via WhatsApp.

        Args:
            session: Session name
            chat_id: Recipient chat ID (phone number with country code)
            text: Message text

        Returns:
            Send message response
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/{session}/sendText",
                    headers=self.headers,
                    json={"chatId": chat_id, "text": text},
                )
                response.raise_for_status()
                logger.info(f"Sent text message to {chat_id} via session {session}")
                return response.json()
        except httpx.HTTPError as e:
            logger.exception(f"Failed to send text message to {chat_id}: {e}")
            raise

    async def send_image(self, session: str, chat_id: str, image_url: str, caption: str | None = None) -> dict[str, Any]:
        """
        Send image message via WhatsApp.

        Args:
            session: Session name
            chat_id: Recipient chat ID
            image_url: URL of the image to send
            caption: Optional image caption

        Returns:
            Send message response
        """
        try:
            payload: dict[str, Any] = {"chatId": chat_id, "file": {"url": image_url}}
            if caption:
                payload["caption"] = caption

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/{session}/sendImage", headers=self.headers, json=payload
                )
                response.raise_for_status()
                logger.info(f"Sent image to {chat_id} via session {session}")
                return response.json()
        except httpx.HTTPError as e:
            logger.exception(f"Failed to send image to {chat_id}: {e}")
            raise

    async def send_location(
        self, session: str, chat_id: str, latitude: float, longitude: float, title: str | None = None
    ) -> dict[str, Any]:
        """
        Send location message via WhatsApp.

        Args:
            session: Session name
            chat_id: Recipient chat ID
            latitude: Location latitude
            longitude: Location longitude
            title: Optional location title

        Returns:
            Send message response
        """
        try:
            payload: dict[str, Any] = {"chatId": chat_id, "latitude": latitude, "longitude": longitude}
            if title:
                payload["title"] = title

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/{session}/sendLocation", headers=self.headers, json=payload
                )
                response.raise_for_status()
                logger.info(f"Sent location to {chat_id} via session {session}")
                return response.json()
        except httpx.HTTPError as e:
            logger.exception(f"Failed to send location to {chat_id}: {e}")
            raise

    async def delete_session(self, session_name: str) -> dict[str, Any]:
        """
        Delete a WhatsApp session.

        Args:
            session_name: Session name to delete

        Returns:
            Deletion response
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(f"{self.base_url}/api/sessions/{session_name}", headers=self.headers)
                response.raise_for_status()
                logger.info(f"Deleted WAHA session: {session_name}")
                return response.json()
        except httpx.HTTPError as e:
            logger.exception(f"Failed to delete WAHA session {session_name}: {e}")
            raise

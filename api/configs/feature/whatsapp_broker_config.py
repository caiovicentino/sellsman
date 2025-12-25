from pydantic import Field, HttpUrl, PositiveInt
from pydantic_settings import BaseSettings


class WhatsAppConfig(BaseSettings):
    """
    Configuration for WAHA WhatsApp API integration
    """

    WAHA_API_KEY: str = Field(
        description="API key for WAHA WhatsApp service authentication",
        default="your-secure-key-here",
    )

    WAHA_BASE_URL: HttpUrl = Field(
        description="Base URL for WAHA WhatsApp API service (internal docker network)",
        default=HttpUrl("http://waha:3000"),
    )

    WAHA_DOCKER_TOKEN: str = Field(
        description="Docker registry token for WAHA Plus image",
        default="",
    )


class OpenRouterConfig(BaseSettings):
    """
    Configuration for OpenRouter AI API
    """

    OPENROUTER_API_KEY: str = Field(
        description="API key for OpenRouter multi-model AI access",
        default="",
    )


class BrokerAssignmentConfig(BaseSettings):
    """
    Configuration for real estate broker assignment and timeout logic
    """

    BROKER_TIMEOUT_MINUTES: PositiveInt = Field(
        description="Default timeout in minutes for broker to respond to visit assignment",
        default=30,
    )

    BROKER_SAME_DAY_MIN_HOURS: PositiveInt = Field(
        description="Minimum hours before same-day visit to apply reduced timeout logic",
        default=2,
    )


class FollowUpConfig(BaseSettings):
    """
    Configuration for automated follow-up intervals
    """

    FOLLOWUP_REMINDER_2H: PositiveInt = Field(
        description="Follow-up reminder interval in hours (first reminder after property viewing)",
        default=2,
    )

    FOLLOWUP_CONTACT_24H: PositiveInt = Field(
        description="Second contact follow-up interval in hours",
        default=24,
    )

    FOLLOWUP_NEW_PROPERTIES_3D: PositiveInt = Field(
        description="New properties notification interval in hours (3 days)",
        default=72,
    )

    FOLLOWUP_SPECIAL_OFFER_7D: PositiveInt = Field(
        description="Special offer follow-up interval in hours (7 days)",
        default=168,
    )

    FOLLOWUP_FINAL_14D: PositiveInt = Field(
        description="Final contact follow-up interval in hours (14 days)",
        default=336,
    )

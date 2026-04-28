"""Pydantic response/request models for the REST API.

Centralized here so they can be referenced from any route module without
introducing circular imports.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from modules.notifier import validate_discord_webhook_url


class GameItem(BaseModel):
    """A free game as returned by the scraper."""

    title: str = Field(..., description="Name of the free game", examples=["Celeste"])
    store: str = Field(
        "epic",
        description="Store identifier where the game is offered for free",
        examples=["epic", "steam"],
    )
    link: str = Field(..., description="Store URL for the game")
    end_date: str = Field(
        ...,
        description="ISO-8601 timestamp when the free promotion ends",
        examples=["2024-01-31T15:00:00.000Z"],
    )
    description: str = Field(..., description="Short description of the game")
    thumbnail: str = Field(..., description="URL to the game's thumbnail image")
    game_type: str = Field(
        "game", description="Content type: 'game' or 'dlc'", examples=["game", "dlc"]
    )
    original_price: Optional[str] = Field(
        default=None,
        description="Original retail price before the free promotion",
        examples=["$19.99", "€14.99"],
    )
    review_scores: List[str] = Field(
        default_factory=list,
        description="Review scores from available sources",
        examples=[["Very Positive", "Metascore: 83"]],
    )


class HealthResponse(BaseModel):
    """Response from the health check endpoint."""

    status: str = Field(
        ..., description="Overall health status", examples=["healthy", "unhealthy"]
    )
    epic_games_api: str = Field(
        ..., description="Epic Games API reachability", examples=["healthy", "unhealthy"]
    )
    database: str = Field(
        ...,
        description="Database connectivity status",
        examples=["healthy", "unhealthy", "not_configured"],
    )


class GamesLatestResponse(BaseModel):
    """Response from the latest games endpoint."""

    games: List[GameItem] = Field(..., description="List of the most recently fetched games")
    count: int = Field(..., description="Number of games returned", examples=[3])


class GamesHistoryResponse(BaseModel):
    """Response from the paginated game history endpoint."""

    games: List[GameItem] = Field(..., description="List of games for the current page")
    total: int = Field(..., description="Total number of games in storage", examples=[42])
    limit: int = Field(..., description="Maximum number of games per page", examples=[20])
    offset: int = Field(..., description="Number of games skipped", examples=[0])


class ResendResponse(BaseModel):
    """Response after re-sending a Discord notification."""

    status: str = Field(..., description="Result of the operation", examples=["success"])
    games_sent: int = Field(
        ..., description="Number of games included in the notification", examples=[2]
    )


class MetricsResponse(BaseModel):
    """Service metrics snapshot."""

    uptime_seconds: float = Field(
        ..., description="Seconds since the API server started", examples=[3600.5]
    )
    games_processed: int = Field(
        ..., description="Total games processed since startup", examples=[12]
    )
    discord_notifications_sent: int = Field(
        ..., description="Successful Discord notifications sent", examples=[5]
    )
    discord_notification_errors: int = Field(
        ..., description="Failed Discord notification attempts", examples=[1]
    )
    errors: int = Field(
        ..., description="Total error count across all operations", examples=[2]
    )


class ConfigResponse(BaseModel):
    """Non-secret runtime configuration."""

    epic_games_api_url: str = Field(..., description="Epic Games API endpoint URL")
    epic_games_region: str = Field(
        ..., description="Region code used in store links", examples=["en-US"]
    )
    data_file_path: str = Field(..., description="Path to the JSON storage file")
    enable_healthcheck: bool = Field(
        ..., description="Whether the external health check ping is enabled"
    )
    healthcheck_configured: bool = Field(
        ..., description="Whether an external health check monitor URL is configured"
    )
    healthcheck_interval_minutes: int = Field(
        ..., description="Interval in minutes between health check pings", examples=[1]
    )
    db_host: Optional[str] = Field(
        None, description="PostgreSQL host (None when DB is not configured)"
    )
    db_port: int = Field(..., description="PostgreSQL port", examples=[5432])
    db_name: Optional[str] = Field(None, description="PostgreSQL database name")
    db_user: Optional[str] = Field(None, description="PostgreSQL user")
    timezone: str = Field(
        ..., description="Configured timezone for date display", examples=["UTC"]
    )
    locale: str = Field(
        ..., description="Locale used for date formatting", examples=["en_US.UTF-8"]
    )
    schedule_time: str = Field(
        ..., description="Daily check time in HH:MM format", examples=["12:00"]
    )
    date_format: str = Field(
        ..., description="strftime format string for promotion end dates"
    )


class CheckE2EResponse(BaseModel):
    """Response from the end-to-end check endpoint."""

    games_fetched: int = Field(
        ..., description="Number of free games fetched from all enabled stores", examples=[2]
    )
    games: List[GameItem] = Field(..., description="Full list of fetched game objects")
    already_in_storage: List[str] = Field(
        ..., description="Titles of games that were already saved in storage"
    )
    new_games: List[str] = Field(
        ..., description="Titles of games not yet in storage"
    )
    notification_status: str = Field(
        ...,
        description="Discord notification result",
        examples=["sent", "skipped", "failed: ..."],
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Human-readable error message")


class WebhookOverrideRequest(BaseModel):
    """Optional request body for Discord notification endpoints.

    Allows callers to specify an alternative Discord webhook URL so that
    test/E2E runs can target a non-default channel without changing global
    configuration.  The ``webhook_url`` field is validated to allow only
    legitimate Discord webhook URLs, preventing SSRF attacks.
    """

    webhook_url: Optional[str] = Field(
        None,
        description=(
            "Override Discord webhook URL for this request. "
            "Must be a valid Discord webhook URL "
            "(https://discord.com/api/webhooks/... or https://discordapp.com/api/webhooks/...)."
        ),
    )

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        v_stripped = v.strip()
        if not v_stripped:
            raise ValueError("webhook_url must not be empty or whitespace")

        validate_discord_webhook_url(v_stripped)
        return v_stripped

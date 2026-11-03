"""Application configuration and security defaults for W.E.D.N.E.S.D.A.Y."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines into the environment. Real environment variables win.

    Values are never logged. Lines that aren't KEY=VALUE are ignored, as are the
    ``your_..._here`` placeholders from .env.example, so a copied template can't pass
    for a real credential.
    """
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key or not value or (value.startswith("your_") and value.endswith("_here")):
            continue
        os.environ.setdefault(key, value)


if not os.environ.get("FRIDAY_SKIP_DOTENV"):
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseModel):
    """Central settings for W.E.D.N.E.S.D.A.Y. Milestone 1."""
    app_name: str = "W.E.D.N.E.S.D.A.Y."
    version: str = "0.1.0"
    
    # Strictly localhost binding — never expose to 0.0.0.0 / local network
    host: str = "127.0.0.1"
    port: int = 8000
    
    # Ollama endpoint and local model selection
    ollama_base_url: str = "http://127.0.0.1:11434"
    model_name: str = "qwen2.5:7b"
    # Per model call. Sized for CPU inference, where a full-length reply can take minutes.
    request_timeout_seconds: float = Field(
        default_factory=lambda: float(os.environ.get("FRIDAY_MODEL_TIMEOUT", "300"))
    )
    
    # Configurable workspace root (must resolve to an absolute path)
    workspace_root: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("FRIDAY_WORKSPACE", str(Path.home() / "FridayWorkspace"))
        ).resolve()
    )
    max_workspace_entries: int = 40
    
    # Media control policy: disabled by default in Milestone 1
    media_control_enabled: bool = False

    # Location tracking configuration — disabled by default, requires explicit user activation
    location_read_enabled: bool = False
    location_tracking_enabled: bool = False
    location_default_interval_seconds: int = 60
    location_min_interval_seconds: int = 15
    location_staleness_threshold_seconds: int = 180
    location_state_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("FRIDAY_LOCATION_STATE", str(Path.home() / ".friday" / "location_state.json"))
        ).resolve()
    )
    memory_db_path: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("FRIDAY_MEMORY_DB", str(Path.home() / ".friday" / "memory.sqlite3"))
        ).resolve()
    )
    location_lock_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("FRIDAY_LOCATION_LOCK", str(Path.home() / ".friday" / "location.lock"))
        ).resolve()
    )

    # Location enrichment provider selection (Phase 2D): 'osm', 'google', or 'none'
    location_provider: str = Field(
        default_factory=lambda: os.environ.get("LOCATION_PROVIDER", "osm").strip().lower()
    )

    # Google Maps Platform configuration (Phase 2C) — disabled by default, requires API key
    google_maps_api_key: Optional[str] = Field(
        default_factory=lambda: os.environ.get("GOOGLE_MAPS_API_KEY")
    )
    places_search_enabled: bool = False
    geocoding_cache_ttl_seconds: int = 300
    nearby_search_max_radius_m: int = 10000
    google_maps_timeout_seconds: float = 8.0

    # OpenStreetMap (OSM) Platform configuration (Phase 2D) — Free, no API key required
    osm_nominatim_url: str = Field(
        default_factory=lambda: os.environ.get("OSM_NOMINATIM_URL", "https://nominatim.openstreetmap.org/reverse")
    )
    osm_overpass_url: str = Field(
        default_factory=lambda: os.environ.get("OSM_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    )
    osm_overpass_fallback_url: str = Field(
        default_factory=lambda: os.environ.get("OSM_OVERPASS_FALLBACK_URL", "https://overpass.kumi.systems/api/interpreter")
    )
    osm_user_agent: str = Field(
        default_factory=lambda: os.environ.get("OSM_USER_AGENT", "WEDNESDAY-Assistant/0.1.0")
    )
    osm_contact_email: Optional[str] = Field(
        default_factory=lambda: os.environ.get("OSM_CONTACT_EMAIL")
    )
    osm_rate_limit_seconds: float = 1.0
    osm_cache_ttl_seconds: int = 600
    osm_timeout_seconds: float = 12.0

    # Phase 3: Real-Time World Intelligence Engine Configuration
    world_intelligence_enabled: bool = True
    world_read_enabled: bool = True
    world_http_timeout_seconds: float = 12.0

    # USGS Earthquakes Feed
    usgs_earthquakes_url: str = Field(
        default_factory=lambda: os.environ.get(
            "USGS_EARTHQUAKES_URL",
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
        )
    )
    usgs_cache_ttl_seconds: int = 180

    # Open-Meteo Weather Forecast API (Free, CC BY 4.0)
    open_meteo_forecast_url: str = Field(
        default_factory=lambda: os.environ.get(
            "OPEN_METEO_FORECAST_URL",
            "https://api.open-meteo.com/v1/forecast"
        )
    )
    open_meteo_cache_ttl_seconds: int = 900

    # NASA EONET v3 Natural Event Tracker
    nasa_eonet_url: str = Field(
        default_factory=lambda: os.environ.get(
            "NASA_EONET_URL",
            "https://eonet.gsfc.nasa.gov/api/v3/events"
        )
    )
    nasa_eonet_days: int = 30
    nasa_eonet_cache_ttl_seconds: int = 1800

    # GDACS Global Disaster Alert and Coordination System
    gdacs_feed_url: str = Field(
        default_factory=lambda: os.environ.get(
            "GDACS_FEED_URL",
            "https://www.gdacs.org/xml/rss.xml"
        )
    )
    gdacs_geojson_url: str = Field(
        default_factory=lambda: os.environ.get(
            "GDACS_GEOJSON_URL",
            "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP?eventtypes=EQ,TC,FL,VO,DR,WF"
        )
    )
    gdacs_cache_ttl_seconds: int = 900

    # Reputable News RSS Allowlist (Stage 8)
    news_rss_enabled: bool = True
    news_rss_feeds: list[str] = Field(
        default_factory=lambda: [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        ]
    )
    news_cache_ttl_seconds: int = 1800
    
    # Execution & reasoning budget limits
    # Additional world layers (ported from the God's Eye View concept; keyless unless noted)
    celestrak_gp_url: str = Field(
        default_factory=lambda: os.environ.get("CELESTRAK_GP_URL", "https://celestrak.org/NORAD/elements/gp.php")
    )
    # CelesTrak asks clients not to re-download the same group more than every 2 hours.
    celestrak_groups: list[str] = Field(default_factory=lambda: ["stations", "visual", "gps-ops", "weather"])
    celestrak_cache_ttl_seconds: int = 6 * 3600
    adsb_lol_url: str = Field(default_factory=lambda: os.environ.get("ADSB_LOL_URL", "https://api.adsb.lol/v2"))
    flights_cache_ttl_seconds: int = 20
    flights_max_radius_nm: int = 250
    launch_library_url: str = Field(
        default_factory=lambda: os.environ.get("LAUNCH_LIBRARY_URL", "https://ll.thespacedevs.com/2.3.0/launches/upcoming/")
    )
    # Launch Library's free tier allows 15 requests/hour.
    launches_cache_ttl_seconds: int = 30 * 60
    firms_map_key: Optional[str] = Field(default_factory=lambda: (os.environ.get("FIRMS_MAP_KEY") or "").strip() or None)
    firms_url: str = Field(default_factory=lambda: os.environ.get("FIRMS_URL", "https://firms.modaps.eosdis.nasa.gov/api/area/csv"))
    firms_source: str = Field(default_factory=lambda: os.environ.get("FIRMS_SOURCE", "VIIRS_NOAA20_NRT"))
    firms_cache_ttl_seconds: int = 30 * 60
    firms_max_points: int = 4000

    max_turns_per_request: int = 6
    max_tool_calls_per_turn: int = 8
    conversation_history_limit: int = 12
    max_active_conversations: int = 50

    # Phase 5: Voice Interaction & Privacy Controls (Privacy-first: off by default)
    voice_enabled: bool = False
    stt_provider: str = Field(
        default_factory=lambda: os.environ.get("FRIDAY_STT_PROVIDER", "windows_sapi").strip().lower()
    )
    tts_provider: str = Field(
        default_factory=lambda: os.environ.get("FRIDAY_TTS_PROVIDER", "windows_sapi").strip().lower()
    )
    tts_voice_name: Optional[str] = Field(
        default_factory=lambda: os.environ.get("FRIDAY_TTS_VOICE")
    )
    stt_language: str = Field(
        default_factory=lambda: os.environ.get("FRIDAY_STT_LANGUAGE", "en-US").strip()
    )
    whisper_model_path: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("FRIDAY_WHISPER_MODEL", str(Path.home() / ".friday" / "models" / "faster-whisper-base.en"))
        ).resolve()
    )
    max_audio_duration_seconds: int = 30
    max_audio_size_bytes: int = 10 * 1024 * 1024  # 10 MB limit
    wake_word_active: bool = False  # Explicitly disabled and inactive


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Return the global Settings instance."""
    return settings


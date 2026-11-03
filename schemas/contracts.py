"""Typed Pydantic data contracts for W.E.D.N.E.S.D.A.Y. Milestone 1.

These contracts enforce clear boundaries between the model,
the capability broker, tool execution, and the verification layer.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PermissionType(str, Enum):
    """Granular permissions governed by the Capability Broker."""
    SYSTEM_TIME = "system:time"
    WORKSPACE_READ = "workspace:read"
    MEDIA_CONTROL = "media:control"
    LOCATION_READ = "location:read"
    LOCATION_CONTROL = "location:control"
    PLACES_SEARCH = "places:search"
    WORLD_READ = "world:read"


class LocationMode(str, Enum):
    """How the user has chosen to share this device's position."""
    OFF = "off"
    ONCE = "once"
    CONTINUOUS = "continuous"


class FixStatus(str, Enum):
    """Normalized status of a device location fix."""
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    ERROR = "error"
    DISABLED = "disabled"
    INITIALIZING = "initializing"


class WindowsLocationStatus(str, Enum):
    """Native Windows.Devices.Geolocation.LocationStatus values."""
    READY = "Ready"
    INITIALIZING = "Initializing"
    NO_DATA = "NoData"
    DISABLED = "Disabled"
    NOT_INITIALIZED = "NotInitialized"
    NOT_AVAILABLE = "NotAvailable"
    TIMEOUT = "Timeout"
    ERROR = "Error"


class DeviceLocationFix(BaseModel):
    """Structured device coordinates and provider telemetry."""
    latitude: Optional[float] = Field(default=None, description="WGS84 latitude in decimal degrees")
    longitude: Optional[float] = Field(default=None, description="WGS84 longitude in decimal degrees")
    accuracy_m: Optional[float] = Field(default=None, description="Horizontal accuracy radius in metres")
    timestamp_utc: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp of the fix")
    status: FixStatus = Field(default=FixStatus.DISABLED, description="Normalized fix status")
    windows_status: Optional[str] = Field(default=None, description="Raw Windows LocationStatus readout")
    provider: str = Field(default="Windows.Devices.Geolocation", description="Name of the underlying hardware/OS provider")
    is_stale: bool = Field(default=False, description="Whether fix exceeds configured staleness threshold")
    details: Optional[str] = Field(default=None, description="Diagnostic, error, or privacy note")


class GeocodedAddress(BaseModel):
    """Human-readable address and administrative components from reverse geocoding."""
    formatted_address: str = Field(..., description="Full formatted address string")
    street: Optional[str] = Field(default=None, description="Street name and number")
    locality: Optional[str] = Field(default=None, description="City, town, or locality")
    sublocality: Optional[str] = Field(default=None, description="Neighborhood or sublocality")
    admin_area: Optional[str] = Field(default=None, description="State, province, or region")
    country: Optional[str] = Field(default=None, description="Country name")
    postal_code: Optional[str] = Field(default=None, description="Postal or ZIP code")
    place_id: Optional[str] = Field(default=None, description="Google Maps Place ID if available")


class ReverseGeocodeResponse(BaseModel):
    """Response payload for reverse geocoding requests."""
    status: str = Field(..., description="Status: 'success', 'provider_not_configured', 'no_fix', or 'error'")
    latitude: Optional[float] = Field(default=None, description="Resolved latitude")
    longitude: Optional[float] = Field(default=None, description="Resolved longitude")
    address: Optional[GeocodedAddress] = Field(default=None, description="Resolved address details")
    provider: str = Field(default="GoogleMaps", description="Enrichment provider name")
    osm_uri: Optional[str] = Field(default=None, description="OpenStreetMap link if resolved via OSM")
    attribution: Optional[str] = Field(default=None, description="Attribution text e.g. '© OpenStreetMap contributors'")
    details: Optional[str] = Field(default=None, description="Diagnostic, error, or setup guidance")


class PlaceSummary(BaseModel):
    """Summary of a point of interest returned by nearby search."""
    id: str = Field(..., description="Unique place identifier")
    name: str = Field(..., description="Display name of the place")
    formatted_address: Optional[str] = Field(default=None, description="Human-readable address")
    latitude: float = Field(..., description="Place latitude")
    longitude: float = Field(..., description="Place longitude")
    types: List[str] = Field(default_factory=list, description="Place categories/types")
    rating: Optional[float] = Field(default=None, description="User rating if available")
    distance_m: Optional[float] = Field(default=None, description="Calculated distance in metres from query center")
    google_maps_uri: Optional[str] = Field(default=None, description="Official Google Maps link")
    osm_uri: Optional[str] = Field(default=None, description="OpenStreetMap link")
    attribution: Optional[str] = Field(default=None, description="Attribution text e.g. '© OpenStreetMap contributors'")


class NearbySearchResponse(BaseModel):
    """Response payload for nearby place searches."""
    status: str = Field(..., description="Status: 'success', 'provider_not_configured', 'no_fix', 'empty', or 'error'")
    query: Optional[str] = Field(default=None, description="Query string or keyword")
    category: Optional[str] = Field(default=None, description="Place category filter")
    center_lat: Optional[float] = Field(default=None, description="Search center latitude")
    center_lng: Optional[float] = Field(default=None, description="Search center longitude")
    radius_m: int = Field(default=1500, description="Search radius in metres")
    places: List[PlaceSummary] = Field(default_factory=list, description="Found points of interest")
    provider: str = Field(default="GoogleMaps", description="Places provider name")
    attribution: Optional[str] = Field(default=None, description="Attribution text e.g. '© OpenStreetMap contributors'")
    details: Optional[str] = Field(default=None, description="Diagnostic, error, or setup guidance")


class LocationServiceStatus(BaseModel):
    """Comprehensive state of the background location worker and latest fix."""
    mode: LocationMode = Field(default=LocationMode.ONCE, description="User-selected location mode")
    tracking_enabled: bool = Field(default=False, description="Whether background tracking is consented and enabled")
    is_paused: bool = Field(default=False, description="Whether location polling is temporarily paused")
    worker_running: bool = Field(default=False, description="Whether background daemon process is alive")
    worker_pid: Optional[int] = Field(default=None, description="Process ID of the background worker")
    update_interval_s: int = Field(default=60, description="Polling interval in seconds")
    latest_fix: Optional[DeviceLocationFix] = Field(default=None, description="Latest acquired location fix")
    details: Optional[str] = Field(default=None, description="Status commentary")



class ToolCallProposal(BaseModel):
    """A tool call proposed by an AI model.
    
    Treated as an unverified request until evaluated by the Capability Broker.
    """
    tool_name: str = Field(..., description="The name of the requested tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Raw arguments supplied by the model")


class PolicyDecision(BaseModel):
    """The capability broker's authorization verdict for a tool call proposal."""
    allowed: bool = Field(..., description="Whether the tool execution is permitted")
    reason: str = Field(..., description="Human-readable rationale for the decision")
    requires_approval: bool = Field(default=False, description="Whether explicit interactive user consent is needed")


class ToolExecutionResult(BaseModel):
    """The outcome of an authorized tool execution, including independent verification."""
    tool_name: str
    ok: bool
    output: Any = Field(default=None, description="The returned data or output detail")
    error: Optional[str] = Field(default=None, description="Error detail if execution failed")
    is_untrusted_content: bool = Field(
        default=True,
        description="Flag indicating output contains external/untrusted data"
    )
    verified: bool = Field(
        default=False,
        description="Whether an independent state check confirmed the expected effect"
    )
    verification_details: Optional[str] = Field(
        default=None,
        description="Explanation or evidence from independent state inspection"
    )


class SessionPolicy(BaseModel):
    """Active permissions and policies for the current session.
    
    The model cannot modify this object.
    """
    allowed_permissions: set[PermissionType] = Field(
        default_factory=lambda: {PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ}
    )
    media_control_enabled: bool = Field(
        default=False,
        description="Whether media control is allowed in this session"
    )
    location_read_enabled: bool = Field(
        default=False,
        description="Whether device location reading is allowed in this session"
    )
    location_control_enabled: bool = Field(
        default=False,
        description="Whether device location tracking start/pause/stop is allowed in this session"
    )
    places_search_enabled: bool = Field(
        default=False,
        description="Whether external places search and geocoding are allowed in this session"
    )
    world_read_enabled: bool = Field(
        default=True,
        description="Whether real-time world intelligence querying is allowed in this session"
    )
    allowed_workspace_root: str = Field(
        ...,
        description="Absolute path to the only authorized workspace directory"
    )


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """A message in the conversational history."""
    role: ChatRole
    content: str
    tool_name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class HealthResponse(BaseModel):
    """Status payload returned by the health endpoint."""
    status: str
    version: str
    model: str
    ollama_reachable: bool
    workspace_root: str
    media_control_enabled: bool
    location_read_enabled: bool = False
    location_tracking_enabled: bool = False
    places_search_enabled: bool = False
    world_read_enabled: bool = True


# ==============================================================================
# Phase 3: Real-Time World Intelligence Contracts
# ==============================================================================


class ProviderStatus(str, Enum):
    """Health/execution status of an external world intelligence provider."""
    OK = "ok"
    EMPTY = "empty"
    STALE = "stale"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    NOT_CONFIGURED = "not_configured"


class EarthquakeRecord(BaseModel):
    """Normalized USGS earthquake event record."""
    id: str = Field(..., description="Stable USGS event identifier")
    title: str = Field(..., description="Event title (e.g. 'M 4.5 - 12 km SSW of Volcano, Hawaii')")
    magnitude: float = Field(..., description="Earthquake magnitude")
    place: str = Field(..., description="Human-readable location description")
    latitude: float = Field(..., description="Epicenter latitude")
    longitude: float = Field(..., description="Epicenter longitude")
    depth_km: float = Field(..., description="Focal depth in kilometers")
    time_utc: str = Field(..., description="ISO-8601 UTC timestamp of occurrence")
    updated_utc: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp of last update")
    url: Optional[str] = Field(default=None, description="Official USGS event web page URL")
    tsunami_alert: bool = Field(default=False, description="Whether a tsunami alert flag was raised")
    felt_reports: Optional[int] = Field(default=None, description="Number of user felt reports submitted to USGS")
    alert_level: Optional[str] = Field(default=None, description="USGS PAGER alert level (green, yellow, orange, red)")


class EarthquakesResponse(BaseModel):
    """Response payload for recent earthquakes from USGS."""
    status: ProviderStatus = Field(..., description="Provider query status")
    count: int = Field(default=0, description="Number of earthquakes returned")
    earthquakes: List[EarthquakeRecord] = Field(default_factory=list, description="List of normalized earthquakes")
    provider: str = Field(default="USGS", description="Data provider name")
    attribution: str = Field(
        default="U.S. Geological Survey (USGS)",
        description="Data attribution"
    )
    retrieved_at: str = Field(..., description="ISO-8601 UTC timestamp of data retrieval")
    is_stale: bool = Field(default=False, description="True if response is served from stale/cached snapshot")
    details: Optional[str] = Field(default=None, description="Diagnostic, rate limit, or error detail")


class WeatherConditionRecord(BaseModel):
    """Normalized atmospheric weather telemetry from Open-Meteo."""
    latitude: float = Field(..., description="Observation latitude")
    longitude: float = Field(..., description="Observation longitude")
    location_name: Optional[str] = Field(default=None, description="Associated location or city label")
    temperature_c: float = Field(..., description="Current temperature in Celsius")
    feels_like_c: float = Field(..., description="Apparent / heat index temperature in Celsius")
    condition: str = Field(..., description="Human-readable WMO condition description")
    weather_code: int = Field(..., description="WMO weather code (0-99)")
    humidity_percent: float = Field(..., description="Relative humidity percentage")
    wind_speed_kmh: float = Field(..., description="Wind speed at 10m in km/h")
    wind_direction_deg: float = Field(..., description="Wind direction in degrees")
    precipitation_mm: float = Field(..., description="Current precipitation rate in mm")
    is_day: bool = Field(default=True, description="True if daytime at the given coordinates")
    forecast_summary: Optional[str] = Field(default=None, description="Short high/low forecast summary")
    daily_forecasts: List[Dict[str, Any]] = Field(default_factory=list, description="Next 3-day daily forecast snapshots")
    source_time_utc: str = Field(..., description="ISO-8601 model observation timestamp")


class WeatherResponse(BaseModel):
    """Response payload for current weather from Open-Meteo."""
    status: ProviderStatus = Field(..., description="Provider query status")
    weather: Optional[WeatherConditionRecord] = Field(default=None, description="Current weather conditions")
    provider: str = Field(default="Open-Meteo", description="Data provider name")
    attribution: str = Field(
        default="Weather data by Open-Meteo.com (CC BY 4.0)",
        description="Data attribution"
    )
    retrieved_at: str = Field(..., description="ISO-8601 UTC timestamp of retrieval")
    is_stale: bool = Field(default=False, description="True if response is served from stale/cached snapshot")
    details: Optional[str] = Field(default=None, description="Diagnostic, rate limit, or error detail")


class NaturalEventRecord(BaseModel):
    """Normalized natural event record from NASA EONET v3."""
    id: str = Field(..., description="NASA EONET event identifier (e.g. 'EONET_6432')")
    title: str = Field(..., description="Event title (e.g. 'Wildfire - Sierra National Forest')")
    category: str = Field(..., description="Category slug (e.g. 'wildfires', 'severeStorms')")
    category_title: str = Field(..., description="Human-readable category title")
    latitude: float = Field(..., description="Latest observed latitude")
    longitude: float = Field(..., description="Latest observed longitude")
    timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of latest observation")
    source_url: Optional[str] = Field(default=None, description="Primary source reference URL")
    description: Optional[str] = Field(default=None, description="Factual event description if supplied")
    geometry_type: str = Field(default="Point", description="Underlying geometry type (Point, Polygon)")
    is_closed: bool = Field(default=False, description="Whether event has been marked as closed")


class NaturalEventsResponse(BaseModel):
    """Response payload for natural events from NASA EONET."""
    status: ProviderStatus = Field(..., description="Provider query status")
    count: int = Field(default=0, description="Number of events returned")
    events: List[NaturalEventRecord] = Field(default_factory=list, description="List of natural events")
    provider: str = Field(default="NASA EONET v3", description="Data provider name")
    attribution: str = Field(
        default="NASA Earth Observatory Natural Event Tracker (EONET v3)",
        description="Data attribution"
    )
    retrieved_at: str = Field(..., description="ISO-8601 UTC timestamp of retrieval")
    is_stale: bool = Field(default=False, description="True if response is served from stale/cached snapshot")
    details: Optional[str] = Field(default=None, description="Diagnostic, rate limit, or error detail")


class DisasterRecord(BaseModel):
    """Normalized disaster alert record from GDACS."""
    id: str = Field(..., description="Stable disaster event identifier")
    title: str = Field(..., description="Disaster alert title")
    event_type: str = Field(..., description="Disaster code (e.g. 'EQ', 'TC', 'FL', 'VO', 'DR', 'WF')")
    alert_level: str = Field(..., description="GDACS alert level: 'Green', 'Orange', or 'Red'")
    severity: Optional[str] = Field(default=None, description="Source severity description or score")
    latitude: float = Field(..., description="Disaster epicenter or center latitude")
    longitude: float = Field(..., description="Disaster epicenter or center longitude")
    country: Optional[str] = Field(default=None, description="Affected country or region name")
    timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of disaster publication")
    url: Optional[str] = Field(default=None, description="Official GDACS report link")
    details: Optional[str] = Field(default=None, description="Disaster alert description")


class DisastersResponse(BaseModel):
    """Response payload for active disaster alerts from GDACS."""
    status: ProviderStatus = Field(..., description="Provider query status")
    count: int = Field(default=0, description="Number of disaster alerts returned")
    disasters: List[DisasterRecord] = Field(default_factory=list, description="List of active disaster alerts")
    provider: str = Field(default="GDACS", description="Data provider name")
    attribution: str = Field(
        default="Global Disaster Alert and Coordination System (GDACS)",
        description="Data attribution"
    )
    retrieved_at: str = Field(..., description="ISO-8601 UTC timestamp of retrieval")
    is_stale: bool = Field(default=False, description="True if response is served from stale/cached snapshot")
    details: Optional[str] = Field(default=None, description="Diagnostic, rate limit, or error detail")


class NewsArticleRecord(BaseModel):
    """Normalized news article from an allowlisted RSS feed."""
    id: str = Field(..., description="Stable article identifier or URL hash")
    title: str = Field(..., description="Article headline")
    publisher: str = Field(..., description="Allowlisted publisher name")
    url: str = Field(..., description="Original article canonical URL")
    published_at_utc: str = Field(..., description="ISO-8601 publication timestamp")
    summary: Optional[str] = Field(default=None, description="Short factual headline summary")


class NewsResponse(BaseModel):
    """Response payload for recent world news articles."""
    status: ProviderStatus = Field(..., description="Provider query status")
    count: int = Field(default=0, description="Number of news articles returned")
    articles: List[NewsArticleRecord] = Field(default_factory=list, description="List of news articles")
    provider: str = Field(default="Verified RSS Feeds", description="Data provider name")
    attribution: str = Field(default="Respective publishers", description="Data attribution")
    retrieved_at: str = Field(..., description="ISO-8601 UTC timestamp of retrieval")
    is_stale: bool = Field(default=False, description="True if response is served from stale/cached snapshot")
    details: Optional[str] = Field(default=None, description="Diagnostic or error detail")


class ProviderHealth(BaseModel):
    """Health, freshness, and cache telemetry for an individual provider."""
    provider: str = Field(..., description="Provider name")
    status: ProviderStatus = Field(..., description="Current operational status")
    last_successful_retrieval: Optional[str] = Field(default=None, description="ISO timestamp of last successful fetch")
    is_stale: bool = Field(default=False, description="Whether currently held data is past its freshness TTL")
    cached_items_count: int = Field(default=0, description="Number of items held in in-memory cache")
    error_message: Optional[str] = Field(default=None, description="Last recorded error if unavailable")


class WorldStatusResponse(BaseModel):
    """Aggregated health and freshness status across all world intelligence providers."""
    status: str = Field(..., description="Overall status: 'healthy', 'degraded', or 'offline'")
    providers: Dict[str, ProviderHealth] = Field(default_factory=dict, description="Per-provider health status")
    retrieved_at: str = Field(..., description="ISO-8601 UTC timestamp of status evaluation")


class _WorldFeedEnvelope(BaseModel):
    """Common provenance fields for world feeds."""
    status: ProviderStatus = Field(..., description="Provider query status")
    provider: str = Field(..., description="Data provider name")
    attribution: str = Field(..., description="Data attribution")
    retrieved_at: str = Field(..., description="ISO-8601 UTC time the upstream data was retrieved")
    is_stale: bool = Field(default=False, description="True if served from an expired snapshot")
    details: Optional[str] = Field(default=None, description="Diagnostic or error detail")


class SatelliteRecord(BaseModel):
    """A satellite position propagated with SGP4 from CelesTrak orbital elements."""
    norad_id: int
    name: str
    group: str = Field(..., description="CelesTrak group the object was listed in")
    latitude: float
    longitude: float
    altitude_km: float
    velocity_kms: float
    inclination_deg: float
    period_min: float
    orbit_class: str = Field(..., description="LEO, MEO, GEO or HEO, from altitude and eccentricity")
    elements_epoch_utc: str = Field(..., description="Epoch of the orbital elements used")


class SatellitesResponse(_WorldFeedEnvelope):
    count: int = 0
    satellites: List[SatelliteRecord] = Field(default_factory=list)
    positions_at: str = Field(..., description="ISO-8601 UTC instant the positions were computed for")


class SatelliteTrackResponse(_WorldFeedEnvelope):
    norad_id: int
    name: Optional[str] = None
    points: List[List[float]] = Field(default_factory=list, description="[lat, lng, altitude_km] samples")
    start_utc: Optional[str] = None
    end_utc: Optional[str] = None


class FlightRecord(BaseModel):
    """An aircraft position decoded from ADS-B/MLAT by the adsb.lol community network."""
    hex: str = Field(..., description="ICAO 24-bit transponder address")
    callsign: Optional[str] = None
    registration: Optional[str] = None
    aircraft_type: Optional[str] = None
    latitude: float
    longitude: float
    altitude_ft: Optional[int] = Field(default=None, description="Barometric altitude; None when on the ground or unknown")
    on_ground: bool = False
    ground_speed_kt: Optional[float] = None
    track_deg: Optional[float] = None
    vertical_rate_fpm: Optional[int] = None
    squawk: Optional[str] = None
    emergency: Optional[str] = None
    position_source: Optional[str] = Field(default=None, description="adsb_icao, mlat, tisb, ...")
    position_age_s: Optional[float] = None


class FlightsResponse(_WorldFeedEnvelope):
    count: int = 0
    flights: List[FlightRecord] = Field(default_factory=list)
    center_lat: float
    center_lng: float
    radius_nm: int


class LaunchRecord(BaseModel):
    """An upcoming orbital launch from The Space Devs' Launch Library 2."""
    id: str
    name: str
    net_utc: Optional[str] = Field(default=None, description="No-earlier-than launch time")
    net_precision: Optional[str] = None
    window_start_utc: Optional[str] = None
    window_end_utc: Optional[str] = None
    status: Optional[str] = None
    status_abbrev: Optional[str] = None
    provider_name: Optional[str] = None
    rocket: Optional[str] = None
    mission_name: Optional[str] = None
    mission_description: Optional[str] = None
    orbit: Optional[str] = None
    pad_name: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    probability: Optional[int] = Field(default=None, description="Weather/go probability percent, if published")
    webcast_live: bool = False
    url: Optional[str] = None


class LaunchesResponse(_WorldFeedEnvelope):
    count: int = 0
    launches: List[LaunchRecord] = Field(default_factory=list)


class FireRecord(BaseModel):
    """A satellite-detected thermal anomaly (active fire) from NASA FIRMS."""
    latitude: float
    longitude: float
    brightness_k: Optional[float] = None
    frp_mw: Optional[float] = Field(default=None, description="Fire radiative power in megawatts")
    confidence: Optional[str] = None
    acquired_utc: Optional[str] = None
    satellite: Optional[str] = None
    daynight: Optional[str] = None


class FiresResponse(_WorldFeedEnvelope):
    count: int = 0
    total_detections: int = 0
    fires: List[FireRecord] = Field(default_factory=list)


# ==============================================================================
# Phase 4: Conversational Intelligence & Safe Tool Orchestration Contracts
# ==============================================================================


class SourceReference(BaseModel):
    """Verifiable source provenance attached to a conversational claim."""
    title: str = Field(..., description="Name or title of the source record")
    url: Optional[str] = Field(default=None, description="Original canonical URL where available")
    publisher: Optional[str] = Field(default=None, description="Provider or publisher name")
    retrieved_at_utc: Optional[str] = Field(default=None, description="Timestamp when data was retrieved")
    is_stale: bool = Field(default=False, description="True if source data was served from stale cache")
    details: Optional[str] = Field(default=None, description="Relevant factual snippet or observation date")

    @property
    def provider(self) -> Optional[str]:
        return self.publisher



class ToolExecutionSummary(BaseModel):
    """Summary of a tool execution attempted during conversational reasoning."""
    tool_name: str = Field(..., description="Name of the tool executed")
    ok: bool = Field(..., description="Whether tool execution succeeded")
    verified: bool = Field(default=False, description="Whether tool output was independently verified")
    allowed: bool = Field(default=True, description="Whether tool was authorized by Capability Broker")
    error: Optional[str] = Field(default=None, description="Error or rejection reason if unsuccessful")
    details: Optional[str] = Field(default=None, description="Summary or commentary")



class ConversationRequest(BaseModel):
    """Inbound conversational turn request from the user."""
    message: str = Field(..., min_length=1, max_length=4000, description="User conversational prompt")
    conversation_id: Optional[str] = Field(default=None, description="Optional stable conversation session ID")
    request_id: Optional[str] = Field(default=None, description="Optional client request ID for retry correlation")


class ConversationResponse(BaseModel):
    """Structured assistant response grounded in verified tool outputs."""
    response: str = Field(..., description="Assistant answer text")
    model: str = Field(..., description="Name of the model that produced the answer")
    conversation_id: Optional[str] = Field(default=None, description="Conversation session ID")
    request_id: Optional[str] = Field(default=None, description="Client request ID if supplied")
    sources: List[SourceReference] = Field(default_factory=list, description="Verifiable sources cited in answer")
    tool_calls: List[ToolExecutionSummary] = Field(default_factory=list, description="Tool actions taken")
    status: str = Field(default="ok", description="Status: 'ok', 'ollama_unavailable', 'turn_limit_reached', 'cancelled', or 'error'")
    error: Optional[str] = Field(default=None, description="Error detail if status is not ok")
    approvals: List["PendingApproval"] = Field(default_factory=list, description="Actions awaiting the user's explicit approval")


class PendingApproval(BaseModel):
    """A denied side-effecting call that the user may approve once, for these exact arguments."""
    approval_id: str
    conversation_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Exact arguments that will run if approved")
    args_digest: str
    reason: str
    status: str = Field(..., description="pending, executing, succeeded, failed, outcome_unknown, denied, or expired")
    created_at: str
    expires_at: str
    result: Optional[Dict[str, Any]] = None


class ConversationResetRequest(BaseModel):
    """Request to clear conversation history."""
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID to reset; None resets default")


class ConversationResetResponse(BaseModel):
    """Confirmation of conversation history reset."""
    status: str = Field(default="ok", description="Status code")
    conversation_id: Optional[str] = Field(default=None, description="Reset conversation ID")
    message: str = Field(default="Conversation history cleared", description="Human-readable detail")


# ==============================================================================
# Phase 5: Privacy-First Local Voice Interaction Contracts
# ==============================================================================


class VoiceStateEnum(str, Enum):
    """Visual and operational states of the local voice pipeline."""
    DISABLED = "DISABLED"
    STANDBY = "STANDBY"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"


class STTTranscriptionRequest(BaseModel):
    """Audio payload submitted for offline local speech-to-text."""
    audio_base64: str = Field(..., description="Base64-encoded audio bytes (WAV or WebM format)")
    audio_format: str = Field(default="wav", description="Audio format: 'wav', 'webm', or 'ogg'")
    sample_rate_hz: int = Field(default=16000, description="Audio sample rate in Hz")
    engine: Optional[str] = Field(default=None, description="Local engine to use ('windows_sapi' or 'faster_whisper'); None uses the configured default")


class STTTranscriptionResponse(BaseModel):
    """Result of offline local speech recognition."""
    status: str = Field(..., description="Status: 'ok', 'empty_transcript', 'model_not_installed', 'transcription_error', or 'format_unsupported'")
    transcript: str = Field(default="", description="Transcribed user utterance")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration in seconds")
    details: Optional[str] = Field(default=None, description="Diagnostic commentary")
    detected_sample_rate: Optional[int] = Field(default=None, description="Measured audio sample rate in Hz")
    detected_channels: Optional[int] = Field(default=None, description="Measured channel count")
    audio_size_bytes: Optional[int] = Field(default=None, description="Payload size in bytes")
    confidence: Optional[float] = Field(default=None, description="Recognizer confidence score if available")
    engine: Optional[str] = Field(default=None, description="Name of recognizer engine used")
    peak_amplitude: Optional[float] = Field(default=None, description="Peak audio signal level (0.0 to 1.0)")
    rms_amplitude: Optional[float] = Field(default=None, description="RMS audio signal level (0.0 to 1.0)")
    silent_samples_ratio: Optional[float] = Field(default=None, description="Ratio of silent samples (< -45 dBFS)")
    audio_samples_count: Optional[int] = Field(default=None, description="Total PCM samples in recording")
    clipped_ratio: Optional[float] = Field(default=None, description="Ratio of samples at or near full scale (clipping)")
    speech_duration_seconds: Optional[float] = Field(default=None, description="Duration after trimming leading/trailing silence")
    segment_count: Optional[int] = Field(default=None, description="Number of recognized phrases joined into the transcript")
    latency_ms: Optional[int] = Field(default=None, description="Server-side recognition time in milliseconds")


class TTSSynthesisRequest(BaseModel):
    """Text submitted for offline local text-to-speech synthesis."""
    text: str = Field(..., min_length=1, max_length=2000, description="Text to synthesize into spoken audio")
    voice_name: Optional[str] = Field(default=None, description="Specific local voice profile name")


class TTSSynthesisResponse(BaseModel):
    """Result of offline local speech synthesis."""
    status: str = Field(..., description="Status: 'ok', 'model_not_installed', 'disabled', or 'error'")
    audio_base64: Optional[str] = Field(default=None, description="Base64-encoded WAV audio bytes")
    audio_format: str = Field(default="wav", description="Synthesized audio format")
    duration_seconds: Optional[float] = Field(default=None, description="Synthesized duration in seconds")
    details: Optional[str] = Field(default=None, description="Diagnostic commentary")


class VoiceConfigResponse(BaseModel):
    """Configuration, privacy posture, and available local speech engines."""
    voice_enabled: bool = Field(default=False, description="Whether voice subsystem is enabled (defaults to False)")
    stt_available: bool = Field(default=True, description="Whether a local STT engine is detected")
    tts_available: bool = Field(default=True, description="Whether a local TTS engine is detected")
    stt_engine: str = Field(default="Windows.Speech.Recognition", description="Active offline STT provider")
    tts_engine: str = Field(default="Windows.Speech.Synthesis", description="Active offline TTS provider")
    available_voices: List[str] = Field(default_factory=list, description="Installed local system voices")
    available_stt_engines: List[str] = Field(default_factory=lambda: ["windows_sapi"], description="Available local STT providers")
    installed_speech_packs: List[str] = Field(default_factory=list, description="Installed speech recognition packs")
    wake_word_active: bool = Field(default=False, description="Strictly False: wake phrase listening is dormant")


class VoicePrivacyRequest(BaseModel):
    """User command to alter voice mode or trigger emergency stop."""
    action: str = Field(..., description="Action: 'enable', 'disable', or 'stop_playback'")


class VoicePrivacyResponse(BaseModel):
    """Acknowledgment of voice privacy update."""
    status: str = Field(..., description="Status code: 'ok' or 'error'")
    voice_enabled: bool = Field(..., description="Current voice enablement state")
    current_state: VoiceStateEnum = Field(..., description="Current voice state")
    details: str = Field(..., description="Action summary")

ConversationResponse.model_rebuild()

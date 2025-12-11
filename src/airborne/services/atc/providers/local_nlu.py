"""Local NLU provider using llama-cpp-python with rule-based pre-matching.

This module provides intent extraction from transcribed pilot speech using:
1. Fast rule-based pattern matching (JSON rules file)
2. Local Llama model fallback via llama-cpp-python

The hybrid approach provides ~0ms latency for common patterns while
using the LLM for complex/ambiguous cases.

Typical usage:
    nlu = LocalNLUProvider()
    nlu.initialize({"model_path": "/path/to/llama-3.2-3B.gguf"})

    intent = nlu.extract_intent("november one two three four request taxi")
    print(f"Intent: {intent.intent_type}, Callsign: {intent.callsign}")
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from airborne.services.atc.providers.base import ATCIntent, ATCIntentType, INLUProvider

logger = logging.getLogger(__name__)

# Path to rules file
RULES_FILE = Path(__file__).parent.parent / "nlu_rules.json"

# Slot extraction patterns (used for both rule-based and LLM results)
SLOT_PATTERNS = {
    "callsign": re.compile(
        r"\b([A-Z]-[A-Z]{4}|[NF]-[A-Z]{4}|"  # F-GXYZ, N-12345
        r"[A-Z]{2,3}\d{1,4}[A-Z]?|"  # AF1418, SK202, UAL123A
        r"(?:november|november)\s*\d[\s\d]*|"  # November 123
        r"(?:cessna|piper|beech|cirrus|diamond)\s*\d+|"  # Cessna 456
        r"[A-Z]{1,2}\d{3,5}[A-Z]{0,2})\b",  # N123AB
        re.IGNORECASE,
    ),
    "runway": re.compile(
        r"(?:runway|piste|rwy)\s*(\d{1,2}[LRC]?(?:\s*(?:left|right|center|gauche|droite))?)",
        re.IGNORECASE,
    ),
    "taxiway": re.compile(
        r"(?:taxiway|via|TWY)\s*([A-Z](?:\d)?)",
        re.IGNORECASE,
    ),
    "altitude": re.compile(
        r"(?:flight level|FL|niveau)\s*(\d{2,3})|"
        r"(\d{3,5})\s*(?:feet|pieds|ft)?",
        re.IGNORECASE,
    ),
    "heading": re.compile(
        r"(?:heading|cap)\s*(\d{3})|"
        r"(?:turn|virage).*?(\d{3})",
        re.IGNORECASE,
    ),
    "frequency": re.compile(
        r"(\d{2,3}[.,]\d{1,3})",
        re.IGNORECASE,
    ),
}

# Try to import llama-cpp-python
# Note: The import itself can fail with FileNotFoundError if the native library is missing
LLAMA_CPP_AVAILABLE = False
Llama = None  # type: ignore[assignment,misc]

try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    pass  # Library not installed
except (OSError, FileNotFoundError) as e:
    # Native library missing (common in bundled apps)
    logger.warning(f"llama-cpp native library not found: {e}")


# System prompt for ATC intent extraction - kept compact to fit context window
SYSTEM_PROMPT = """ATC intent parser. Extract ONLY explicitly stated info. EN/FR.

RULES: 1) Only extract what's said 2) Unmentioned=null 3) Garbled/unclear→unknown,0.2

INTENT KEYWORDS (use exact match):
GROUND: "sol/ground+bonjour/hello"→initial_contact | "request taxi/demande roulage/ready to taxi"→request_taxi | "pushback/refoulement"→request_pushback | "holding short/maintien avant piste"→report_holding_short | "request ATIS/information"→request_atis | "clearance/clairance"→request_clearance | "radio check/how do you read/essai radio"→request_radio_check

TOWER: "ready for departure/prêt départ/ready to go/number one"→ready_for_departure | "immediate departure/immediate takeoff"→request_immediate_takeoff | "request takeoff"→request_takeoff | "request landing/full stop/inbound for landing"→request_landing | "touch and go/posé décollé"→request_touch_and_go | "option"→request_option | "closed traffic/reste circuit"→request_closed_traffic

PATTERN: "crosswind/vent traversier"→report_crosswind | "downwind/vent arrière"→report_downwind | "midfield downwind"→report_midfield_downwind | "base/turning base/étape de base/en base"→report_base | "final/finale"→report_final | "short final/courte finale"→report_short_final | "go around/going around/remise de gaz/on remet les gaz"→request_go_around | "clear of runway/off the runway/piste dégagée/piste libre/runway vacated"→report_clear_of_runway

APPROACH: "approche ILS/ILS approach"→request_ils_approach | "visual approach/approche à vue"→request_visual_approach | "RNAV"→request_rnav_approach | "VOR approach"→request_vor_approach | "established/établi"→report_established | "field in sight/airport in sight/terrain en vue"→report_field_in_sight

ENROUTE: "flight following/VFR advisories"→request_flight_following | "request flight level/request altitude/request level/requesting higher/requesting lower/demande niveau/demande altitude"→request_altitude_change | "level flight level/level at/stabilisé niveau/niveau atteint"→report_level | "leaving X for Y/passant niveau/climbing through/descending through"→report_leaving | "reaching/niveau atteint"→report_reaching | "request heading/demande cap"→request_heading | "request direct"→request_direct

TRAFFIC: "traffic in sight/trafic en vue"→report_traffic_in_sight | "negative traffic/no contact/looking for traffic/cherche le trafic"→negative_traffic

EMERGENCY: "mayday/pan pan"→declare_emergency

ACK (single words): "roger/reçu"→roger | "wilco/will comply/compris"→wilco | "affirm/affirmatif"→affirm | "negative/négatif"→negative | "unable/impossible"→unable | "say again/répétez"→say_again | "standby/attendez"→standby

READBACK (pilot confirms ATC clearance - NOT requests): "taxi to runway X via Y"→readback_taxi | "hold short runway X/maintien avant piste"→readback_hold_short | "cleared for takeoff/autorisé décollage/cleared takeoff"→readback_departure | "cleared to land/cleared land/autorisé atterrissage"→readback_landing | "climb/descend/maintain/climbing/descending/montée/descente"→readback_altitude | "heading X/turn X/cap X/virage"→readback_heading | "contact X.X/frequency X.X/tower X.X/departure X.X/approach X.X/contacter"→readback_frequency

Output JSON: intent, confidence(0-1), callsign, runway, taxiway, altitude, heading, frequency, position, hold_short"""

USER_PROMPT_TEMPLATE = """"{text}"
JSON:"""

# All valid intent values - must match ATCIntentType enum
VALID_INTENTS = [
    # Pre-flight / Clearance
    "request_atis",
    "request_clearance",
    "request_startup",
    # Ground operations
    "request_taxi",
    "request_pushback",
    "report_ready_for_taxi",
    "request_taxi_to_runway",
    "request_taxi_to_parking",
    "report_holding_short",
    # Tower / Traffic pattern
    "ready_for_departure",
    "request_takeoff",
    "request_immediate_takeoff",
    "request_intersection_departure",
    "request_landing",
    "report_crosswind",
    "report_downwind",
    "report_midfield_downwind",
    "report_base",
    "report_final",
    "report_short_final",
    "request_go_around",
    "request_touch_and_go",
    "request_stop_and_go",
    "request_low_approach",
    "request_option",
    "request_closed_traffic",
    "report_clear_of_runway",
    # Departure
    "request_departure_frequency",
    "report_airborne",
    "report_leaving",
    "request_flight_following",
    # Approach
    "request_approach",
    "request_ils_approach",
    "request_visual_approach",
    "request_rnav_approach",
    "request_vor_approach",
    "report_field_in_sight",
    "report_established",
    "cancel_ifr",
    # En-route
    "request_altitude_change",
    "request_heading",
    "request_speed_change",
    "request_direct",
    "request_deviation",
    "report_position",
    "report_level",
    "report_reaching",
    # Traffic
    "report_traffic_in_sight",
    "negative_traffic",
    # Emergency
    "declare_emergency",
    "cancel_emergency",
    # Contact / Frequency
    "initial_contact",
    "request_frequency_change",
    "request_radio_check",
    # Readback/Collation
    "readback",
    "readback_taxi",
    "readback_departure",
    "readback_landing",
    "readback_altitude",
    "readback_heading",
    "readback_frequency",
    "readback_hold_short",
    # Acknowledgements
    "roger",
    "wilco",
    "affirm",
    "negative",
    "unable",
    "say_again",
    "standby",
    # Unknown
    "unknown",
]

# JSON schema for structured output
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": VALID_INTENTS,
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "callsign": {"type": ["string", "null"]},
        "runway": {"type": ["string", "null"]},
        "taxiway": {"type": ["string", "null"]},
        "altitude": {"type": ["integer", "null"]},
        "heading": {"type": ["integer", "null"]},
        "frequency": {"type": ["string", "null"]},
        "position": {"type": ["string", "null"]},
        "destination": {"type": ["string", "null"]},
        "hold_short": {"type": ["string", "null"]},
    },
    "required": ["intent", "confidence"],
}


class LocalNLUProvider(INLUProvider):
    """Local NLU provider with rule-based pre-matching and LLM fallback.

    This provider uses a hybrid approach:
    1. Fast rule-based pattern matching (~0ms) for common patterns
    2. Local Llama model fallback for complex/ambiguous cases (~2s)

    It works offline with GGUF model files.
    """

    def __init__(self) -> None:
        """Initialize the local NLU provider."""
        self._model: Any = None
        self._model_path: str = ""
        self._n_ctx: int = 2048
        self._n_threads: int = 4
        self._initialized = False
        self._rules: list[dict[str, Any]] = []
        self._rules_loaded = False

    def _load_rules(self) -> None:
        """Load NLU rules from JSON file."""
        if self._rules_loaded:
            return

        try:
            if RULES_FILE.exists():
                with open(RULES_FILE) as f:
                    data = json.load(f)
                    self._rules = data.get("rules", [])
                    # Pre-compile regex patterns
                    for rule in self._rules:
                        if rule.get("regex"):
                            for lang, patterns in rule.get("patterns", {}).items():
                                rule["patterns"][lang] = [
                                    re.compile(p, re.IGNORECASE) for p in patterns
                                ]
                    self._rules_loaded = True
                    logger.info(f"Loaded {len(self._rules)} NLU rules")
            else:
                logger.warning(f"NLU rules file not found: {RULES_FILE}")
        except Exception as e:
            logger.error(f"Failed to load NLU rules: {e}")

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the NLU provider with configuration.

        Args:
            config: Configuration dictionary with keys:
                - model_path: Path to GGUF model file (required)
                - n_ctx: Context size (default: 2048)
                - n_threads: Number of CPU threads (default: 4)
                - n_gpu_layers: GPU layers to offload (default: 0)

        Raises:
            ImportError: If llama-cpp-python is not installed.
            ValueError: If model_path is not provided.
            RuntimeError: If model loading fails.
        """
        # Load rules first (fast, no dependencies)
        self._load_rules()

        if not LLAMA_CPP_AVAILABLE:
            raise ImportError(
                "llama-cpp-python is required for local NLU. Install with: uv add llama-cpp-python"
            )

        self._model_path = config.get("model_path", "")
        if not self._model_path:
            raise ValueError("model_path is required for LocalNLUProvider")

        self._n_ctx = config.get("n_ctx", 2048)
        self._n_threads = config.get("n_threads", 4)
        n_gpu_layers = config.get("n_gpu_layers", 0)

        logger.info(f"Loading Llama model from '{self._model_path}'...")

        try:
            self._model = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self._initialized = True
            logger.info("Llama model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Llama model: {e}")
            raise RuntimeError(f"Failed to load Llama model: {e}") from e

    def _detect_language(self, text: str) -> str:
        """Detect language from text (simple heuristic).

        Args:
            text: Input text.

        Returns:
            'fr' for French, 'en' for English.
        """
        french_markers = [
            "bonjour",
            "sol",
            "piste",
            "roulage",
            "demande",
            "maintien",
            "décollage",
            "atterrissage",
            "niveau",
            "approche",
            "reçu",
            "compris",
            "négatif",
            "affirmatif",
            "gauche",
            "droite",
            "vent arrière",
            "étape de base",
            "finale",
            "autorisé",
            "terrain",
            "établi",
            "trafic",
            "remise de gaz",
            "posé",
        ]
        text_lower = text.lower()
        for marker in french_markers:
            if marker in text_lower:
                return "fr"
        return "en"

    def _match_rules(self, text: str) -> ATCIntent | None:
        """Try to match text against pre-defined rules.

        Args:
            text: Input text.

        Returns:
            ATCIntent if matched, None otherwise.
        """
        if not self._rules:
            return None

        text_lower = text.lower().strip()
        lang = self._detect_language(text)

        for rule in self._rules:
            patterns = rule.get("patterns", {})
            lang_patterns = patterns.get(lang, []) + patterns.get("en", [])  # Fallback to EN

            is_regex = rule.get("regex", False)
            is_exact = rule.get("exact_match", False)

            for pattern in lang_patterns:
                matched = False

                if is_regex:
                    # Pattern is pre-compiled regex
                    if pattern.search(text_lower):
                        matched = True
                elif is_exact:
                    # Exact match (for single-word acknowledgements)
                    if text_lower == pattern.lower():
                        matched = True
                else:
                    # Substring match
                    if pattern.lower() in text_lower:
                        matched = True

                if matched:
                    intent_str = rule.get("intent", "unknown")
                    confidence = rule.get("confidence", 0.9)

                    try:
                        intent_type = ATCIntentType(intent_str)
                    except ValueError:
                        logger.warning(f"Unknown intent in rules: {intent_str}")
                        continue

                    # Extract slots using regex patterns
                    slots = self._extract_slots(text)

                    logger.info(f"Rule match: '{pattern}' -> {intent_str} (conf={confidence})")

                    return ATCIntent(
                        intent_type=intent_type,
                        confidence=confidence,
                        raw_text=text,
                        **slots,
                    )

        return None

    def _extract_slots(self, text: str) -> dict[str, Any]:
        """Extract slot values from text using regex.

        Args:
            text: Input text.

        Returns:
            Dictionary of extracted slots.
        """
        slots: dict[str, Any] = {}

        # Callsign
        match = SLOT_PATTERNS["callsign"].search(text)
        if match:
            slots["callsign"] = match.group(0).upper()

        # Runway
        match = SLOT_PATTERNS["runway"].search(text)
        if match:
            slots["runway"] = match.group(1).upper()

        # Taxiway
        match = SLOT_PATTERNS["taxiway"].search(text)
        if match:
            slots["taxiway"] = match.group(1).upper()

        # Altitude (could be FL or feet)
        match = SLOT_PATTERNS["altitude"].search(text)
        if match:
            val = match.group(1) or match.group(2)
            if val:
                slots["altitude"] = int(val)

        # Heading
        match = SLOT_PATTERNS["heading"].search(text)
        if match:
            val = match.group(1) or match.group(2)
            if val:
                slots["heading"] = int(val)

        # Frequency
        match = SLOT_PATTERNS["frequency"].search(text)
        if match:
            slots["frequency"] = match.group(1).replace(",", ".")

        return slots

    def extract_intent(self, text: str, context: dict[str, Any] | None = None) -> ATCIntent:
        """Extract structured intent from transcribed text.

        Uses a hybrid approach:
        1. Try fast rule-based matching first
        2. Fall back to LLM for complex cases

        Args:
            text: Transcribed pilot speech (any language).
            context: Optional flight context (not currently used).

        Returns:
            ATCIntent with extracted slots and confidence.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to NLU")
            return ATCIntent(raw_text=text)

        # 1. Try rule-based matching first (fast path)
        rule_result = self._match_rules(text)
        if rule_result is not None:
            return rule_result

        # 2. Fall back to LLM (slow path)
        if not self._initialized or not self._model:
            logger.error("NLU provider not initialized, no rule match")
            return ATCIntent(raw_text=text)

        try:
            # Build the prompt
            user_prompt = USER_PROMPT_TEMPLATE.format(text=text.strip())

            # Generate response with JSON grammar enforcement
            response = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=256,
                temperature=0.1,  # Low temperature for consistent output
                response_format={
                    "type": "json_object",
                    "schema": JSON_SCHEMA,
                },
            )

            # Extract the generated text
            generated = response["choices"][0]["message"]["content"].strip()
            logger.info(f"NLU LLM response: {generated}")

            # Parse JSON from response
            intent = self._parse_json_response(generated, text)
            return intent

        except Exception as e:
            logger.error(f"Intent extraction failed: {e}", exc_info=True)
            return ATCIntent(raw_text=text)

    def _parse_json_response(self, response: str, original_text: str) -> ATCIntent:
        """Parse JSON response from the model.

        Args:
            response: Raw model output.
            original_text: Original transcribed text.

        Returns:
            Parsed ATCIntent.
        """
        # Try to extract JSON from the response
        json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
        if not json_match:
            logger.warning(f"No JSON found in NLU response: {response}")
            return ATCIntent(raw_text=original_text)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in NLU response: {e}")
            return ATCIntent(raw_text=original_text)

        # Map intent string to enum
        intent_str = data.get("intent", "unknown")
        try:
            intent_type = ATCIntentType(intent_str)
        except ValueError:
            logger.warning(f"Unknown intent type: {intent_str}")
            intent_type = ATCIntentType.UNKNOWN

        return ATCIntent(
            intent_type=intent_type,
            confidence=float(data.get("confidence", 0.0)),
            callsign=data.get("callsign"),
            runway=data.get("runway"),
            taxiway=data.get("taxiway"),
            altitude=self._parse_int(data.get("altitude")),
            heading=self._parse_int(data.get("heading")),
            frequency=data.get("frequency"),
            position=data.get("position"),
            destination=data.get("destination"),
            hold_short=data.get("hold_short"),
            raw_text=original_text,
        )

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        """Safely parse an integer value.

        Args:
            value: Value to parse.

        Returns:
            Integer or None.
        """
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def is_available(self) -> bool:
        """Check if the provider is ready for use.

        Returns:
            True if the model is loaded and ready.
        """
        return self._initialized and self._model is not None

    def shutdown(self) -> None:
        """Release provider resources."""
        if self._model is not None:
            # llama-cpp models are garbage collected
            self._model = None
            self._initialized = False
            logger.info("Local NLU provider shutdown")

    @property
    def name(self) -> str:
        """Get provider name."""
        model_name = self._model_path.split("/")[-1] if self._model_path else "unknown"
        return f"LocalNLU(llama-cpp/{model_name})"

    @staticmethod
    def is_library_available() -> bool:
        """Check if llama-cpp-python library is installed.

        Returns:
            True if llama-cpp-python is available.
        """
        return LLAMA_CPP_AVAILABLE

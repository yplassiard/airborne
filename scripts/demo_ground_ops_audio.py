"""Audio demonstration script for ground operations workflow.

This script plays the complete ground-to-takeoff workflow using the actual
audio system with appropriate voice effects (ATC radio, cockpit, etc.).
"""

import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pygame

from airborne.audio.engine.fmod_engine import FMODEngine
from airborne.audio.tts.audio_provider import AudioSpeechProvider
from airborne.plugins.radio.atis import ATISGenerator, ATISInfo, WeatherInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class GroundOpsAudioDemo:
    """Complete ground operations demonstration with audio."""

    def __init__(self, airport_icao: str = "KPAO", parking_id: str = "parking_3") -> None:
        """Initialize demo.

        Args:
            airport_icao: Airport ICAO code (default: KPAO - Palo Alto)
            parking_id: Starting parking position
        """
        self.airport_icao = airport_icao
        self.parking_id = parking_id

        # Initialize pygame for event loop
        pygame.init()

        # Initialize audio engine
        logger.info("Initializing FMOD audio engine...")
        self.audio_engine = FMODEngine()

        # Initialize TTS
        logger.info("Initializing TTS system...")
        self.tts = AudioSpeechProvider()
        self.tts.initialize(
            {
                "language": "en",
                "audio_engine": self.audio_engine,
                "speech_dir": "data/speech",
                "config_dir": "config",
            }
        )

        # Initialize ATIS generator
        self.atis_generator = ATISGenerator()

        # Aircraft state
        self.aircraft_id = "N123AB"
        self.aircraft_type = "C172"
        self.destination_runway = "31"

        # Current ATIS
        self.current_atis: ATISInfo | None = None

        logger.info("=" * 80)
        logger.info("AirBorne Ground Operations Audio Demo")
        logger.info("=" * 80)
        logger.info("Airport: %s", self.airport_icao)
        logger.info("Aircraft: %s (%s)", self.aircraft_id, self.aircraft_type)
        logger.info("Parking: %s", self.parking_id)
        logger.info("=" * 80)

    def run(self) -> None:
        """Run the complete demonstration."""
        try:
            self.phase_1_cold_and_dark()
            time.sleep(3)

            self.phase_2_preflight()
            time.sleep(3)

            self.phase_3_engine_start()
            time.sleep(3)

            self.phase_4_atc_clearance()
            time.sleep(3)

            self.phase_5_taxi()
            time.sleep(3)

            self.phase_6_runway_entry()
            time.sleep(3)

            self.phase_7_takeoff()

            logger.info("=" * 80)
            logger.info("Ground Operations Demo Complete!")
            logger.info("=" * 80)

        except KeyboardInterrupt:
            logger.info("\nDemo interrupted by user")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")
        if hasattr(self, "audio_engine"):
            self.audio_engine.shutdown()
        pygame.quit()

    def phase_1_cold_and_dark(self) -> None:
        """Phase 1: Cold and Dark at Parking."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 1: COLD AND DARK AT PARKING")
        logger.info("=" * 80)

        # Announce position
        self._speak_and_wait(
            "cockpit",
            f"Parked at {self.parking_id}, {self._get_airport_name()}",
            "MSG_POSITION_PARKED",
        )

        self._speak_and_wait(
            "cockpit",
            "Aircraft is cold and dark, parking brake set",
            "MSG_COCKPIT_COLD_DARK",
        )

    def phase_2_preflight(self) -> None:
        """Phase 2: Pre-Flight Checks and Ground Services."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 2: PRE-FLIGHT")
        logger.info("=" * 80)

        # Request refueling
        logger.info("\nRequesting ground services...")
        self._speak_and_wait(
            "pilot",
            "Ground, Cessna one two three alpha bravo, request refueling to full",
            "MSG_PILOT_REQUEST_FUEL",
        )

        time.sleep(0.5)
        self._speak_and_wait(
            "ground",
            "Cessna three alpha bravo, fuel truck on the way",
            "MSG_GROUND_FUEL_TRUCK",
        )

        time.sleep(1)
        self._speak_and_wait(
            "ground",
            "Cessna three alpha bravo, refueling to fifty two gallons",
            "MSG_GROUND_REFUELING",
        )

        time.sleep(1)
        self._speak_and_wait(
            "ground",
            "Cessna three alpha bravo, refueling complete, you are cleared to start engines",
            "MSG_GROUND_REFUEL_COMPLETE",
        )

        # Pre-start checklist
        logger.info("\nCompleting pre-start checklist...")
        time.sleep(1)
        self._speak_and_wait(
            "cockpit",
            "Pre-start checklist complete",
            "MSG_CHECKLIST_COMPLETE",
        )

    def phase_3_engine_start(self) -> None:
        """Phase 3: Engine Start."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 3: ENGINE START")
        logger.info("=" * 80)

        # Engine start
        logger.info("\nStarting engine...")
        self._speak_and_wait(
            "cockpit",
            "Clear prop",
            "MSG_COCKPIT_CLEAR_PROP",
        )

        time.sleep(1)
        self._speak_and_wait(
            "cockpit",
            "Starter engaged",
            "MSG_ENGINE_STARTER",
        )

        time.sleep(2)
        self._speak_and_wait(
            "cockpit",
            "Engine running",
            "MSG_ENGINE_RUNNING",
        )

        time.sleep(1)
        self._speak_and_wait(
            "cockpit",
            "Engine start checklist complete",
            "MSG_CHECKLIST_COMPLETE",
        )

    def phase_4_atc_clearance(self) -> None:
        """Phase 4: ATC Clearance."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 4: ATC CLEARANCE")
        logger.info("=" * 80)

        # Get ATIS
        logger.info("\nTuning ATIS frequency 135.65...")
        time.sleep(1)

        # Generate ATIS
        weather = WeatherInfo(
            wind_direction=310,
            wind_speed=8,
            wind_gusts=None,
            visibility=10,
            sky_condition="clear",
            temperature_c=22,
            dewpoint_c=14,
            altimeter=30.12,
        )

        self.current_atis = ATISInfo(
            airport_name=self._get_airport_name(),
            information_letter="Alpha",
            time_zulu="1855",
            weather=weather,
            active_runway=self.destination_runway,
            remarks="VFR aircraft say direction of flight",
            include_parking_instructions=True,
        )

        atis_broadcast = self.atis_generator.generate(self.current_atis)

        logger.info("\nATIS broadcast:")
        logger.info("-" * 80)
        logger.info(atis_broadcast)
        logger.info("-" * 80)

        # Play ATIS with radio effect
        self._speak_and_wait("atis", atis_broadcast, "MSG_ATIS_BROADCAST")

        # Contact Ground
        time.sleep(2)
        logger.info("\nContacting Ground Control on 121.7...")
        self._speak_and_wait(
            "pilot",
            f"Palo Alto Ground, Cessna one two three alpha bravo, {self.parking_id}, "
            f"taxi with information Alpha",
            "MSG_PILOT_GROUND_CONTACT",
        )

        time.sleep(1)

        # Ground responds
        ground_response = (
            f"Cessna one two three alpha bravo, Palo Alto Ground, "
            f"taxi to runway {self.destination_runway} via Alpha, hold short of runway"
        )
        logger.info("\nGround: %s", ground_response)
        self._speak_and_wait("ground", ground_response, "MSG_GROUND_TAXI_CLEARANCE")

        # Pilot readback
        time.sleep(1)
        readback = (
            f"Taxi runway {self.destination_runway} via Alpha, hold short, Cessna three alpha bravo"
        )
        logger.info("Pilot: %s", readback)
        self._speak_and_wait("pilot", readback, "MSG_PILOT_READBACK")

    def phase_5_taxi(self) -> None:
        """Phase 5: Taxi."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 5: TAXI")
        logger.info("=" * 80)

        # Release parking brake
        logger.info("\nReleasing parking brake...")
        self._speak_and_wait("cockpit", "Parking brake released", "MSG_PARKING_BRAKE_RELEASED")

        time.sleep(1)
        logger.info("Beginning taxi...")
        self._speak_and_wait("cockpit", "Taxiing", "MSG_COCKPIT_TAXIING")

        # Taxi segments with position announcements
        time.sleep(2)
        logger.info("\nPosition: Approaching taxiway Alpha")
        self._speak_and_wait("cockpit", "Approaching taxiway Alpha", "MSG_POSITION_APPROACHING")

        time.sleep(2)
        logger.info("Position: On taxiway Alpha centerline")
        self._speak_and_wait("cockpit", "On taxiway Alpha centerline", "MSG_POSITION_TAXIWAY")

        # AI traffic hold short
        time.sleep(2)
        logger.info("\n[AI Traffic: Another aircraft on taxiway]")
        self._speak_and_wait(
            "ground",
            "Cessna four five six charlie delta, hold short taxiway Alpha, traffic crossing left to right",
            "MSG_GROUND_HOLD_SHORT_TRAFFIC",
        )

        # Progressive taxi instruction
        time.sleep(2)
        logger.info("\n[Approaching runway]")
        self._speak_and_wait(
            "ground",
            f"Cessna three alpha bravo, continue taxi, hold short runway {self.destination_runway} at Alpha",
            "MSG_GROUND_TAXI_HOLD_SHORT",
        )

        time.sleep(1)
        self._speak_and_wait(
            "pilot",
            f"Hold short {self.destination_runway}, Cessna three alpha bravo",
            "MSG_PILOT_READBACK",
        )

        # At hold short line
        time.sleep(2)
        logger.info(f"\nArrived at runway {self.destination_runway} hold short line")
        self._speak_and_wait(
            "cockpit",
            f"Holding short runway {self.destination_runway}",
            "MSG_POSITION_HOLD_SHORT",
        )

        # Before takeoff checklist
        time.sleep(1)
        logger.info("\nCompleting before takeoff checklist...")
        self._speak_and_wait(
            "cockpit",
            "Before takeoff checklist complete",
            "MSG_CHECKLIST_COMPLETE",
        )

    def phase_6_runway_entry(self) -> None:
        """Phase 6: Runway Entry."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 6: RUNWAY ENTRY")
        logger.info("=" * 80)

        # Contact tower
        logger.info("\nSwitching to Tower 118.5...")
        time.sleep(1)

        self._speak_and_wait(
            "pilot",
            f"Palo Alto Tower, Cessna one two three alpha bravo, holding short runway {self.destination_runway}",
            "MSG_PILOT_TOWER_CONTACT",
        )

        time.sleep(1)

        # Tower clears for takeoff
        clearance = (
            f"Cessna one two three alpha bravo, runway {self.destination_runway}, "
            f"wind three one zero at eight, cleared for takeoff"
        )
        logger.info("\nTower: %s", clearance)
        self._speak_and_wait("tower", clearance, "MSG_TOWER_CLEARED_TAKEOFF")

        # Pilot readback
        time.sleep(1)
        readback = f"Cleared for takeoff runway {self.destination_runway}, Cessna three alpha bravo"
        logger.info("Pilot: %s", readback)
        self._speak_and_wait("pilot", readback, "MSG_PILOT_READBACK")

        # Line up on runway
        time.sleep(1)
        logger.info(f"\nTaxiing onto runway {self.destination_runway}...")
        self._speak_and_wait(
            "cockpit", f"On runway {self.destination_runway}", "MSG_POSITION_RUNWAY"
        )

    def phase_7_takeoff(self) -> None:
        """Phase 7: Takeoff."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 7: TAKEOFF")
        logger.info("=" * 80)

        # Apply takeoff power
        logger.info("\nApplying takeoff power...")
        self._speak_and_wait("cockpit", "Full throttle", "MSG_THROTTLE_FULL")

        # Speed callouts
        time.sleep(1)
        self._speak_and_wait("cockpit", "Twenty knots", "MSG_SPEED_20")

        time.sleep(1)
        self._speak_and_wait("cockpit", "Forty knots", "MSG_SPEED_40")

        time.sleep(1)
        self._speak_and_wait("cockpit", "V R, rotate", "MSG_SPEED_VR")

        time.sleep(1)
        self._speak_and_wait("cockpit", "Positive rate, gear up", "MSG_POSITIVE_RATE")

        time.sleep(1)
        self._speak_and_wait("cockpit", "Seventy five knots, climbing", "MSG_SPEED_75")

        # Liftoff
        time.sleep(1)
        logger.info("\nAirborne!")
        self._speak_and_wait("cockpit", "Aircraft airborne, climbing", "MSG_AIRBORNE")

        # Initial climb
        time.sleep(2)
        logger.info("\nClimbing through 500 feet AGL")
        self._speak_and_wait("cockpit", "Five hundred feet, climb established", "MSG_ALTITUDE_500")

        # After takeoff checklist
        time.sleep(1)
        logger.info("\nCompleting after takeoff checklist...")
        self._speak_and_wait(
            "cockpit", "After takeoff checklist complete", "MSG_CHECKLIST_COMPLETE"
        )

        # Departure
        time.sleep(1)
        logger.info("\n" + "=" * 80)
        logger.info("Departure successful!")
        logger.info("=" * 80)

    def _get_airport_name(self) -> str:
        """Get airport name from ICAO code.

        Returns:
            Airport name
        """
        airport_names = {
            "KPAO": "Palo Alto Airport",
            "KSFO": "San Francisco International",
            "KOAK": "Oakland International",
            "KSJC": "San Jose International",
        }
        return airport_names.get(self.airport_icao, f"{self.airport_icao}")

    def _speak_and_wait(self, voice_type: str, text: str, message_key: str) -> None:
        """Speak text and wait for completion.

        Args:
            voice_type: Type of voice (pilot, tower, ground, atis, cockpit, etc.)
            text: Text to speak
            message_key: Message key for lookup
        """
        logger.info("[%s] %s", voice_type.upper(), text)

        # Speak with appropriate message key
        # The voice and audio effects are determined by the message_key configuration
        self.tts.speak(message_key)

        # Wait for speech to complete
        # Check if channel is still playing
        max_wait = 30  # Maximum 30 seconds per message
        wait_time = 0
        check_interval = 0.1

        # For ATC messages, add radio static effect
        if voice_type in ["tower", "ground", "atis"]:
            # FMOD will apply the radio effect based on voice type
            pass

        while wait_time < max_wait:
            # Update audio engine
            self.audio_engine.update()

            # Check if still playing
            # Simple approach: just wait based on text length
            # More sophisticated: check actual playback status
            estimated_duration = len(text.split()) * 0.4  # ~0.4s per word at 200 WPM
            if wait_time >= estimated_duration:
                break

            time.sleep(check_interval)
            wait_time += check_interval

        # Small pause after each message
        time.sleep(0.5)


def main():
    """Run demonstration."""
    import argparse

    parser = argparse.ArgumentParser(description="Ground Operations Audio Demo")
    parser.add_argument(
        "--airport",
        default="KPAO",
        help="Airport ICAO code (default: KPAO)",
    )
    parser.add_argument(
        "--parking",
        default="parking_3",
        help="Parking position (default: parking_3)",
    )

    args = parser.parse_args()

    # Run demo
    demo = GroundOpsAudioDemo(airport_icao=args.airport, parking_id=args.parking)
    demo.run()


if __name__ == "__main__":
    main()

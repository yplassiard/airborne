"""Demonstration script for complete ground operations workflow.

This script demonstrates the integrated ground-to-takeoff workflow:
1. Cold and Dark at Parking
2. Pre-Flight (ground services, checklist)
3. Engine Start
4. ATC Clearance (ATIS, ground contact)
5. Taxi (progressive instructions, proximity audio)
6. Runway Entry (tower contact, takeoff clearance)
7. Takeoff

The script works at any airport size and plays all appropriate speech messages.
"""

import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.plugins.radio.atis import ATISGenerator, ATISInfo, WeatherInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class GroundOpsDemo:
    """Complete ground operations demonstration."""

    def __init__(self, airport_icao: str = "KPAO", parking_id: str = "parking_3") -> None:
        """Initialize demo.

        Args:
            airport_icao: Airport ICAO code (default: KPAO - Palo Alto)
            parking_id: Starting parking position
        """
        self.airport_icao = airport_icao
        self.parking_id = parking_id
        self.current_phase = 0

        # Initialize systems
        self.atis_generator = ATISGenerator()

        # Aircraft state
        self.aircraft_id = "N123AB"
        self.aircraft_type = "C172"
        self.position = (0.0, 0.0, 0.0)  # Will be updated
        self.heading = 0.0
        self.on_ground = True
        self.parking_brake = True

        # Flight plan
        self.destination_runway = "31"
        self.taxi_route = ["Alpha", "Bravo"]

        # ATIS
        self.current_atis: ATISInfo | None = None

        logger.info("=" * 80)
        logger.info("AirBorne Ground Operations Demo")
        logger.info("=" * 80)
        logger.info("Airport: %s", self.airport_icao)
        logger.info("Aircraft: %s (%s)", self.aircraft_id, self.aircraft_type)
        logger.info("Parking: %s", self.parking_id)
        logger.info("=" * 80)

    def run(self) -> None:
        """Run the complete demonstration."""
        try:
            self.phase_1_cold_and_dark()
            time.sleep(2)

            self.phase_2_preflight()
            time.sleep(2)

            self.phase_3_engine_start()
            time.sleep(2)

            self.phase_4_atc_clearance()
            time.sleep(2)

            self.phase_5_taxi()
            time.sleep(2)

            self.phase_6_runway_entry()
            time.sleep(2)

            self.phase_7_takeoff()

            logger.info("=" * 80)
            logger.info("Ground Operations Demo Complete!")
            logger.info("=" * 80)

        except KeyboardInterrupt:
            logger.info("\nDemo interrupted by user")
        except Exception as e:
            logger.error("Demo failed: %s", e, exc_info=True)

    def phase_1_cold_and_dark(self) -> None:
        """Phase 1: Cold and Dark at Parking."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 1: COLD AND DARK AT PARKING")
        logger.info("=" * 80)

        # Announce position
        self._speak("POSITION", f"Parked at {self.parking_id}, {self._get_airport_name()}")

        # Show aircraft state
        logger.info("Aircraft State:")
        logger.info("  Battery: OFF")
        logger.info("  Fuel Pump: OFF")
        logger.info("  Magnetos: OFF")
        logger.info("  Engine: OFF")
        logger.info("  Parking Brake: SET")
        logger.info("  Fuel: %.1f gallons", 26.0)  # Half tanks
        logger.info("  Weight: 2300 lbs")

        self._speak("COCKPIT", "Aircraft is cold and dark, parking brake set")

    def phase_2_preflight(self) -> None:
        """Phase 2: Pre-Flight Checks and Ground Services."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 2: PRE-FLIGHT")
        logger.info("=" * 80)

        # Request refueling
        logger.info("\nRequesting ground services...")
        self._speak("PILOT", "Ground, Cessna one two three alpha bravo, request refueling to full")

        # Simulate refueling
        logger.info("Ground services dispatching fuel truck...")
        self._speak("GROUND", "Cessna three alpha bravo, fuel truck on the way")

        time.sleep(1)
        logger.info("Refueling in progress...")
        self._speak("GROUND", "Cessna three alpha bravo, refueling to fifty two gallons")

        time.sleep(1)
        logger.info("Refueling complete: 52.0 gallons")
        self._speak(
            "GROUND",
            "Cessna three alpha bravo, refueling complete, you are cleared to start engines",
        )

        # Pre-start checklist
        logger.info("\nCompleting pre-start checklist...")
        checklist_items = [
            "Parking brake - SET",
            "Fuel quantity - CHECK",
            "Seats and belts - SECURE",
            "Flight controls - FREE AND CORRECT",
            "Fuel selector - BOTH",
            "Avionics - OFF",
        ]

        for item in checklist_items:
            logger.info("  ☑ %s", item)
            time.sleep(0.3)

        self._speak("CHECKLIST", "Pre-start checklist complete")

    def phase_3_engine_start(self) -> None:
        """Phase 3: Engine Start."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 3: ENGINE START")
        logger.info("=" * 80)

        # Engine start checklist
        logger.info("\nCompleting engine start checklist...")
        start_items = [
            "Throttle - 1/4 INCH OPEN",
            "Mixture - RICH",
            "Carburetor heat - COLD",
            "Master switch - ON",
            "Beacon - ON",
        ]

        for item in start_items:
            logger.info("  ☑ %s", item)
            time.sleep(0.3)

        # Start engine
        logger.info("\nStarting engine...")
        self._speak("COCKPIT", "Clear prop")

        time.sleep(0.5)
        logger.info("Magnetos BOTH, engaging starter...")
        self._speak("ENGINE", "Starter engaged")

        time.sleep(1)
        logger.info("Engine starting...")

        # Simulate engine start (simplified - no actual engine object in demo)
        # In real implementation: self.engine.magnetos = 3, etc.

        time.sleep(1)
        logger.info("Engine running at 1000 RPM")
        self._speak("ENGINE", "Engine running")

        logger.info("\nPost-start checks:")
        logger.info("  ☑ Oil pressure - IN GREEN")
        logger.info("  ☑ Alternator - CHARGING")
        logger.info("  ☑ Radios - ON")

        self._speak("CHECKLIST", "Engine start checklist complete")

    def phase_4_atc_clearance(self) -> None:
        """Phase 4: ATC Clearance."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 4: ATC CLEARANCE")
        logger.info("=" * 80)

        # Get ATIS
        logger.info("\nTuning ATIS frequency 135.65...")
        time.sleep(0.5)

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

        logger.info("\nATIS received:")
        logger.info("-" * 80)
        logger.info(atis_broadcast)
        logger.info("-" * 80)

        self._speak("ATIS", atis_broadcast)

        # Contact Ground
        time.sleep(1)
        logger.info("\nContacting Ground Control on 121.7...")
        self._speak(
            "PILOT",
            f"Palo Alto Ground, Cessna one two three alpha bravo, {self.parking_id}, "
            f"taxi with information Alpha",
        )

        time.sleep(0.5)

        # Ground responds
        ground_response = (
            f"Cessna one two three alpha bravo, Palo Alto Ground, "
            f"taxi to runway {self.destination_runway} via Alpha, hold short of runway"
        )
        logger.info("\nGround: %s", ground_response)
        self._speak("GROUND", ground_response)

        # Pilot readback
        time.sleep(0.5)
        readback = (
            f"Taxi runway {self.destination_runway} via Alpha, hold short, Cessna three alpha bravo"
        )
        logger.info("Pilot: %s", readback)
        self._speak("PILOT", readback)

    def phase_5_taxi(self) -> None:
        """Phase 5: Taxi."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 5: TAXI")
        logger.info("=" * 80)

        # Release parking brake
        logger.info("\nReleasing parking brake...")
        self.parking_brake = False
        self._speak("COCKPIT", "Parking brake released")

        # Start taxi
        time.sleep(0.5)
        logger.info("Beginning taxi...")
        self._speak("COCKPIT", "Taxiing")

        # Simulate taxi with progressive clearances
        segments = [
            ("Alpha", "Approaching taxiway Alpha"),
            ("Alpha centerline", "On taxiway Alpha centerline"),
            ("Alpha/Bravo intersection", "Approaching Bravo"),
            ("Runway 31 hold short", "Holding short runway 31 at Alpha"),
        ]

        for i, (waypoint, announcement) in enumerate(segments):
            time.sleep(1)
            logger.info("\nPosition: %s", waypoint)
            self._speak("POSITION", announcement)

            # Simulate AI traffic
            if i == 1:
                logger.info("\n[AI Traffic: N456CD taxiing on Bravo]")
                self._speak(
                    "GROUND",
                    "Cessna four five six charlie delta, hold short taxiway Alpha, traffic crossing left to right",
                )

            # Progressive taxi instruction
            if i == 2:
                time.sleep(0.5)
                logger.info("\n[Approaching runway crossing point]")
                self._speak(
                    "GROUND",
                    f"Cessna three alpha bravo, continue taxi, hold short runway {self.destination_runway} at Alpha",
                )
                time.sleep(0.3)
                self._speak(
                    "PILOT", f"Hold short {self.destination_runway}, Cessna three alpha bravo"
                )

        # At hold short line
        time.sleep(1)
        logger.info("\nArrived at runway %s hold short line", self.destination_runway)
        self._speak("COCKPIT", f"Holding short runway {self.destination_runway}")

        # Before takeoff checklist
        logger.info("\nCompleting before takeoff checklist...")
        before_takeoff_items = [
            "Flight controls - FREE AND CORRECT",
            "Flaps - SET FOR TAKEOFF",
            "Trim - TAKEOFF",
            "Fuel selector - BOTH",
            "Mixture - RICH",
            "Carburetor heat - COLD",
            "Engine instruments - GREEN",
            "Doors and windows - CLOSED AND LOCKED",
        ]

        for item in before_takeoff_items:
            logger.info("  ☑ %s", item)
            time.sleep(0.3)

        self._speak("CHECKLIST", "Before takeoff checklist complete")

    def phase_6_runway_entry(self) -> None:
        """Phase 6: Runway Entry."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 6: RUNWAY ENTRY")
        logger.info("=" * 80)

        # Contact tower
        logger.info("\nSwitching to Tower 118.5...")
        time.sleep(0.5)

        self._speak(
            "PILOT",
            f"Palo Alto Tower, Cessna one two three alpha bravo, holding short runway {self.destination_runway}",
        )

        time.sleep(0.5)

        # Tower clears for takeoff
        clearance = (
            f"Cessna one two three alpha bravo, runway {self.destination_runway}, "
            f"wind three one zero at eight, cleared for takeoff"
        )
        logger.info("\nTower: %s", clearance)
        self._speak("TOWER", clearance)

        # Pilot readback
        time.sleep(0.5)
        readback = f"Cleared for takeoff runway {self.destination_runway}, Cessna three alpha bravo"
        logger.info("Pilot: %s", readback)
        self._speak("PILOT", readback)

        # Line up on runway
        time.sleep(1)
        logger.info("\nTaxiing onto runway %s...", self.destination_runway)
        self._speak("POSITION", f"On runway {self.destination_runway}")

        # Final checks
        time.sleep(0.5)
        logger.info("\nFinal checks before takeoff:")
        logger.info("  ☑ Heading - ALIGNED WITH RUNWAY")
        logger.info("  ☑ Lights - LANDING/STROBE ON")
        logger.info("  ☑ Transponder - ALT")
        logger.info("  ☑ TIME - NOTED")

    def phase_7_takeoff(self) -> None:
        """Phase 7: Takeoff."""
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 7: TAKEOFF")
        logger.info("=" * 80)

        # Apply takeoff power
        logger.info("\nApplying takeoff power...")
        self._speak("COCKPIT", "Full throttle")

        time.sleep(0.5)
        logger.info("Throttle: FULL")
        logger.info("Mixture: RICH")
        logger.info("RPM: 2400")

        # Acceleration
        speeds = [
            (1, 20, "Twenty knots"),
            (1, 40, "Forty knots"),
            (1, 55, "V R, rotate"),
            (1, 65, "Positive rate, gear up"),
            (1, 75, "Seventy five knots, climbing"),
        ]

        for delay, speed, callout in speeds:
            time.sleep(delay)
            logger.info("Airspeed: %d knots", speed)
            self._speak("COCKPIT", callout)

        # Liftoff
        time.sleep(1)
        self.on_ground = False
        logger.info("\nAirborne!")
        self._speak("COCKPIT", "Aircraft airborne, climbing")

        # Initial climb
        time.sleep(1)
        logger.info("\nClimbing through 500 feet AGL")
        logger.info("Airspeed: 80 knots")
        logger.info("Vertical speed: 700 feet per minute")

        self._speak("COCKPIT", "Five hundred feet, climb established")

        # After takeoff checklist
        time.sleep(1)
        logger.info("\nCompleting after takeoff checklist...")
        after_takeoff_items = [
            "Throttle - AS REQUIRED",
            "Mixture - LEAN FOR ALTITUDE",
            "Carburetor heat - AS REQUIRED",
        ]

        for item in after_takeoff_items:
            logger.info("  ☑ %s", item)
            time.sleep(0.3)

        self._speak("CHECKLIST", "After takeoff checklist complete")

        # Departure
        time.sleep(1)
        logger.info("\n" + "=" * 80)
        logger.info("Departure successful!")
        logger.info("Altitude: 1000 feet AGL")
        logger.info("Airspeed: 90 knots")
        logger.info("Heading: 310 degrees")
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

    def _speak(self, voice_type: str, text: str) -> None:
        """Simulate speech output.

        Args:
            voice_type: Type of voice (PILOT, TOWER, GROUND, ATIS, COCKPIT, etc.)
            text: Text to speak
        """
        # In a real implementation, this would use the TTS system
        # For demo, we just log with voice type prefix
        prefix_map = {
            "PILOT": "[PILOT]",
            "TOWER": "[TOWER]",
            "GROUND": "[GROUND]",
            "ATIS": "[ATIS]",
            "COCKPIT": "[COCKPIT]",
            "ENGINE": "[ENGINE]",
            "POSITION": "[POSITION]",
            "CHECKLIST": "[CHECKLIST]",
        }

        prefix = prefix_map.get(voice_type, f"[{voice_type}]")
        logger.info("%s %s", prefix, text)

        # NOTE: In real integration, would publish audio message
        # self.message_queue.publish(Message(...)) for audio playback


def main():
    """Run demonstration."""
    # Parse arguments
    import argparse

    parser = argparse.ArgumentParser(description="Ground Operations Demo")
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
    demo = GroundOpsDemo(airport_icao=args.airport, parking_id=args.parking)
    demo.run()


if __name__ == "__main__":
    main()

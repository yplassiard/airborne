"""Generate and cache taxiway data for all airports.

This script processes all airports in the OurAirports database and generates
taxiway networks based on airport size. The generated data is cached to disk
for fast loading at runtime.

Usage:
    python scripts/generate_taxiway_cache.py

Output:
    - data/airports/taxiway_cache.json: Cached taxiway data for all airports
"""

import json
import logging
import time
from pathlib import Path

from airborne.airports.classifier import AirportClassifier
from airborne.airports.database import AirportDatabase
from airborne.airports.taxiway_generator import TaxiwayGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def serialize_taxiway_graph(graph):
    """Serialize a TaxiwayGraph to a JSON-compatible dict.

    Args:
        graph: TaxiwayGraph to serialize

    Returns:
        Dictionary containing nodes and edges
    """
    nodes_data = []
    for node_id, node in graph.nodes.items():
        nodes_data.append(
            {
                "id": node_id,
                "position": {"x": node.position.x, "y": node.position.y, "z": node.position.z},
                "type": node.node_type,
                "name": node.name,
            }
        )

    edges_data = []
    for from_node, edges in graph.edges.items():
        for edge in edges:
            edges_data.append(
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "distance_m": edge.distance_m,
                    "type": edge.edge_type,
                    "name": edge.name,
                }
            )

    return {"nodes": nodes_data, "edges": edges_data}


def generate_taxiway_cache(
    data_dir: Path,
    output_file: Path,
    min_runway_length_ft: float = 2000.0,
    max_airports: int | None = None,
) -> None:
    """Generate taxiway cache for all airports.

    Args:
        data_dir: Directory containing OurAirports CSV files
        output_file: Output file for cached taxiway data
        min_runway_length_ft: Minimum runway length to include airport
        max_airports: Maximum number of airports to process (for testing)
    """
    logger.info("Starting taxiway cache generation...")
    logger.info("Loading airport database from %s", data_dir)

    # Load airport database
    db = AirportDatabase()
    db.load_from_csv(data_dir)

    logger.info("Loaded %d airports", db.get_airport_count())

    # Initialize classifier and generator
    classifier = AirportClassifier()
    generator = TaxiwayGenerator()

    # Cache data structure
    cache = {
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "airports": {},
        "statistics": {
            "total_processed": 0,
            "by_category": {"small": 0, "medium": 0, "large": 0, "extra_large": 0},
            "skipped": {"no_runways": 0, "short_runways": 0},
        },
    }

    # Process airports
    processed_count = 0
    skipped_no_runways = 0
    skipped_short_runways = 0

    for icao, airport in db.airports.items():
        # Check if we've hit the limit
        if max_airports and processed_count >= max_airports:
            logger.info("Reached maximum airport limit (%d)", max_airports)
            break

        # Get runways for this airport
        runways = db.get_runways(icao)

        # Skip airports with no runways
        if not runways:
            skipped_no_runways += 1
            continue

        # Skip airports with only very short runways
        longest_runway = max(runways, key=lambda r: r.length_ft)
        if longest_runway.length_ft < min_runway_length_ft:
            skipped_short_runways += 1
            continue

        # Classify airport
        category = classifier.classify(airport, runways)

        # Generate taxiway network
        try:
            graph = generator.generate(airport, runways, category)

            # Serialize and cache
            cache["airports"][icao] = {
                "name": airport.name,
                "category": category.value,
                "position": {
                    "x": airport.position.x,
                    "y": airport.position.y,
                    "z": airport.position.z,
                },
                "runway_count": len(runways),
                "longest_runway_ft": longest_runway.length_ft,
                "taxiways": serialize_taxiway_graph(graph),
                "node_count": graph.get_node_count(),
                "edge_count": graph.get_edge_count(),
            }

            # Update statistics
            cache["statistics"]["by_category"][category.value] += 1
            processed_count += 1

            if processed_count % 100 == 0:
                logger.info(
                    "Processed %d airports (%d skipped)",
                    processed_count,
                    skipped_no_runways + skipped_short_runways,
                )

        except Exception as e:
            logger.error("Error generating taxiways for %s: %s", icao, e)
            continue

    # Update final statistics
    cache["statistics"]["total_processed"] = processed_count
    cache["statistics"]["skipped"]["no_runways"] = skipped_no_runways
    cache["statistics"]["skipped"]["short_runways"] = skipped_short_runways

    # Write cache to disk
    logger.info("Writing cache to %s", output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

    # Print summary
    logger.info("=" * 80)
    logger.info("Taxiway Cache Generation Complete")
    logger.info("=" * 80)
    logger.info("Total airports processed: %d", processed_count)
    logger.info("Skipped (no runways): %d", skipped_no_runways)
    logger.info("Skipped (short runways): %d", skipped_short_runways)
    logger.info("")
    logger.info("By category:")
    for category, count in cache["statistics"]["by_category"].items():
        logger.info("  %s: %d", category.upper(), count)
    logger.info("")
    logger.info("Cache file size: %.2f MB", output_file.stat().st_size / 1024 / 1024)
    logger.info("Output: %s", output_file)


def main():
    """Main entry point."""
    # Paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data" / "airports"
    output_file = data_dir / "taxiway_cache.json"

    # Check if airport data exists
    if not (data_dir / "airports.csv").exists():
        logger.error("Airport data not found at %s", data_dir)
        logger.error("Run scripts/download_airport_data.py first")
        return 1

    # Generate cache
    generate_taxiway_cache(
        data_dir=data_dir,
        output_file=output_file,
        min_runway_length_ft=2000.0,
        max_airports=None,  # Process all airports (use a number for testing)
    )

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

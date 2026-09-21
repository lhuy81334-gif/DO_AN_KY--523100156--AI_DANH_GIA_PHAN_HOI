import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.database import db, ensure_indexes
from app.ingestion.csv_importer import CSVImporter
from app.ingestion.json_importer import JSONImporter


def main() -> None:
    parser = argparse.ArgumentParser(description="Import review dataset into MongoDB")
    parser.add_argument("file", help="Path to .csv or .json review file")
    parser.add_argument("--platform", default="tiki", help="Platform code matching imported products: tiki or lazada")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    ensure_indexes(db)
    importer = CSVImporter(db, args.batch_size) if args.file.lower().endswith(".csv") else JSONImporter(db, args.batch_size)
    stats = importer.import_reviews_file(args.file, platform_code=args.platform, progress_callback=lambda p, t: print(f"processed {p}/{t}"))
    print(stats)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""entry point for pmu-misevolution-guard CLI commands"""
import sys
import os

def main():
    """Print usage and exit."""
    print("Usage: pmu-guard --help")
    print("")
    print("Commands:")
    print("  guard    Run the three-gate security guard")
    print("  audit    Run drift self-check")
    print("")
    print("Use 'python scripts/write_gate.py' or 'python scripts/drift_report.py' directly.")
    sys.exit(0)

if __name__ == "__main__":
    main()
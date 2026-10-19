#!/usr/bin/env python3
"""PMU Misevolution Guard - Entry point CLI"""
import sys
import os

def main():
    """CLI entry point for pmu-misevolution-guard."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("")
        print("Available commands:")
        print("  pre      Pre-use gate (write_gate --mode pre)")
        print("  post     Post-use gate (write_gate --mode post)")
        print("  drift    Drift report (drift_report.py)")
        print("")
        print("Direct usage:")
        print("  python scripts/write_gate.py --mode pre --content '...'")
        print("  python scripts/drift_report.py --scan <dir>")
        sys.exit(0)

    cmd = sys.argv[1]
    script_dir = os.path.join(os.path.dirname(__file__), '..', 'scripts')
    script_dir = os.path.abspath(script_dir)

    if cmd == 'pre':
        os.execvp('python3', ['python3', os.path.join(script_dir, 'write_gate.py'), '--mode', 'pre'] + sys.argv[2:])
    elif cmd == 'post':
        os.execvp('python3', ['python3', os.path.join(script_dir, 'write_gate.py'), '--mode', 'post'] + sys.argv[2:])
    elif cmd == 'drift':
        os.execvp('python3', ['python3', os.path.join(script_dir, 'drift_report.py')] + sys.argv[2:])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(2)

if __name__ == "__main__":
    main()
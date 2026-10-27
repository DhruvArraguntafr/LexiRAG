"""Start an isolated app, run the browser workflows, and stop the test server.

python -m scripts.check_application --directory refactor-validation/browser --live
Requires development dependencies and Chromium or Edge. --live uses Gemini.
"""
import argparse
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

from config.settings import ROOT
from scripts.check_simple_ui import check


def main(args):
    directory = args.directory.resolve()
    corpus = directory / "corpus"
    if (corpus / "metadata.sqlite3").exists():
        raise SystemExit("Choose a fresh validation directory; the upload check expects an empty test corpus.")
    directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LEXIRAG_DATA_DIR=str(corpus), LEXIRAG_PORT=str(args.port))
    env.setdefault("HF_HOME", str(ROOT / "data/model_cache"))
    url = f"http://127.0.0.1:{args.port}"
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=ROOT, env=env,
                                  stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            while True:
                if server.poll() is not None:
                    raise RuntimeError("Test server exited; inspect server.log.")
                try:
                    with urlopen(url + "/api/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Test server did not become ready; inspect server.log.")
                    time.sleep(0.2)
            asyncio.run(check(url, directory, args.live))
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("refactor-validation/application"))
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument("--live", action="store_true")
    main(parser.parse_args())

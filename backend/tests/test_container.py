"""Opt-in checks for the production image, run by CI after building it."""
import json
import os
import re
import subprocess
import time
import uuid
from http.client import HTTPException
from urllib.request import Request, urlopen

import pytest


IMAGE = os.getenv("GROUNDEDNEWS_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="Set GROUNDEDNEWS_IMAGE to test a built image")


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def test_container_serves_ui_api_and_persists_sqlite():
    name = f"groundednews-test-{uuid.uuid4().hex}"
    volume = f"{name}-data"
    docker("volume", "create", volume)
    try:
        def start():
            docker("run", "-d", "--name", name, "-p", "127.0.0.1::3000",
                   "-v", f"{volume}:/data", IMAGE)
            address = docker("port", name, "3000/tcp")
            base = f"http://{address}"
            for _ in range(90):
                try:
                    with urlopen(f"{base}/api/stats", timeout=2) as response:
                        assert response.status == 200
                    return base
                except (OSError, HTTPException):
                    time.sleep(1)
            pytest.fail(f"Container did not become ready:\n{docker('logs', name)}")

        base = start()
        with urlopen(base, timeout=10) as response:
            html = response.read().decode()
        assert "GroundedNews" in html
        asset = re.search(r'src="(/_next/static/[^"]+)"', html)
        assert asset, "The frontend should serve its production JavaScript"
        with urlopen(f"{base}{asset.group(1)}", timeout=10) as response:
            assert response.status == 200
        request = Request(
            f"{base}/api/sources",
            data=json.dumps({"name": name, "feed_url": "https://example.com/feed",
                             "bias_label": "center"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            source_id = json.load(response)["id"]
        docker("stop", "--time", "10", name)
        assert docker("inspect", "-f", "{{.State.ExitCode}}", name) == "0"
        docker("rm", name)
        base = start()
        with urlopen(f"{base}/api/sources", timeout=10) as response:
            sources = json.load(response)
        assert any(source["id"] == source_id and source["name"] == name for source in sources)
        assert docker("exec", name, "id", "-u") == "10001"
        assert docker("exec", name, "test", "-f", "/data/groundednews.db") == ""
        assert name in docker("exec", name, "python", "/app/cli.py", "sources")
        docker("exec", name, "python", "/app/backend/backup_db.py")
        assert docker("exec", name, "ls", "/data/backups").startswith("groundednews-")
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False)
        subprocess.run(["docker", "volume", "rm", volume], check=False)

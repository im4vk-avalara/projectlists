#!/usr/bin/env python3
"""Starter verifier supplied with the prior audit."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Response:
    status: int
    body: str
    headers: dict[str, str]


def request(endpoint: str, host: str, path: str) -> Response:
    req = urllib.request.Request(
        f"{endpoint}{path}",
        headers={"Host": host},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return Response(
                response.status,
                response.read().decode(),
                dict(response.headers.items()),
            )
    except urllib.error.HTTPError as error:
        return Response(
            error.code,
            error.read().decode(),
            dict(error.headers.items()),
        )


def main() -> int:
    endpoint = os.getenv("PRIVATE_ENDPOINT", "http://127.0.0.1:28480")

    assistant = request(endpoint, "assistant.internal.lab", "/openapi.json")
    workflow = request(endpoint, "workflow.internal.lab", "/")
    entrypoint = assistant.headers.get("X-Lab-Entrypoint")

    print(f"PRIVATE_ENDPOINT: {endpoint}")
    print(f"entrypoint: {entrypoint or 'missing'}")
    print(f"assistant: {assistant.status}")
    print(f"workflow root: {workflow.status}")

    if entrypoint != "approved-consumer":
        print(
            "FAIL: PRIVATE_ENDPOINT did not reach the approved-consumer "
            "listener; check the exported port"
        )
        return 1

    if assistant.status == 200 and workflow.status == 404:
        print("PASS: approved service reachable; workflow blocked")
        return 0

    print("FAIL: isolation contract not met")
    return 1


if __name__ == "__main__":
    sys.exit(main())

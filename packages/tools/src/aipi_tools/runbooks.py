"""Deterministic BM25 over local Markdown chunks; no vector database or arbitrary paths."""

import math
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import cast

from aipi_telemetry.evidence import Evidence, Redaction, evidence_id
from aipi_telemetry.redaction import redact
from pydantic import JsonValue

from aipi_tools.scope import Scope


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


class RunbookIndex:
    def __init__(self, root: Path) -> None:
        self.chunks: list[tuple[str, str, tuple[str, ...]]] = []
        for path in sorted(root.glob("*.md")):
            if path.is_symlink():
                continue
            content = path.read_text()
            match = re.search(r"<!-- services:([^>]+)-->", content)
            services = tuple(x.strip() for x in match[1].split(",")) if match else ()
            for chunk in re.split(r"(?m)(?=^## )", content):
                if chunk.strip():
                    self.chunks.append((path.name, chunk[:4000], services))

    def search(self, query: str, scope: Scope) -> tuple[Evidence, ...]:
        documents = [chunk for chunk in self.chunks if set(chunk[2]) & set(scope.services)]
        if not documents:
            return ()
        counts = [Counter(tokens(chunk[1])) for chunk in documents]
        lengths = [sum(count.values()) for count in counts]
        mean = sum(lengths) / len(lengths) or 1
        ranked = []
        for index, (name, chunk, services) in enumerate(documents):
            score = 0.0
            for term in sorted(set(tokens(query))):
                df = sum(term in count for count in counts)
                frequency = counts[index][term]
                idf = math.log(1 + (len(counts) - df + 0.5) / (df + 0.5))
                score += (
                    idf
                    * frequency
                    * 2.5
                    / (frequency + 1.5 * (0.25 + 0.75 * lengths[index] / mean))
                )
            if score <= 0:
                continue
            service = next(s for s in scope.services if s in services)
            digest = sha256(chunk.encode()).hexdigest()
            reference = f"runbooks:{name}:{digest}:{service}:{scope.window.start_time.isoformat()}"
            clean, markers = redact({"text": chunk, "summary": chunk.splitlines()[0][:200]})
            payload = cast(dict[str, JsonValue], clean)
            evidence = Evidence(
                evidence_id=evidence_id("runbook", reference),
                type="runbook",
                service=service,
                timestamp=scope.window.start_time,
                source_ref=reference,
                summary=str(payload.pop("summary")),
                payload=payload,
                redactions=tuple(Redaction.model_validate(m) for m in markers),
            )
            ranked.append((score, evidence))
        return tuple(e for _, e in sorted(ranked, key=lambda x: (-x[0], x[1].source_ref)))

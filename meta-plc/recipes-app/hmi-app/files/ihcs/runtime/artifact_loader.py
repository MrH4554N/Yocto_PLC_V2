"""
Load and verify the IHCS Raspberry Pi artifact package.

Verifies SHA256 checksums on load. Fails closed: if checksums are missing
or invalid, raises ArtifactIntegrityError and produces no advisory output.
"""

import hashlib
import json
from pathlib import Path


class ArtifactIntegrityError(RuntimeError):
    pass


class ArtifactLoader:
    def __init__(self, artifact_dir: str):
        self.artifact_dir = Path(artifact_dir)
        self._manifest: dict | None = None
        self._verified = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_and_verify(self) -> dict:
        """Load manifest and verify all checksums. Raises on failure."""
        manifest_path = self.artifact_dir / "manifest.json"
        if not manifest_path.exists():
            raise ArtifactIntegrityError(
                f"manifest.json not found in {self.artifact_dir}"
            )

        with open(manifest_path) as f:
            manifest = json.load(f)

        self._verify_safety_fields(manifest)
        self._verify_checksums()

        self._manifest = manifest
        self._verified = True
        return manifest

    @property
    def manifest(self) -> dict:
        if self._manifest is None:
            raise RuntimeError("load_and_verify() must be called before accessing manifest")
        return self._manifest

    def load_json(self, rel_path: str) -> dict:
        self._require_verified()
        p = self.artifact_dir / rel_path
        if not p.exists():
            raise FileNotFoundError(f"Artifact file not found: {rel_path}")
        with open(p) as f:
            return json.load(f)

    def model_path(self, rel_path: str) -> str:
        self._require_verified()
        p = self.artifact_dir / rel_path
        if not p.exists():
            raise FileNotFoundError(f"Model file not found: {rel_path}")
        return str(p)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_verified(self) -> None:
        if not self._verified:
            raise RuntimeError("load_and_verify() must be called first")

    def _verify_safety_fields(self, manifest: dict) -> None:
        errors = []
        if manifest.get("safety_mode") != "advisory_only":
            errors.append(f"safety_mode is not 'advisory_only': {manifest.get('safety_mode')}")
        if manifest.get("plc_write_allowed") is not False:
            errors.append(f"plc_write_allowed is not false: {manifest.get('plc_write_allowed')}")
        if manifest.get("human_approval_required") is not True:
            errors.append(f"human_approval_required is not true: {manifest.get('human_approval_required')}")
        if errors:
            raise ArtifactIntegrityError(
                "Manifest safety field verification failed:\n" + "\n".join(errors)
            )

    def _verify_checksums(self) -> None:
        checksum_file = self.artifact_dir / "checksums.sha256"
        if not checksum_file.exists():
            raise ArtifactIntegrityError(
                f"checksums.sha256 not found in {self.artifact_dir} — fail closed"
            )

        failures = []
        with open(checksum_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("  ", 1)
                if len(parts) != 2:
                    continue
                expected_hex, rel_path = parts
                file_path = self.artifact_dir / rel_path
                if not file_path.exists():
                    failures.append(f"MISSING: {rel_path}")
                    continue
                actual_hex = _sha256(file_path)
                if actual_hex != expected_hex:
                    failures.append(f"CHECKSUM_MISMATCH: {rel_path}")

        if failures:
            raise ArtifactIntegrityError(
                f"Artifact integrity check failed ({len(failures)} error(s)):\n"
                + "\n".join(failures)
            )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

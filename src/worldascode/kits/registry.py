"""Kit catalog, immutable release repository and scoped host permissions."""

import fnmatch
import json
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from worldascode.config import ROOT, paths
from worldascode.kits.context import cards
from worldascode.storage.artifacts import digest, file_hash, run_lock, write_json

SLUG = re.compile(r"^[a-z][a-z0-9.-]{0,79}$")

ACTIONS = {"submit", "promote-incubating", "promote-stable", "set-default", "rollback"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc)


def package_files(folder):
    from worldascode.kits.code import analyze_source

    folder = Path(folder)
    names = {"kit.mjs", "kit-api.md", "capabilities.json"}
    pending = ["kit.mjs"]
    while pending:
        name = pending.pop()
        for specifier in analyze_source((folder / name).read_text(encoding="utf-8"))[
            "imports"
        ]:
            if not specifier.startswith("./"):
                continue
            dep = specifier[2:]
            if Path(dep).name != dep:
                raise ValueError("KIT_UNSUPPORTED_DEPENDENCY_PATH")
            if dep not in names:
                names.add(dep)
                pending.append(dep)
    manifest = folder / "kit-manifest.json"
    if manifest.is_file():
        names.add("kit-manifest.json")
        names.update(entry["path"] for entry in read(manifest)["documents"])
    for name in names:
        if not (folder / name).resolve().is_relative_to(folder.resolve()):
            raise ValueError("KIT_UNSAFE_PACKAGE_PATH")
    return [folder / name for name in sorted(names)]


class PermissionService:
    def __init__(self, root):
        self.root = root

    def grant(self, subject, packages, actions, hours=24 * 30):
        if (
            not set(actions) <= ACTIONS
            or not actions
            or not subject
            or not 0 < hours <= 24 * 366
        ):
            raise ValueError("INVALID_KIT_GRANT")
        if not packages or any(not SLUG.fullmatch(p) for p in packages):
            raise ValueError("INVALID_KIT_PACKAGE_SCOPE")
        token = uuid.uuid4().hex
        record = {
            "id": token,
            "subject": subject,
            "packages": packages,
            "actions": sorted(set(actions)),
            "expires_at": (now() + timedelta(hours=hours)).isoformat(),
            "revoked": False,
        }
        write_json(self.root / "grants" / f"{token}.json", record, exclusive=True)
        return token

    def authorize(self, token, subject, package, action):
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            raise ValueError("KIT_GRANT_REQUIRED")
        grant = read(self.root / "grants" / f"{token}.json")
        if (
            grant["revoked"]
            or grant["subject"] != subject
            or now() >= datetime.fromisoformat(grant["expires_at"])
        ):
            raise ValueError("KIT_GRANT_EXPIRED_OR_REVOKED")
        if action not in grant["actions"] or not any(
            fnmatch.fnmatchcase(package, p) for p in grant["packages"]
        ):
            raise ValueError("KIT_GRANT_SCOPE_DENIED")
        return grant

    def revoke(self, token):
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("INVALID_KIT_GRANT_ID")
        with run_lock(self.root):
            path = self.root / "grants" / f"{token}.json"
            record = read(path)
            record["revoked"] = True
            write_json(path, record)


class ReleaseRepository:
    def __init__(self, root):
        self.root = root

    def verify_release(self, package, version):
        if not SLUG.fullmatch(package) or not re.fullmatch(r"[a-f0-9]{64}", version):
            raise ValueError("INVALID_KIT_RELEASE_ID")
        folder = self.root / "releases" / package / version
        release = read(folder / "release.json")
        if (
            release["package"] != package
            or release["version"] != version
            or digest(release["files"]) != version
        ):
            raise ValueError("KIT_RELEASE_DESCRIPTOR_MISMATCH")
        for name, expected in release["files"].items():
            if (
                not (folder / name).resolve().is_relative_to(folder.resolve())
                or file_hash(folder / name) != expected
            ):
                raise ValueError("KIT_RELEASE_FILE_MISMATCH")
        return folder, release

    def resolve(self, package="buildings", channel=None, version=None):
        package_record = read(self.root / "registry.json")["packages"][package]
        channel = channel or package_record["default_channel"]
        if channel not in ("builtin", "incubating", "stable"):
            raise ValueError("INVALID_KIT_CHANNEL")
        version = version or package_record["channels"].get(channel)
        if not version:
            raise ValueError("KIT_CHANNEL_UNAVAILABLE:" + channel)
        folder, release = self.verify_release(package, version)
        return folder, {
            "package": package,
            "channel": channel,
            "version": version,
            "kit_sha256": release["files"]["kit.mjs"],
        }

    def pin(self, destination, package="buildings", channel=None, version=None):
        folder, selection = self.resolve(package, channel, version)
        shutil.copytree(folder, destination)
        write_json(Path(destination) / "library-selection.json", selection)
        return Path(destination) / "kit.mjs"

    def search(self, query, limit=6):
        if not 1 <= limit <= 12:
            raise ValueError("KIT_SEARCH_LIMIT")
        words = set(re.findall(r"\w+", query.lower()))
        matches = []
        for name, entry in read(self.root / "registry.json")["packages"].items():
            text = (name + " " + entry["summary"]).lower()
            score = sum(word in text for word in words)
            if score:
                matches.append(
                    (
                        score,
                        {
                            "package": name,
                            "summary": entry["summary"],
                            "default_channel": entry["default_channel"],
                        },
                    )
                )
        return [
            entry
            for _, entry in sorted(matches, key=lambda item: item[0], reverse=True)[
                :limit
            ]
        ]


class KitRegistry:
    def __init__(self, root=None):
        from worldascode.kits.publication import KitPublisher
        from worldascode.kits.validation import ReleaseValidator

        self.root = Path(root or paths().library_dir).resolve()
        self.permissions = PermissionService(self.root)
        self.releases = ReleaseRepository(self.root)
        self.validator = ReleaseValidator(self)
        self.publisher = KitPublisher(self)

    def initialize(self, source=None):
        """Bootstrap the existing SDK, explicitly not a new validated release."""
        self.root.mkdir(parents=True, exist_ok=True)
        with run_lock(self.root):
            if (self.root / "registry.json").exists():
                return read(self.root / "registry.json")
            source = Path(source or ROOT / "runtime")
            files = package_files(source)
            hashes = {p.relative_to(source).as_posix(): file_hash(p) for p in files}
            version = digest(hashes)
            folder = self.root / "releases/buildings" / version
            folder.mkdir(parents=True)
            for path in files:
                target = folder / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            write_json(
                folder / "release.json",
                {
                    "schema": "shared-kit-release-1",
                    "package": "buildings",
                    "version": version,
                    "files": hashes,
                    "origin": "builtin snapshot; no new cross-site quality claim",
                    "channel": "builtin",
                },
            )
            write_json(
                folder / "context-index.json",
                {
                    "cards": [
                        {"id": c["id"], "methods": c["methods"]}
                        for c in cards(folder / "kit-api.md").values()
                    ]
                },
            )
            registry = {
                "schema": "shared-kit-registry-1",
                "revision": 1,
                "packages": {
                    "buildings": {
                        "summary": "Metric building geometry, roof/facade/material authoring",
                        "channels": {
                            "builtin": version,
                            "incubating": None,
                            "stable": None,
                        },
                        "default_channel": "builtin",
                    }
                },
            }
            write_json(
                self.root / "policy.json",
                {
                    "schema": "kit-release-policy-1",
                    "incubating": {
                        "require_local_activation": True,
                        "minimum_fixture_cases": 3,
                    },
                    "stable": {"minimum_distinct_accepted_sites": 2},
                    "note": "Permissions do not bypass validation. Stable is not granted automatically.",
                },
            )
            write_json(self.root / "registry.json", registry)
            return registry

    def grant(self, subject, packages, actions, hours=24 * 30):
        return self.permissions.grant(subject, packages, actions, hours)

    def authorize(self, token, subject, package, action):
        return self.permissions.authorize(token, subject, package, action)

    def revoke(self, token):
        return self.permissions.revoke(token)

    def verify_release(self, package, version):
        return self.releases.verify_release(package, version)

    def resolve(self, package="buildings", channel=None, version=None):
        return self.releases.resolve(package, channel, version)

    def pin(self, destination, package="buildings", channel=None, version=None):
        return self.releases.pin(destination, package, channel, version)

    def search(self, query, limit=6):
        return self.releases.search(query, limit)

    def validate(self, submission_id, heldout_runs=()):
        return self.validator.validate(submission_id, heldout_runs)

    def submit(self, manifest, package, token, subject="workflow"):
        return self.publisher.submit(manifest, package, token, subject)

    def promote(
        self, submission_id, channel, token, subject="workflow", set_default=False
    ):
        return self.publisher.promote(
            submission_id, channel, token, subject, set_default
        )

    def rollback(self, package, channel, version, token, subject="operator"):
        return self.publisher.rollback(package, channel, version, token, subject)


Library = KitRegistry

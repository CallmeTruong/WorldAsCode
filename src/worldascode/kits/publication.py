"""KitPublisher: isolated kit-library responsibility."""

import re
import shutil
import uuid
from pathlib import Path

from worldascode.kits.context import cards
from worldascode.kits.registry import SLUG, package_files, read
from worldascode.storage.artifacts import digest, file_hash, run_lock, write_json


class KitPublisher:
    def __init__(self, registry):
        self.registry = registry
        self.root = registry.root

    def submit(self, manifest, package, token, subject="workflow"):
        self.registry.authorize(token, subject, package, "submit")
        if not SLUG.fullmatch(package):
            raise ValueError("INVALID_KIT_PACKAGE")
        # Verify the local activation and dependencies using the same loader used
        # by design runs; a model-proposed release label is never sufficient.
        from worldascode.kits.evolution import copy_active_version

        record = read(manifest)
        submission_id = digest({"manifest": file_hash(manifest), "package": package})
        folder = self.root / "submissions" / submission_id
        with run_lock(self.root):
            if (folder / "submission.json").exists():
                return read(folder / "submission.json")
            folder.mkdir(parents=True, exist_ok=True)
            copy_active_version(manifest, folder / "runtime")
            if file_hash(folder / "runtime/kit.mjs") != record["sha256"]:
                raise ValueError("KIT_SUBMISSION_COPY_MISMATCH")
            cycle = Path(record["path"]).parent.parent
            permissions = read(cycle / "permissions.json")
            proposal = read(cycle / "proposal.json")
            write_json(folder / "permissions.json", permissions)
            write_json(folder / "proposal.json", proposal)
            shutil.copy2(cycle / "exercise.json", folder / "exercise.json")
            decision = read(record.get("validation_path", cycle / "decision.json"))
            write_json(folder / "activation.json", decision)
            data = {
                "id": submission_id,
                "package": package,
                "subject": subject,
                "candidate_sha256": record["sha256"],
                "base_sha256": permissions["base_sha256"],
                "state": "submitted",
                "provenance": str(Path(manifest).resolve()),
                "input_hashes": self.registry.validator._submission_hashes(folder),
            }
            write_json(folder / "submission.json", data)
            return data

    def promote(
        self, submission_id, channel, token, subject="workflow", set_default=False
    ):
        if channel not in ("incubating", "stable") or not re.fullmatch(
            r"[a-f0-9]{64}", submission_id
        ):
            raise ValueError("INVALID_KIT_PROMOTION")
        folder = self.root / "submissions" / submission_id
        submission = read(folder / "submission.json")
        package = submission["package"]
        self.registry.authorize(token, subject, package, "promote-" + channel)
        if set_default:
            self.registry.authorize(token, subject, package, "set-default")
        with run_lock(self.root):
            validation = read(folder / "validation.json")
            if (
                file_hash(folder / "validation.json")
                != submission.get("validation_sha256")
                or self.registry.validator._submission_hashes(folder)
                != submission["input_hashes"]
                or validation["input_hashes"] != submission["input_hashes"]
                or validation["policy_sha256"] != file_hash(self.root / "policy.json")
                or not validation.get(channel + "_eligible")
            ):
                raise ValueError("KIT_PROMOTION_GATES_FAILED")
            if channel == "stable":
                for site in validation["heldout_sites"]:
                    if site["accepted"] and any(
                        not Path(path).is_file() or file_hash(path) != expected
                        for path, expected in site["artifacts"].items()
                    ):
                        raise ValueError("KIT_HELDOUT_EVIDENCE_CHANGED")
            registry = read(self.root / "registry.json")
            channel_head = registry["packages"][package]["channels"][channel]
            head, _ = (
                self.registry.resolve(package, version=channel_head)
                if channel_head
                else self.registry.resolve(package)
            )
            if file_hash(head / "kit.mjs") not in (
                submission["base_sha256"],
                submission["candidate_sha256"],
            ):
                raise ValueError("KIT_SHARED_HEAD_CONFLICT_REBASE_REQUIRED")
            paths = package_files(folder / "runtime")
            if (folder / "runtime/version.json").is_file():
                paths.append(folder / "runtime/version.json")
            hashes = {
                p.relative_to(folder / "runtime").as_posix(): file_hash(p)
                for p in paths
            }
            version = digest(hashes)
            destination = self.root / "releases" / package / version
            if not destination.exists():
                destination.mkdir(parents=True)
                for path in paths:
                    target = destination / path.relative_to(folder / "runtime")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                write_json(
                    destination / "release.json",
                    {
                        "schema": "shared-kit-release-1",
                        "package": package,
                        "version": version,
                        "files": hashes,
                        "channel": channel,
                        "submission": submission_id,
                        "validation_sha256": file_hash(folder / "validation.json"),
                    },
                )
                write_json(
                    destination / "context-index.json",
                    {
                        "cards": [
                            {"id": c["id"], "methods": c["methods"]}
                            for c in cards(destination / "kit-api.md").values()
                        ]
                    },
                )
            self.registry.verify_release(package, version)
            previous = registry["packages"][package]["channels"][channel]
            registry["packages"][package]["channels"][channel] = version
            if set_default:
                registry["packages"][package]["default_channel"] = channel
            registry["revision"] += 1
            write_json(self.root / "registry.json", registry)
            write_json(
                self.root / "events" / f"{uuid.uuid4().hex}.json",
                {
                    "action": "promote",
                    "package": package,
                    "channel": channel,
                    "version": version,
                    "previous": previous,
                    "subject": subject,
                    "grant_fingerprint": digest(token),
                    "submission": submission_id,
                },
            )
            return {
                "package": package,
                "channel": channel,
                "version": version,
                "default_changed": set_default,
            }

    def rollback(self, package, channel, version, token, subject="operator"):
        self.registry.authorize(token, subject, package, "rollback")
        if channel not in ("incubating", "stable"):
            raise ValueError("INVALID_KIT_CHANNEL")
        self.registry.verify_release(package, version)
        with run_lock(self.root):
            registry = read(self.root / "registry.json")
            history = [read(p) for p in (self.root / "events").glob("*.json")]
            installed = {
                e["version"]
                for e in history
                if e["package"] == package
                and e["channel"] == channel
                and e["action"] == "promote"
            }
            if channel == "incubating":
                installed.add(registry["packages"][package]["channels"]["builtin"])
            if version not in installed:
                raise ValueError("KIT_ROLLBACK_REQUIRES_PREVIOUS_CHANNEL_RELEASE")
            prior = registry["packages"][package]["channels"][channel]
            registry["packages"][package]["channels"][channel] = version
            registry["revision"] += 1
            write_json(self.root / "registry.json", registry)
            write_json(
                self.root / "events" / f"{uuid.uuid4().hex}.json",
                {
                    "action": "rollback",
                    "package": package,
                    "channel": channel,
                    "version": version,
                    "previous": prior,
                    "subject": subject,
                    "grant_fingerprint": digest(token),
                },
            )
        return {"package": package, "channel": channel, "version": version}

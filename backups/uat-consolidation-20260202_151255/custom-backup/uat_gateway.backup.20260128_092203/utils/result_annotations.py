"""
Result Annotations System - Feature #386

Allows users to add annotations/notes to test results for documentation and analysis.
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import uuid

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Annotation:
    """Represents an annotation/note on a test result"""
    id: str
    test_id: str
    content: str
    user_id: str
    username: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "test_id": self.test_id,
            "content": self.content,
            "user_id": self.user_id,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Annotation':
        """Create from dictionary"""
        return cls(
            id=data["id"],
            test_id=data["test_id"],
            content=data["content"],
            user_id=data["user_id"],
            username=data["username"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        )


# ============================================================================
# Annotation Store
# ============================================================================

class AnnotationStore:
    """
    Manages annotations for test results

    Features:
    - Add annotations to results
    - Retrieve annotations by test_id
    - Update annotations
    - Delete annotations
    - Persist annotations to disk
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the annotation store

        Args:
            storage_path: Path to JSON file for persistence (defaults to data/annotations.json)
        """
        self.logger = get_logger(__name__)

        # Storage: test_id -> List[Annotation]
        self._annotations: Dict[str, List[Annotation]] = {}

        # Persistence
        if storage_path is None:
            storage_path = "data/annotations.json"
        self.storage_path = Path(storage_path)

        # Create data directory if needed
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing annotations
        self._load_from_disk()

        self.logger.info(f"AnnotationStore initialized with {len(self._annotations)} test results having annotations")

    def add_annotation(
        self,
        test_id: str,
        content: str,
        user_id: str,
        username: str
    ) -> Annotation:
        """
        Add an annotation to a test result

        Args:
            test_id: Test result ID
            content: Annotation text content
            user_id: User ID adding the annotation
            username: Username adding the annotation

        Returns:
            Created annotation
        """
        annotation = Annotation(
            id=str(uuid.uuid4()),
            test_id=test_id,
            content=content,
            user_id=user_id,
            username=username,
            created_at=datetime.now()
        )

        if test_id not in self._annotations:
            self._annotations[test_id] = []

        self._annotations[test_id].append(annotation)
        self._save_to_disk()

        self.logger.info(
            f"User '{username}' added annotation to test result '{test_id}' "
            f"(annotation_id={annotation.id})"
        )

        return annotation

    def get_annotations(self, test_id: str) -> List[Annotation]:
        """
        Get all annotations for a test result

        Args:
            test_id: Test result ID

        Returns:
            List of annotations (sorted by created_at, newest first)
        """
        if test_id not in self._annotations:
            return []

        # Sort by created_at descending (newest first)
        return sorted(
            self._annotations[test_id],
            key=lambda a: a.created_at,
            reverse=True
        )

    def update_annotation(
        self,
        annotation_id: str,
        content: str,
        user_id: str,
        username: str
    ) -> Optional[Annotation]:
        """
        Update an existing annotation

        Args:
            annotation_id: Annotation ID
            content: New content
            user_id: User ID making the update
            username: Username making the update

        Returns:
            Updated annotation or None if not found
        """
        for test_id, annotations in self._annotations.items():
            for annotation in annotations:
                if annotation.id == annotation_id:
                    # Check user owns this annotation
                    if annotation.user_id != user_id:
                        self.logger.warning(
                            f"User '{username}' attempted to update annotation '{annotation_id}' "
                            f"owned by user '{annotation.user_id}'"
                        )
                        return None

                    annotation.content = content
                    annotation.updated_at = datetime.now()
                    self._save_to_disk()

                    self.logger.info(
                        f"User '{username}' updated annotation '{annotation_id}' "
                        f"on test result '{test_id}'"
                    )

                    return annotation

        return None

    def delete_annotation(self, annotation_id: str, user_id: str, username: str) -> bool:
        """
        Delete an annotation

        Args:
            annotation_id: Annotation ID
            user_id: User ID making the delete
            username: Username making the delete

        Returns:
            True if deleted, False if not found or unauthorized
        """
        for test_id, annotations in self._annotations.items():
            for i, annotation in enumerate(annotations):
                if annotation.id == annotation_id:
                    # Check user owns this annotation
                    if annotation.user_id != user_id:
                        self.logger.warning(
                            f"User '{username}' attempted to delete annotation '{annotation_id}' "
                            f"owned by user '{annotation.user_id}'"
                        )
                        return False

                    del annotations[i]

                    # Clean up empty test_id entries
                    if not annotations:
                        del self._annotations[test_id]

                    self._save_to_disk()

                    self.logger.info(
                        f"User '{username}' deleted annotation '{annotation_id}' "
                        f"on test result '{test_id}'"
                    )

                    return True

        return False

    def _save_to_disk(self) -> None:
        """Save annotations to disk as JSON"""
        data = {
            "annotations": [
                annotation.to_dict()
                for annotations in self._annotations.values()
                for annotation in annotations
            ],
            "updated_at": datetime.now().isoformat()
        }

        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.debug(f"Saved {data['annotations']} annotations to {self.storage_path}")

    def _load_from_disk(self) -> None:
        """Load annotations from disk"""
        if not self.storage_path.exists():
            self.logger.info(f"No existing annotations file at {self.storage_path}")
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            # Load annotations
            for annotation_data in data.get("annotations", []):
                annotation = Annotation.from_dict(annotation_data)
                test_id = annotation.test_id

                if test_id not in self._annotations:
                    self._annotations[test_id] = []

                self._annotations[test_id].append(annotation)

            self.logger.info(f"Loaded {len(data.get('annotations', []))} annotations from disk")

        except Exception as e:
            self.logger.error(f"Failed to load annotations from disk: {e}")


# ============================================================================
# Global Store Instance
# ============================================================================

_annotation_store: Optional[AnnotationStore] = None


def get_annotation_store() -> AnnotationStore:
    """
    Get the global annotation store instance (singleton pattern)

    Returns:
        AnnotationStore instance
    """
    global _annotation_store
    if _annotation_store is None:
        _annotation_store = AnnotationStore()
    return _annotation_store

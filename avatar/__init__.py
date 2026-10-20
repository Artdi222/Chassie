"""Model-specific expression capabilities independent of the rendering backend."""

from .controller import AvatarController
from .manifest import ExpressionMapping, AvatarManifest, load_manifest, audit_assets

__all__ = ["AvatarController", "ExpressionMapping", "AvatarManifest", "load_manifest", "audit_assets"]

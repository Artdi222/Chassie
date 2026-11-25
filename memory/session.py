"""Manually controlled participant scope, independent of speaker/face recognition."""

from dataclasses import dataclass
import threading

from .store import Memory, bounded_text


@dataclass(frozen=True)
class Guest:
    id: str
    name: str
    invited: bool = False


@dataclass(frozen=True)
class RequestContext:
    revision: int
    memory_revision: int
    scope: str
    mode: str
    memories: tuple[Memory, ...]
    shared_notes: tuple[str, ...]


class SessionContext:
    """Presence suspends personal context even before an invitation is accepted.

    Callers must cancel generation/playback and clear model conversation history
    when revision changes; filtering new memories alone cannot sanitize history.
    Presence is supplied explicitly by the controller, not detected here.
    """

    def __init__(self, owner_profile_id=None, mode='focus'):
        self._lock = threading.RLock()
        self._revision = 0
        self._owner_profile_id = owner_profile_id
        self._owner_present = owner_profile_id is not None
        self._guests = {}
        self._shared_notes = []
        self._mode = 'focus'
        self.set_mode(mode)

    @property
    def revision(self):
        with self._lock:
            return self._revision

    @property
    def mode(self):
        return self._mode

    @property
    def owner_profile_id(self):
        return self._owner_profile_id

    @property
    def owner_present(self):
        return self._owner_present

    @property
    def guests(self):
        with self._lock:
            return tuple(self._guests.values())

    def set_owner(self, profile_id):
        """Trusted local UI selection only; never invoke from a speaker's claim."""
        with self._lock:
            if profile_id != self._owner_profile_id:
                self._owner_profile_id = profile_id
                self._owner_present = profile_id is not None
                self._shared_notes.clear()
                self._revision += 1

    def set_owner_present(self, present):
        if not isinstance(present, bool):
            raise ValueError('present must be a boolean')
        with self._lock:
            if present != self._owner_present:
                self._owner_present = present
                self._revision += 1

    def set_mode(self, mode):
        if mode not in ('focus', 'casual'):
            raise ValueError('mode must be focus or casual')
        with self._lock:
            if mode != self._mode:
                self._mode = mode
                self._revision += 1

    def mark_guest_present(self, guest_id, name='Guest'):
        guest_id = bounded_text(guest_id, 'guest_id', 100)
        name = bounded_text(name, 'name', 100)
        with self._lock:
            previous = self._guests.get(guest_id)
            if previous and previous.name == name:
                return previous
            if previous is None and len(self._guests) >= 16:
                raise ValueError('Maximum of 16 temporary guests reached')
            guest = Guest(guest_id, name, previous.invited if previous else False)
            self._guests[guest_id] = guest
            # Notes shared with previous participants are not implicitly shared
            # with an additional person, even if that person is later invited.
            if previous is None:
                self._shared_notes.clear()
            self._revision += 1
            return guest

    def invite_guest(self, guest_id):
        """A local owner's action; this neither enrolls nor verifies a guest."""
        with self._lock:
            if guest_id not in self._guests:
                raise KeyError('Guest is not present')
            guest = self._guests[guest_id]
            if not guest.invited:
                guest = Guest(guest.id, guest.name, True)
                self._guests[guest_id] = guest
                self._revision += 1
            return guest

    def remove_guest(self, guest_id):
        with self._lock:
            if guest_id not in self._guests:
                return False
            del self._guests[guest_id]
            self._shared_notes.clear()
            self._revision += 1
            return True

    def add_shared_note(self, content):
        content = bounded_text(content, 'shared note', 2000)
        with self._lock:
            if len(self._shared_notes) >= 50:
                raise ValueError('Maximum of 50 shared session notes reached')
            self._shared_notes.append(content)
            self._revision += 1

    def clear(self):
        """End temporary session state; persistent profiles/memories remain."""
        with self._lock:
            self._guests.clear()
            self._shared_notes.clear()
            self._revision += 1

    def context_for_request(self, store):
        with self._lock:
            if self._guests:
                return RequestContext(self._revision, store.revision, 'shared', self._mode,
                                      (), tuple(self._shared_notes))
            if self._owner_present and self._owner_profile_id is not None:
                memory_revision, memories = store.snapshot(self._owner_profile_id)
                if memories is not None:
                    return RequestContext(self._revision, memory_revision, 'personal', self._mode,
                                          memories, ())
            return RequestContext(self._revision, store.revision, 'inactive', self._mode, (), ())

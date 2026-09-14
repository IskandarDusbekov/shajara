from .models import TREE_KEY_LENGTH


class TreeKeyConverter:
    """Matches a Tree.public_id — exactly the base64url alphabet, fixed length.

    Anything else (an old numeric id, a path traversal attempt, an injected
    payload) never reaches a view: it 404s in the URL resolver.
    """

    regex = r"[A-Za-z0-9_-]{%d}" % TREE_KEY_LENGTH

    def to_python(self, value):
        return value

    def to_url(self, value):
        return str(value)

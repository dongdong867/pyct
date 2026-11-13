"""The keys pyct gives a meaning in seed JSON, and how a plain dict writes a key that would
otherwise make it an object form.

A JSON object holding ``"__class__"`` is an object form. A plain dict that holds that key, one
the solver added it to say, writes it ``"!__class__"``, and a key of one or more ``!`` then
``__class__`` takes one ``!`` more, so every such key reads back as it was. No other key is
escaped. A form's and ``self``'s keys are a constructor's arguments, and are never escaped.
"""

# the key that names an object form's class, and the key of the items it passes by position
CLASS_KEY = "__class__"
ARGS_KEY = "__args__"

# what a plain dict's key starts with one more of when it is written
ESCAPE = "!"


def read_key(key: object) -> object:
    """A plain dict's key as seed JSON wrote it, read back: one ``!`` fewer on a str of one or
    more ``!`` then ``__class__``, any other key as it is."""
    if type(key) is str and _escaped(key):
        return key[len(ESCAPE) :]
    return key


def written_key(key: object) -> object:
    """A plain dict's key as seed JSON writes it: one ``!`` more on the str ``__class__`` or a
    str of ``!`` then ``__class__``, any other key as it is."""
    if type(key) is str and (key == CLASS_KEY or _escaped(key)):
        return ESCAPE + key
    return key


def _escaped(key: str) -> bool:
    """Whether a str is one or more ``!`` then ``__class__``."""
    bare = key.lstrip(ESCAPE)
    return bare == CLASS_KEY and len(bare) < len(key)

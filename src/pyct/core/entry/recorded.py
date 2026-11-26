"""The bounds a loss site's recorded run keeps to (`pyct.core.entry.losses`), apart from the
recording, so that the journal reads them with no import of it."""

# the runs of each loss site recorded in an input, its first
MOST_RUNS = 3
# a recorded value's JSON text is shorter than this many characters, each one byte
MOST_VALUE = 2048
# what an input's recorded runs may count together, by `size`
MOST_TEXT = 1024 * 1024
# what `size` counts for each run, and for each value, beside their characters
RUN_COUNT, VALUE_COUNT = 64, 2

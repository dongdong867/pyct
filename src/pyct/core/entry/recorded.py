"""The bounds a recorded run keeps to, a loop's (`pyct.core.entry.pieces`) and a loss site's
(`pyct.core.entry.losses`) alike, apart from either, so that importing the losses' recording
loads no hook of a piece."""

# the runs of each piece recorded in an input, its first
MOST_RUNS = 3
# a recorded value's JSON text is shorter than this many characters, each one byte
MOST_VALUE = 2048
# what an input's recorded runs may count together, by `size`
MOST_TEXT = 1024 * 1024
# what `size` counts for each run, and for each value, beside their characters
RUN_COUNT, VALUE_COUNT = 64, 2

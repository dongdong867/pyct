# camel_to_snake_case, copied from TheAlgorithms/Python, strings/camel_case_to_snake_case.py at
# commit 7f94a73eec45edfd215e8f07148c9c657b4e4b89:
# https://github.com/TheAlgorithms/Python/blob/7f94a73eec45edfd215e8f07148c9c657b4e4b89/strings/camel_case_to_snake_case.py
# The doctest runner under `if __name__ == "__main__":` is left out. Its license, from
# TheAlgorithms/Python's LICENSE.md:
#
# MIT License
#
# Copyright (c) 2016-2022 TheAlgorithms and contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


def camel_to_snake_case(input_str: str) -> str:
    """
    Transforms a camelCase (or PascalCase) string to snake_case

    >>> camel_to_snake_case("someRandomString")
    'some_random_string'

    >>> camel_to_snake_case("SomeRandomStr#ng")
    'some_random_str_ng'

    >>> camel_to_snake_case("123someRandom123String123")
    '123_some_random_123_string_123'

    >>> camel_to_snake_case("123SomeRandom123String123")
    '123_some_random_123_string_123'

    >>> camel_to_snake_case(123)
    Traceback (most recent call last):
        ...
    ValueError: Expected string as input, found <class 'int'>

    """

    # check for invalid input type
    if not isinstance(input_str, str):
        msg = f"Expected string as input, found {type(input_str)}"
        raise ValueError(msg)

    snake_str = ""

    for index, char in enumerate(input_str):
        if char.isupper():
            snake_str += "_" + char.lower()

        # if char is lowercase but proceeded by a digit:
        elif input_str[index - 1].isdigit() and char.islower():
            snake_str += "_" + char

        # if char is a digit proceeded by a letter:
        elif input_str[index - 1].isalpha() and char.isnumeric():
            snake_str += "_" + char.lower()

        # if char is not alphanumeric:
        elif not char.isalnum():
            snake_str += "_"

        else:
            snake_str += char

    # remove leading underscore
    if snake_str[0] == "_":
        snake_str = snake_str[1:]

    return snake_str

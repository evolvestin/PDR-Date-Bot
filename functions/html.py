import re
from typing import Any

# Mapping of characters to their HTML escape sequences
ESCAPE_SEQUENCES = {'{': '&#123;', '<': '&#60;', '}': '&#125;', '\'': '&#39;'}


def bold(text: Any) -> str:
    """Wraps the given text in bold HTML tags.

    :param text: The text to be bolded.
    :type text: Any
    :return: A string containing the HTML-bolded text.
    :rtype: str
    """
    return f'<b>{text}</b>'


def italic(text: Any) -> str:
    """Wraps the given text in italic HTML tags.

    :param text: The text to be italicized.
    :type text: Any
    :return: A string containing the HTML-italicized text.
    :rtype: str
    """
    return f'<i>{text}</i>'


def under(text: Any) -> str:
    """Wraps the given text in underline HTML tags.

    :param text: The text to be underlined.
    :type text: Any
    :return: A string containing the HTML-underlined text.
    :rtype: str
    """
    return f'<u>{text}</u>'


def code(text: Any) -> str:
    """Wraps the given text in code HTML tags.

    :param text: The text to be formatted as code.
    :type text: Any
    :return: A string containing the HTML code-formatted text.
    :rtype: str
    """
    return f'<code>{text}</code>'


def html_link(link: str, text: str) -> str:
    """Creates an HTML hyperlink with the specified URL and link text.

    :param link: The URL of the hyperlink.
    :type link: str
    :param text: The text to display for the hyperlink.
    :type text: str
    :return: A string containing the HTML hyperlink.
    :rtype: str
    """
    return f'<a href="{link}">{text}</a>'


def sub_tag(text: str) -> str:
    """Removes all HTML tags from the given text.

    :param text: The text from which to remove HTML tags.
    :type text: str
    :return: A string with HTML tags removed.
    :rtype: str
    """
    return re.sub('<.*?>', '', str(text))


def blockquote(text: Any, expandable: bool = False) -> str:
    """Wraps the given text in blockquote HTML tags, with an optional expandable attribute.

    :param text: The text to be wrapped in a blockquote.
    :type text: Any
    :param expandable: If True, includes an 'expandable' attribute in the blockquote tag.
    :type expandable: bool
    :return: A string containing the HTML blockquote.
    :rtype: str
    """
    return f"{'<blockquote expandable>' if expandable else '<blockquote>'}{text}</blockquote>"


def html_secure(text: Any, reverse: bool = False) -> str:
    """Escapes or unescapes HTML special characters in the given text.

    :param text: The text to secure (escape) or unsecure (unescape).
    :type text: Any
    :param reverse: If True, unescapes the text; otherwise, escapes it.
    :type reverse: bool
    :return: A string with HTML characters escaped (reverse=False) or unescaped (reverse=True).
    :rtype: str
    """
    for pattern, value in ESCAPE_SEQUENCES.items():
        text = re.sub(pattern, value, str(text)) if not reverse else re.sub(value, pattern, str(text))
    return text

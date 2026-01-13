from __future__ import annotations

from dataclasses import dataclass

ANSI_RESET = "\x1b[0m"


@dataclass(frozen=True)
class Style:
    prefix: str

    def apply(self, text: str, enabled: bool) -> str:
        if not enabled:
            return text
        return f"{self.prefix}{text}{ANSI_RESET}"


STYLES = {
    "bold": Style("\x1b[1m"),
    "blue": Style("\x1b[34m"),
    "cyan": Style("\x1b[36m"),
    "magenta": Style("\x1b[35m"),
    "green": Style("\x1b[32m"),
    "yellow": Style("\x1b[33m"),
    "red": Style("\x1b[31m"),
    "gray": Style("\x1b[90m"),
    "white": Style("\x1b[37m"),
}


def style_text(text: str, *, color: str | None = None, bold: bool = False, enabled: bool = True) -> str:
    if not enabled:
        return text
    output = text
    if color:
        output = STYLES[color].apply(output, True)
    if bold:
        output = STYLES["bold"].apply(output, True)
    return output

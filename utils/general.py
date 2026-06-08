import math
from typing import Iterator, Tuple


def gradient_text(
    text: str,
    start_color: Tuple[int, int, int] = (0, 0, 255),
    end_color: Tuple[int, int, int] = (255, 0, 255),
    frequency: float = 1.0,
) -> str:
    """终端渐变色文字"""
    def color_function(t: float) -> Tuple[int, int, int]:
        def interpolate(start: float, end: float, t: float) -> float:
            return start + (end - start) * (math.sin(math.pi * t * frequency) + 1) / 2
        r = round(interpolate(start_color[0], end_color[0], t))
        g = round(interpolate(start_color[1], end_color[1], t))
        b = round(interpolate(start_color[2], end_color[2], t))
        return (r, g, b)

    def gradient_gen(length: int) -> Iterator[Tuple[int, int, int]]:
        return (color_function(i / (length - 1)) for i in range(length))

    gradient = gradient_gen(len(text))
    return "".join(
        f"\033[38;2;{r};{g};{b}m{char}\033[0m"
        for char, (r, g, b) in zip(text, gradient)
    )

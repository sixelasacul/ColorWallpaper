"""Handles CLI parsing"""

import re
import argparse

from pathlib import Path
from typing import Tuple, Sequence, Type

from common import *
from Color import *


__all__ = ["get_options"]


resolution_re = re.compile(r"\s*(\d+)\s*[x:]\s*(\d+)\s*")


def resolution(arg: str) -> Tuple[int, int]:
    """Parses resolution CLI argument"""
    groups = resolution_re.fullmatch(arg)

    if groups is None:
        raise argparse.ArgumentTypeError("Unable to parse the resolution")

    res = int_tuple(groups.group(1), groups.group(2))

    if any(dimension < 150 for dimension in res):
        raise argparse.ArgumentTypeError("Minimal resolution is 150x150")

    return res


def positive(typ: Type):
    """Binds a type to the inner function

    :param typ: Type to be bound
    :return: A function that returns a number of max(:param typ:, 1)
    """

    def typed_positive(arg: str):
        """Parses a number from :param arg:. The smallest number returned is 1"""
        return max(1, typ(float(arg)))

    return typed_positive


def in_range(typ: Type, low: float, high: float):
    """Binds a range and type to the inner function

    :param typ: Type to be bound
    :param low: Lower bound
    :param high: Upper bound
    :return: A function that raises if a number is not in range.
    """
    low, high = sorted((low, high))

    def is_in_range(arg: str):
        """Parses a number from :param arg:
        :raises AssertionError: If not in the bound range
        """
        arg = typ(float(arg))
        if not low <= arg <= high:
            raise argparse.ArgumentTypeError(f'"{arg}" must be in range ({low}, {high})')

        return arg

    return is_in_range


def fix_casing(names: Sequence[str]):
    """Binds :param names: to the inner function
       fix_casing(('One', 'Two', 'Three'))('tHreE') ~> 'Three'\n
       fix_casing(('aaa', 'Aaa', 'bbb'))('BbB') ~> 'bbb'\n
       fix_casing(('aaa', 'Aaa', 'bbb'))('aaa') ~> 'aaa'\n
       fix_casing(('aaa', 'Aaa', 'bbb'))('aAa') ~> argparse.ArgumentTypeError  # Ambiguous choice

    :param names: Templates for the fixing, non-empty
    :return: A function that fixes casing
    """

    def cased(arg: str) -> str:
        """Fixes the casing of :param arg: using the bound :param names: as template

        :param arg: Argument that needs to be fixed
        :return: Correctly cased :param arg:
        """
        low_names = tuple(name.lower() for name in names)

        if not isinstance(arg, str) or arg.lower() not in low_names:
            raise argparse.ArgumentTypeError(f'Invalid choice: "{arg}". Chose from {names}')

        duplicate_names = set(name for name in low_names if low_names.count(name) > 1)

        if arg in names:
            arg = names[names.index(arg)]
        elif arg.lower() not in duplicate_names:
            arg = names[low_names.index(arg.lower())]
        else:
            raise argparse.ArgumentTypeError(
                f"Ambiguous choice: {arg}. Unable to decide between "
                f"{[name for name in names if name.lower() in duplicate_names and name.lower() == arg.lower()]}"
            )
        return arg

    return cased


def get_options(args: Sequence[str] = None) -> argparse.Namespace:
    """Parses CLI options

    :param args: None for `sys.argv`
    :return: Object with options as attributes
    """
    ret = argparse.ArgumentParser(
        description="Minimalist wallpaper generator", usage=f"python %(prog)s ...", allow_abbrev=False
    )

    general_g = ret.add_argument_group("General options")
    general_g.add_argument(
        "-o", "--output", metavar="PATH", type=Path, default=Path("out.png"), help="Image output path"
    )

    general_g.add_argument("-y", "--yes", action="store_true", help="Force overwrite of --output")

    color_g = ret.add_argument_group("Color options")
    color_g.add_argument("-c", "--color", default="random", help="Background color. #Hex / R,G,B / random / name")

    color_g.add_argument(
        "-c2", "--color2", metavar="COLOR", default="inverted", help="Highlight color. #Hex / R,G,B / inverted / name"
    )

    color_g.add_argument(
        "-d", "--display", help="Override the display name of --color. Empty string disables the name row"
    )

    color_g.add_argument(
        "--min-contrast",
        type=in_range(float, 1, 21),
        default=1,
        help="Min contrast of --color and --color2, if --color2 is `inverted`."
        "Must be in range (1-21). Will be raise if this can not be satisfied",
    )

    color_g.add_argument(
        "--overlay-color",
        metavar="COLOR",
        type=Color.from_str,
        help="Color of potential overlay, like icons or text. #Hex / R,G,B / name",
    )

    color_g.add_argument(
        "--overlay-contrast",
        type=in_range(float, 1, 21),
        default=1,
        help="Min contrast of --color and --overlay-color."
        "Must be in range (1-21). Will be raise if this can not be satisfied",
    )

    display_g = ret.add_argument_group("Display options")
    display_g.add_argument(
        "-r",
        "--resolution",
        type=resolution,
        default=(1920, 1080),
        help="The dimensions of the result image. WIDTHxHEIGHT",
    )

    display_g.add_argument(
        "-s", "--scale", type=positive(int), default=3, help="The size of the highlight will be divided by this"
    )

    display_g.add_argument(
        "-f",
        "--formats",
        type=fix_casing(("empty", "hex", "#hex", "HEX", "#HEX", "rgb", "hsv", "hsl", "cmyk")),
        default=["empty", "HEX", "rgb"],
        nargs="+",
        help="Declares the order and formats to display. Available choices: "
        "{hex, #hex, HEX, #HEX, rgb, hsv, hsl, cmyk, empty}",
    )

    ret = ret.parse_args(args)

    random = normalized(ret.color) == "random"
    inverted = normalized(ret.color2) == "inverted"

    if random:
        ret.color = Color.random()
    else:
        ret.color = Color.from_str(ret.color)

    while True:
        if ret.overlay_color is not None:
            if not random and ret.color / ret.overlay_color < ret.overlay_contrast:
                raise RuntimeError(
                    f"Contrast of {ret.color} and {ret.overlay_color} is lower than "
                    f"{ret.overlay_contrast} ({ret.color / ret.overlay_color})"
                )

            while ret.color / ret.overlay_color < ret.overlay_contrast:
                ret.color = Color.random()

        if inverted:
            try:
                ret.color2 = ret.color.inverted(ret.min_contrast)
            except RuntimeError:
                ret.color = Color.random()
            else:
                break
        else:
            ret.color2 = Color.from_str(ret.color2)
            break

    return ret

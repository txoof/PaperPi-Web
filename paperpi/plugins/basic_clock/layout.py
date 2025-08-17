# basic clock layout
from paperpi.library.font_search import locate_path

font_path = locate_path('fonts')

basic_clock = {
    'digit_time': {
        'type': 'TextBlock',
        'image': None,
        'max_lines': 2,
        'width': 1,
        'height': 1,
        'abs_coordinates': (0, 0),
        'rand': True,
        'font': font_path / 'Kanit/Kanit-Medium.ttf',
        'mode': 'L',
        'fill': 'BLACK',
        'bkground': 'WHITE'
    },
}

# set the default layout here
layout = basic_clock
